"""
baixar_dca_liquido.py
=====================

Baixa do SICONFI (Tesouro Nacional) o **valor líquido** das seguintes receitas
do DCA (Declaração de Contas Anuais, Anexo I-C — Balanço Orçamentário de
Receitas), para todos os entes brasileiros, no período 2013-2025:

    • ICMS              — estados (inclui Adicional ICMS-FCP quando existir)
    • ISS               — municípios (inclui Adicional ISS-FCP quando existir)
    • Cota-Parte ICMS   — municípios

Fórmula do valor líquido:

    valor_liquido = abs(RBR_principal)   - abs(ODR_principal)
                  + abs(RBR_adicional)   - abs(ODR_adicional)   (quando existir)

  - RBR = "Receitas Brutas Realizadas"
  - ODR = "Outras Deduções da Receita"

Em 2013-2016 a coluna "Outras Deduções da Receita" não existia nesses códigos —
o líquido se reduz a abs(RBR). Em 2017+ a ODR passa a ser descontada.

Plano de contas (PCASP) — 3 gerações cobertas:
  - 2013-2017 → PCASP "antigo"        (RO1.1.1.3.02.00.00 etc — sem FCP)
  - 2018-2021 → PCASP "intermediário" (RO1.1.1.8.02.x.0    — com FCP)
  - 2022-2025 → PCASP "novo"          (RO1.1.1.4.5x.y.0    — com FCP)

API do SICONFI não publica DCA para 2012. Esse ano é simplesmente pulado.

Saída: receitas_dca_liquido.csv (no mesmo diretório do script).
Colunas: cod_ibge ; nome ; tipo_receita ; ano ; valor_liquido

Distrito Federal: incluído duas vezes — como estado (id_ente=53) para o ICMS
e como município (id_ente=5300108) para ISS/Cota-Parte. O cod_ibge gravado no
CSV é o que foi enviado à API.

Dependências:
    pip install requests pandas tqdm

Uso:
    python baixar_dca_liquido.py

Permite retomada: se interrompido, basta rodar de novo — registros já gravados
no CSV não serão re-baixados.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

BASE_URL    = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
ANOS        = list(range(2013, 2026))           # 2013 a 2025 (API não tem 2012)
MAX_WORKERS = 6                                 # 8 causou TCP hangs no Azure
PAUSA       = 0.20                              # entre páginas da paginação
MAX_RETRY   = 3
SALVAR_A_CADA = 100                             # persiste CSV a cada N entes

# Timeouts: (connect, read). connect curto detecta network down rapido;
# read um pouco maior porque a API as vezes demora ate 30s pra responder uma
# pagina cheia. Total max por chamada = read_timeout. Se a TCP travar sem
# resposta, este timeout dispara e o retry assume.
HTTP_TIMEOUT = (10, 45)

DIR_SAIDA = Path(__file__).resolve().parent
CSV_SAIDA = DIR_SAIDA / "receitas_dca_liquido.csv"

# Distrito Federal: no SICONFI, todo o dado é publicado sob id_ente=53.
# Brasília (5300108) não retorna nada no DCA. Para coletar ISS/Cota-Parte do
# DF, consultamos id_ente=53 com esfera "M".
_IBGE_BRASILIA  = 5300108
_IBGE_DF_ESTADO = 53
IBGE_PARA_ID_ENTE: dict[int, int] = {_IBGE_BRASILIA: _IBGE_DF_ESTADO}

# ---------------------------------------------------------------------------
# Plano de contas (PCASP) — 3 gerações
# ---------------------------------------------------------------------------
# Para cada (esfera, ano) → lista de "componentes" SOMADOS para formar o
# valor líquido do indicador final.
#
# Cada componente é (cod_conta, "principal"|"adicional").
# O valor líquido do componente é abs(RBR) - abs(ODR).
# O valor líquido do indicador é a soma de seus componentes.

# 2013-2017 (PCASP antigo) — não havia Adicional FCP, ODR só a partir de 2017
_CONTAS_2013_2017 = {
    ("E", "ICMS"): [
        ("RO1.1.1.3.02.00.00", "principal"),   # ICMS estadual
    ],
    ("M", "ISS"): [
        ("RO1.1.1.3.05.00.00", "principal"),   # ISSQN municipal
    ],
    ("M", "Cota-Parte ICMS"): [
        ("RO1.7.2.2.01.01.00", "principal"),   # Cota-Parte ICMS para municípios
    ],
}

# 2018-2021 (PCASP intermediário) — Adicional FCP já existe
_CONTAS_2018_2021 = {
    ("E", "ICMS"): [
        ("RO1.1.1.8.02.1.0", "principal"),
        ("RO1.1.1.8.02.2.0", "adicional"),     # Adicional ICMS-FCP
    ],
    ("M", "ISS"): [
        ("RO1.1.1.8.02.3.0", "principal"),
        ("RO1.1.1.8.02.4.0", "adicional"),     # Adicional ISS-FCP
    ],
    ("M", "Cota-Parte ICMS"): [
        ("RO1.7.2.8.01.1.0", "principal"),
    ],
}

# 2022-2025 (PCASP novo)
_CONTAS_2022_2025 = {
    ("E", "ICMS"): [
        ("RO1.1.1.4.50.1.0", "principal"),
        ("RO1.1.1.4.50.2.0", "adicional"),
    ],
    ("M", "ISS"): [
        ("RO1.1.1.4.51.1.0", "principal"),
        ("RO1.1.1.4.51.2.0", "adicional"),
    ],
    ("M", "Cota-Parte ICMS"): [
        ("RO1.7.2.1.50.0.0", "principal"),
    ],
}


def _contas_por_ano(esfera: str, ano: int) -> dict:
    """Retorna {cod_conta: (indicador, papel)} válido para esfera/ano."""
    if ano <= 2017:
        fonte = _CONTAS_2013_2017
    elif ano <= 2021:
        fonte = _CONTAS_2018_2021
    else:
        fonte = _CONTAS_2022_2025
    out: dict[str, tuple[str, str]] = {}
    for (esf, indicador), componentes in fonte.items():
        if esf != esfera:
            continue
        for cod, papel in componentes:
            out[cod] = (indicador, papel)
    return out


# ---------------------------------------------------------------------------
# HTTP — sessão por thread, com retry simples
# ---------------------------------------------------------------------------

_thread_local = threading.local()


def _session() -> requests.Session:
    s = getattr(_thread_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"Accept": "application/json"})
        _thread_local.s = s
    return s


def _reset_session() -> None:
    """Fecha e descarta a session da thread atual.
    Usado após timeout: força um novo TCP/TLS handshake em vez de tentar
    reusar uma conexao zumbi do pool keep-alive."""
    s = getattr(_thread_local, "s", None)
    if s is not None:
        try:
            s.close()
        except Exception:
            pass
        _thread_local.s = None


def _get(url: str, params: dict) -> dict:
    """GET com retry e back-off. 404 retorna {} (não é erro)."""
    motivo = "?"
    for tent in range(1, MAX_RETRY + 1):
        try:
            r = _session().get(url, params=params, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return {}
            if r.status_code == 429:
                time.sleep(30 * tent)
                motivo = "HTTP 429"
            else:
                time.sleep(5 * tent)
                motivo = f"HTTP {r.status_code}"
        except requests.exceptions.Timeout:
            # Após timeout, descarta a session: conexao pode estar zumbi
            _reset_session()
            time.sleep(5 * tent)
            motivo = "timeout"
        except requests.exceptions.RequestException as exc:
            _reset_session()
            time.sleep(10)
            motivo = f"rede:{exc.__class__.__name__}"
    raise RuntimeError(f"Falha após {MAX_RETRY} tentativas em {url} ({motivo})")


def _paginar(endpoint: str, params: dict) -> list:
    todos, offset, limit = [], 0, 500
    base = {**params, "limit": limit}
    while True:
        d = _get(BASE_URL + endpoint, {**base, "offset": offset})
        todos.extend(d.get("items", []))
        if not d.get("hasMore", False):
            break
        offset += limit
        time.sleep(PAUSA)
    return todos


# ---------------------------------------------------------------------------
# Lista de entes (estados + municípios)
# ---------------------------------------------------------------------------

_MIN_ESTADOS    = 26
_MIN_MUNICIPIOS = 5500


def obter_entes() -> pd.DataFrame:
    """Baixa lista de entes do SICONFI e adiciona DF como estado sintético."""
    print("Carregando lista de entes...")
    items = _paginar("entes", {})
    if not items:
        raise RuntimeError("API de entes retornou lista vazia.")
    df = pd.DataFrame(items)
    df = df[df["esfera"].isin(["E", "M"])].copy()
    df = df.sort_values("exercicio", ascending=False).drop_duplicates("cod_ibge")

    # DF como estado sintético (para ICMS)
    df = pd.concat([df, pd.DataFrame([{
        "cod_ibge": _IBGE_DF_ESTADO,
        "ente":     "Distrito Federal",
        "uf":       "DF",
        "esfera":   "E",
        "exercicio": int(df["exercicio"].max()),
    }])], ignore_index=True)

    n_e = int((df.esfera == "E").sum())
    n_m = int((df.esfera == "M").sum())
    print(f"  Estados: {n_e} (incl. DF) | Municípios: {n_m}")
    if n_e < _MIN_ESTADOS or n_m < _MIN_MUNICIPIOS:
        raise RuntimeError(
            f"Lista incompleta ({n_e} E, {n_m} M). Re-execute para tentar novamente."
        )
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Busca por (ente, ano) → registros líquidos
# ---------------------------------------------------------------------------

COLUNAS_USADAS = {
    # 2013: nomes "curtos" (sem qualificadores)
    "Receitas Realizadas":          "RBR",   # bruto em 2013 (não havia "Brutas")
    # 2014+: nomenclatura padronizada
    "Receitas Brutas Realizadas":   "RBR",
    "Outras Deduções da Receita":   "ODR",   # só existe a partir de 2017
    # NOTA: "Deduções da Receita" (sem "Outras") em 2013 = FUNDEB, NÃO descontar.
    # NOTA: "Deduções - FUNDEB" e "Deduções - Transferências Constitucionais"
    #       em 2014-2016 também são FUNDEB/repartição, NÃO descontar.
}


def _buscar(cod_ibge: int, ano: int, esfera: str, nome: str) -> list[dict]:
    """
    Faz UMA chamada ao DCA (filtra por id_ente + ano) e calcula os valores
    líquidos de todos os indicadores aplicáveis. Retorna lista de dicts com:
    cod_ibge, nome, tipo_receita, ano, valor_liquido.
    """
    alvo = _contas_por_ano(esfera, ano)
    if not alvo:
        return []

    id_ente = IBGE_PARA_ID_ENTE.get(cod_ibge, cod_ibge)
    # NÃO filtrar por no_anexo: em 2013-2017 o campo vem None no banco e o
    # filtro server-side retorna 0 itens. Identificamos o Anexo I-C pelos
    # códigos de conta (RO1.1.1.x.x.x — receitas orçamentárias), o que é
    # suficiente e funciona em todos os anos.
    items = _paginar("dca", {
        "an_exercicio": ano,
        "id_ente":      id_ente,
    })

    # Acumulador: indicador -> {"principal": [rbr, odr], "adicional": [rbr, odr]}
    acc: dict[str, dict[str, list[float]]] = {}
    nome_api = nome or ""

    for item in items:
        cod_conta = item.get("cod_conta", "")
        coluna    = item.get("coluna", "")
        if cod_conta not in alvo or coluna not in COLUNAS_USADAS:
            continue
        indicador, papel = alvo[cod_conta]
        valor = item.get("valor")
        if valor is None:
            continue
        slot = acc.setdefault(indicador, {}).setdefault(papel, [0.0, 0.0])
        if COLUNAS_USADAS[coluna] == "RBR":
            slot[0] += abs(float(valor))
        else:  # ODR
            slot[1] += abs(float(valor))
        # Captura o nome do ente conforme a API, se vier
        if not nome_api:
            nome_api = item.get("instituicao", "") or ""

    out: list[dict] = []
    for indicador, papeis in acc.items():
        liquido = 0.0
        for papel, (rbr, odr) in papeis.items():
            liquido += rbr - odr
        out.append({
            "cod_ibge":      cod_ibge,
            "nome":          nome_api,
            "tipo_receita":  indicador,
            "ano":           ano,
            "valor_liquido": round(liquido, 2),
        })
    return out


# ---------------------------------------------------------------------------
# Persistência incremental
# ---------------------------------------------------------------------------

COLS_CSV = ["cod_ibge", "nome", "tipo_receita", "ano", "valor_liquido"]
CHAVE    = ["cod_ibge", "ano", "tipo_receita"]


def carregar_existente() -> tuple[list[dict], set[tuple]]:
    """Retorna (linhas, conjunto de (esfera_implicita, cod_ibge, ano) já feitos)."""
    if not CSV_SAIDA.exists():
        return [], set()
    df = pd.read_csv(CSV_SAIDA, sep=";", decimal=",", dtype={"cod_ibge": "int64", "ano": "int64"})
    df = df.drop_duplicates(subset=CHAVE, keep="last")
    return df.to_dict("records"), set()  # o "feitos" é reconstruído por (cod_ibge, ano) abaixo


def salvar_csv(linhas: list[dict]) -> None:
    if not linhas:
        return
    tmp = CSV_SAIDA.with_suffix(".csv.tmp")
    pd.DataFrame(linhas, columns=COLS_CSV).sort_values(
        ["cod_ibge", "ano", "tipo_receita"]
    ).to_csv(tmp, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    tmp.replace(CSV_SAIDA)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()
    print(f"Saída: {CSV_SAIDA}")
    print(f"Anos: {ANOS[0]}–{ANOS[-1]}  |  Workers: {MAX_WORKERS}")

    linhas, _ = carregar_existente()
    # Reconstruir "feitos" a partir do CSV: chave (cod_ibge, ano, esfera_inferida).
    # Como uma mesma (cod_ibge, ano) pode produzir 1 (estado=ICMS) ou 2 (município=ISS+CotaParte)
    # linhas, a presença de QUALQUER linha (cod_ibge, ano) basta para considerar feito.
    feitos: set[tuple[int, int]] = {(int(ln["cod_ibge"]), int(ln["ano"])) for ln in linhas}
    print(f"Registros já existentes no CSV: {len(linhas)}  | (cod_ibge,ano) já feitos: {len(feitos)}")

    entes = obter_entes()

    # Monta lista de tarefas (cod_ibge, ano, esfera, nome) pendentes
    tarefas = []
    for _, row in entes.iterrows():
        cod_ibge = int(row["cod_ibge"])
        esfera   = row["esfera"]
        nome     = str(row.get("ente", "") or "")
        for ano in ANOS:
            # Para o DF, a chave de "feito" precisa diferenciar estado (53) e
            # município (5300108) — e diferenciam, pois têm cod_ibge distintos.
            if (cod_ibge, ano) in feitos:
                continue
            tarefas.append((cod_ibge, ano, esfera, nome))

    total     = len(entes) * len(ANOS)
    pendentes = len(tarefas)
    print(f"Tarefas: total {total} | pendentes {pendentes}\n")

    if pendentes == 0:
        print("Nada a baixar — CSV já completo.")
        return

    erros = 0
    novos = 0

    def _job(args):
        cod_ibge, ano, esfera, nome = args
        return (cod_ibge, ano), _buscar(cod_ibge, ano, esfera, nome)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futuros = {exe.submit(_job, t): t for t in tarefas}
        with tqdm(total=pendentes, desc="DCA-líquido", unit="req") as pbar:
            for fut in as_completed(futuros):
                t = futuros[fut]
                try:
                    chave, registros = fut.result()
                except Exception as exc:
                    erros += 1
                    tqdm.write(f"  [ERRO] {t} → {exc}")
                    pbar.update(1)
                    continue

                linhas.extend(registros)
                feitos.add(chave)
                novos += 1
                pbar.set_postfix(uf=t[2], ano=t[1], n=len(registros))
                pbar.update(1)

                if novos % SALVAR_A_CADA == 0:
                    salvar_csv(linhas)

    # Deduplica antes do save final (caso retomada tenha repetido linhas)
    df_final = pd.DataFrame(linhas, columns=COLS_CSV)
    df_final = df_final.drop_duplicates(subset=CHAVE, keep="last")
    df_final = df_final.sort_values(["cod_ibge", "ano", "tipo_receita"])
    df_final.to_csv(CSV_SAIDA, sep=";", decimal=",", index=False, encoding="utf-8-sig")

    dur = (time.time() - t0) / 60
    print(f"\nConcluído — {len(df_final)} linhas | erros: {erros} | duração: {dur:.1f} min")
    print(f"Arquivo: {CSV_SAIDA}")

    # Resumo por (tipo_receita, ano)
    if not df_final.empty:
        resumo = df_final.groupby(["tipo_receita", "ano"]).agg(
            entes=("cod_ibge", "nunique"),
            total_bilhoes=("valor_liquido", lambda s: round(s.sum() / 1e9, 2)),
        )
        print("\nResumo por tipo_receita × ano (total em R$ bilhões):")
        print(resumo.to_string())


if __name__ == "__main__":
    main()
