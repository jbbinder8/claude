"""
common.py — Infraestrutura compartilhada entre os módulos SICONFI/SIOPE.

Contém: cliente HTTP com retry, paginação ORDS, carregamento de entes,
leitura/gravação de checkpoint e exportação CSV.
"""

import json
import time
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

MODO_TESTE = False

_IBGE_PARANA   = 41        # Estado do Paraná
_IBGE_CURITIBA = 4106902   # Município de Curitiba / PR

# ---------------------------------------------------------------------------
# Sessão HTTP
# ---------------------------------------------------------------------------

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})


def _get(url: str, params: dict) -> dict:
    """GET com retry e back-off exponencial. Retorna {} em falha definitiva."""
    for tentativa in range(1, MAX_RETRY + 1):
        try:
            r = SESSION.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return {}
            if r.status_code == 429:
                espera = 30 * tentativa
                print(f"\n  [429] Rate limit — aguardando {espera}s...")
                time.sleep(espera)
            else:
                time.sleep(5 * tentativa)
        except requests.exceptions.Timeout:
            time.sleep(10 * tentativa)
        except Exception:
            time.sleep(10)
    return {}


def paginar(endpoint: str, params: dict = None, base_url: str = BASE_URL_SICONFI) -> list:
    """Itera todas as páginas ORDS (hasMore + offset). Retorna lista de items."""
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

def obter_entes() -> pd.DataFrame:
    """
    Retorna DataFrame com estados (E) e municípios (M) do SICONFI.
    Em MODO_TESTE, constrói o DataFrame diretamente (evita paginação de 6 mil+
    registros, que pode cortar resultados se uma página falhar no meio).
    """
    if MODO_TESTE:
        df = pd.DataFrame([
            {"cod_ibge": _IBGE_PARANA,   "ente": "Paraná",   "uf": "PR", "esfera": "E", "exercicio": 2026},
            {"cod_ibge": _IBGE_CURITIBA, "ente": "Curitiba", "uf": "PR", "esfera": "M", "exercicio": 2026},
        ])
        print(f"  [MODO TESTE] Paraná (E) + Curitiba (M) — sem chamada à API de entes")
        return df

    print("Carregando lista de entes...")
    items = paginar("entes")
    df = pd.DataFrame(items)
    df = df[df["esfera"].isin(["E", "M"])].copy()
    df = df.sort_values("exercicio", ascending=False).drop_duplicates("cod_ibge")
    print(f"  Estados: {(df.esfera=='E').sum()} | Municípios: {(df.esfera=='M').sum()}")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Checkpoint e CSV
# ---------------------------------------------------------------------------

def ler_checkpoint(path: Path) -> set:
    if path.exists():
        return set(json.loads(path.read_text(encoding="utf-8"))["feitos"])
    return set()


def gravar_checkpoint(path: Path, feitos: set):
    path.write_text(json.dumps({"feitos": list(feitos)}), encoding="utf-8")


def salvar_csv(path: Path, linhas: list):
    if linhas:
        pd.DataFrame(linhas).to_csv(
            path, sep=";", decimal=",",
            index=False, encoding="utf-8-sig"
        )


def imprimir_resumo(linhas: list, fonte: str):
    if not linhas:
        return
    df = pd.DataFrame(linhas)
    resumo = df.groupby(["indicador", "ano"]).agg(
        entes=("cod_ibge", "nunique"),
        total_reais=("valor", "sum"),
    )
    print(f"\nResumo {fonte} — por indicador × ano:")
    print(resumo.to_string())
