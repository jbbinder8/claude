"""
common.py — Infraestrutura compartilhada entre os módulos SICONFI/SIOPE.

Contém: cliente HTTP com retry, paginação ORDS, carregamento de entes,
leitura/gravação de checkpoint e exportação CSV.
"""

import csv
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Constantes globais
# ---------------------------------------------------------------------------

BASE_URL_SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"

ANOS       = list(range(2019, 2026))
PAUSA      = 0.20     # segundos entre requisições sequenciais
MAX_RETRY  = 3
MAX_WORKERS    = 8
SALVAR_A_CADA  = 200  # persiste checkpoint a cada N tarefas concluídas

# ---------------------------------------------------------------------------
# Modo teste — filtra para Paraná (estado) + Curitiba (município)
# Mude para False para rodar com a lista completa de entes.
# ---------------------------------------------------------------------------

MODO_TESTE = True

_IBGE_PARANA   = 41        # Estado do Paraná
_IBGE_CURITIBA = 4106902   # Município de Curitiba / PR

# ---------------------------------------------------------------------------
# Sessão HTTP — thread-local (cada worker do ThreadPoolExecutor recebe a sua)
# ---------------------------------------------------------------------------

_thread_local = threading.local()


def _get_session() -> requests.Session:
    """Retorna a Session da thread atual, criando-a sob demanda."""
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"Accept": "application/json"})
        _thread_local.session = s
    return s


class APIError(Exception):
    """Falha definitiva de rede/HTTP após esgotar os retries."""


def _get(url: str, params: dict) -> dict:
    """
    GET com retry e back-off. Retorna o JSON em sucesso (HTTP 200) ou {} em
    HTTP 404 (recurso inexistente — não é erro). Levanta APIError em qualquer
    outra falha definitiva (timeout, 5xx persistente, erro de rede), para que
    o chamador NÃO marque a tarefa como concluída em cima de dados truncados.
    """
    ultimo_motivo = "desconhecido"
    sessao = _get_session()
    for tentativa in range(1, MAX_RETRY + 1):
        try:
            r = sessao.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return {}
            if r.status_code == 429:
                espera = 30 * tentativa
                print(f"\n  [429] Rate limit — aguardando {espera}s...")
                time.sleep(espera)
                ultimo_motivo = "HTTP 429"
            else:
                time.sleep(5 * tentativa)
                ultimo_motivo = f"HTTP {r.status_code}"
        except requests.exceptions.Timeout:
            time.sleep(10 * tentativa)
            ultimo_motivo = "timeout"
        except requests.exceptions.RequestException as exc:
            time.sleep(10)
            ultimo_motivo = f"erro de rede: {exc.__class__.__name__}"
    raise APIError(f"Falha após {MAX_RETRY} tentativas em {url} ({ultimo_motivo})")


def paginar(endpoint: str, params: dict = None, base_url: str = BASE_URL_SICONFI) -> list:
    """
    Itera todas as páginas ORDS (hasMore + offset). Retorna lista de items.
    Propaga APIError se qualquer página falhar — nunca devolve resultado parcial.
    """
    todos, offset, limit = [], 0, 500
    base = {**(params or {}), "limit": limit}
    while True:
        d = _get(base_url + endpoint, {**base, "offset": offset})
        lote = d.get("items", [])
        todos.extend(lote)
        if not d.get("hasMore", False):
            break
        offset += limit
        time.sleep(PAUSA)
    return todos


# ---------------------------------------------------------------------------
# Entes
# ---------------------------------------------------------------------------

_MIN_ESTADOS    = 27     # 26 estados + DF
_MIN_MUNICIPIOS = 5500   # ~5570 municípios — margem para entes inativos


def obter_entes() -> pd.DataFrame:
    """
    Retorna DataFrame com estados (E) e municípios (M) do SICONFI.
    Em MODO_TESTE, constrói o DataFrame diretamente.

    Em produção, valida que a lista carregada tem o tamanho mínimo esperado
    (27 estados + ~5570 municípios). Levanta RuntimeError se a paginação
    devolveu lista vazia ou suspeitamente curta — sinal de falha parcial.
    """
    if MODO_TESTE:
        df = pd.DataFrame([
            {"cod_ibge": _IBGE_PARANA,   "ente": "Paraná",   "uf": "PR", "esfera": "E", "exercicio": max(ANOS)},
            {"cod_ibge": _IBGE_CURITIBA, "ente": "Curitiba", "uf": "PR", "esfera": "M", "exercicio": max(ANOS)},
        ])
        print(f"  [MODO TESTE] Paraná (E) + Curitiba (M) — sem chamada à API de entes")
        return df

    print("Carregando lista de entes...")
    items = paginar("entes")
    if not items:
        raise RuntimeError("API de entes retornou lista vazia — abortando para não corromper a base.")
    df = pd.DataFrame(items)
    if "esfera" not in df.columns:
        raise RuntimeError(f"Resposta da API de entes sem coluna 'esfera'. Colunas: {list(df.columns)}")
    df = df[df["esfera"].isin(["E", "M"])].copy()
    df = df.sort_values("exercicio", ascending=False).drop_duplicates("cod_ibge")
    n_e = int((df.esfera == "E").sum())
    n_m = int((df.esfera == "M").sum())
    print(f"  Estados: {n_e} | Municípios: {n_m}")
    if n_e < _MIN_ESTADOS or n_m < _MIN_MUNICIPIOS:
        raise RuntimeError(
            f"Lista de entes parece incompleta: {n_e} estados (mín {_MIN_ESTADOS}), "
            f"{n_m} municípios (mín {_MIN_MUNICIPIOS}). Possível falha de paginação. "
            "Re-execute para tentar novamente."
        )
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Checkpoint e CSV
# ---------------------------------------------------------------------------

def ler_checkpoint(path: Path) -> set:
    if not path.exists():
        return set()
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
        return set(dados.get("feitos", []))
    except (json.JSONDecodeError, OSError) as exc:
        # Checkpoint corrompido (queda durante escrita anterior, p.ex.).
        # Tratado como vazio: a re-execução fará a sincronização via CSV.
        print(f"  [AVISO] Checkpoint {path} ilegível ({exc}). Iniciando do zero — "
              "será reconstruído a partir do CSV existente, se houver.")
        return set()


def _gravar_atomico_text(path: Path, conteudo: str):
    """Escreve em arquivo temporário no mesmo diretório e faz rename atômico."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(conteudo, encoding="utf-8")
    tmp.replace(path)


def gravar_checkpoint(path: Path, feitos: set):
    """Grava checkpoint atomicamente (write tmp + rename), evitando corrupção."""
    _gravar_atomico_text(path, json.dumps({"feitos": list(feitos)}))


def ler_csv(path: Path, chaves_unicas: list = None) -> list:
    """
    Lê CSV existente e retorna lista de dicts. Retorna [] se não existir.

    Se `chaves_unicas` for fornecida, deduplica por essas colunas mantendo a
    última ocorrência. Usa-se para tolerar duplicação que possa surgir de uma
    queda entre a gravação do CSV e a do checkpoint (ver baixar() em cada módulo).
    """
    if not path.exists():
        return []
    df = pd.read_csv(path, sep=";", decimal=",")
    if chaves_unicas:
        faltantes = [c for c in chaves_unicas if c not in df.columns]
        if faltantes:
            print(f"  [AVISO] CSV {path} sem colunas {faltantes} — pulando deduplicação.")
        else:
            df = df.drop_duplicates(subset=chaves_unicas, keep="last")
    return df.to_dict("records")


def salvar_csv(path: Path, linhas: list):
    """
    Grava CSV atomicamente: escreve em arquivo temporário e faz rename. Se a
    execução for interrompida durante a escrita, o arquivo final permanece
    intacto (a versão anterior).
    """
    if not linhas:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    pd.DataFrame(linhas).to_csv(
        tmp, sep=";", decimal=",",
        index=False, encoding="utf-8-sig"
    )
    tmp.replace(path)


def imprimir_resumo(linhas: list, fonte: str):
    if not linhas:
        return
    df = pd.DataFrame(linhas)
    if not {"indicador", "ano", "cod_ibge", "valor"}.issubset(df.columns):
        return
    resumo = df.groupby(["indicador", "ano"]).agg(
        entes=("cod_ibge", "nunique"),
        total_reais=("valor", "sum"),
    )
    print(f"\nResumo {fonte} — por indicador × ano:")
    print(resumo.to_string())


# ---------------------------------------------------------------------------
# Log de execução — uma linha por módulo, agora com contagem de erros
# ---------------------------------------------------------------------------

_LOG_EXECUCAO = Path("output/receitas/log_execucao.csv")


def gravar_log_execucao(modulo: str, t_inicio: float, registros: int, erros: int = 0):
    """Acrescenta uma linha ao log de execução com duração, registros e erros."""
    _LOG_EXECUCAO.parent.mkdir(parents=True, exist_ok=True)
    novo = not _LOG_EXECUCAO.exists()
    with open(_LOG_EXECUCAO, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["data_hora", "modulo", "duracao_min", "registros", "erros"])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            modulo.upper(),
            f"{(time.time() - t_inicio) / 60:.1f}",
            registros,
            erros,
        ])
