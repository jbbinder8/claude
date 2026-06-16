"""
rreo_icms_estados_standalone.py
Extrai ICMS de estados via RREO/SICONFI, 2022-2026, por mês.
Salva 'rreo_icms_estados.csv' na mesma pasta do script.

A API retorna colunas <MR>, <MR-1>, ..., <MR-11> onde MR = mês de referência
(fim do bimestre). Para bimestre 6 (dezembro), MR=12 e MR-11=1 cobrem jan-dez.

Dependências: pip install requests tqdm
Uso: python rreo_icms_estados_standalone.py
"""

from __future__ import annotations

import csv
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from tqdm import tqdm

# Bypassa proxy corporativo para a API do Tesouro (acesso direto à internet gov)
os.environ.setdefault("NO_PROXY", "apidatalake.tesouro.gov.br")

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

BASE_URL     = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
MAX_WORKERS  = 6
PAUSA        = 0.20
MAX_RETRY    = 3
HTTP_TIMEOUT = (10, 45)

COD_ICMS = "ICMSLiquidoExcetoTransferenciasEFUNDEB"

ANO_ATUAL      = 2026
ANOS_COMPLETOS = list(range(2022, ANO_ATUAL))   # 2022-2025: bimestre 6 tem jan-dez completo

DIR_SAIDA = Path(__file__).resolve().parent
CSV_SAIDA = DIR_SAIDA / "rreo_icms_estados.csv"

# ---------------------------------------------------------------------------
# HTTP com retry
# ---------------------------------------------------------------------------

_thread_local = threading.local()


def _get_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"Accept": "application/json"})
        _thread_local.session = s
    return s


def _get(url: str, params: dict) -> dict:
    session = _get_session()
    for tentativa in range(1, MAX_RETRY + 1):
        try:
            r = session.get(url, params=params, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return {}
            if r.status_code == 429:
                time.sleep(30 * tentativa)
            else:
                time.sleep(5 * tentativa)
        except requests.exceptions.Timeout:
            time.sleep(10 * tentativa)
        except requests.exceptions.RequestException:
            time.sleep(10)
    return {}


def paginar(endpoint: str, params: dict) -> list:
    todos, offset, limit = [], 0, 500
    base = {**params, "limit": limit}
    while True:
        d = _get(BASE_URL + endpoint, {**base, "offset": offset})
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


def obter_estados() -> list[dict]:
    """Retorna lista de estados (esfera E + DF distrital tratado como estado)."""
    print("Carregando lista de estados...")
    items = paginar("entes", {})
    por_ibge: dict[int, dict] = {}
    for it in items:
        if it.get("esfera") not in ("E", "D"):   # D = Distrital (DF)
            continue
        cod = it.get("cod_ibge")
        ex = it.get("exercicio", 0)
        if cod not in por_ibge or ex > por_ibge[cod]["exercicio"]:
            por_ibge[cod] = dict(it)
    estados = list(por_ibge.values())
    print(f"  {len(estados)} estados encontrados")
    return estados

# ---------------------------------------------------------------------------
# Mapeamento de colunas <MR-k> → (ano, mês)
# ---------------------------------------------------------------------------


def _mr_para_mes_ano(coluna: str, ref_mes: int, ano: int) -> tuple[int, int] | tuple[None, None]:
    """
    Converte '<MR>' ou '<MR-k>' para (ano_resultado, mes).
    ref_mes = bimestre * 2  (ex: bimestre 6 → ref_mes = 12 = dezembro)
    Ajusta para ano anterior quando necessário (ex: ref_mes=2, k=3 → dezembro do ano anterior).
    """
    if coluna == "<MR>":
        k = 0
    elif coluna.startswith("<MR-") and coluna.endswith(">"):
        try:
            k = int(coluna[4:-1])
        except ValueError:
            return None, None
    else:
        return None, None

    mes = ref_mes - k
    ano_res = ano
    while mes <= 0:
        mes += 12
        ano_res -= 1
    return ano_res, mes

# ---------------------------------------------------------------------------
# Busca RREO
# ---------------------------------------------------------------------------


def buscar(id_ente: int, ano: int, bimestre: int, filtrar_ano: int) -> list[dict]:
    """
    Busca ICMS no RREO para (id_ente, ano, bimestre).
    Retorna apenas linhas cujo ano_resultado == filtrar_ano.
    ref_mes = bimestre * 2  (bimestre 6 → dezembro = mês 12).
    """
    ref_mes = bimestre * 2
    items = paginar("rreo", {
        "id_ente"              : id_ente,
        "an_exercicio"         : ano,
        "nr_periodo"           : bimestre,
        "co_tipo_demonstrativo": "RREO",
    })
    linhas = []
    for item in items:
        if item.get("cod_conta") != COD_ICMS:
            continue
        ano_res, mes = _mr_para_mes_ano(item.get("coluna", ""), ref_mes, ano)
        if ano_res != filtrar_ano:
            continue
        linhas.append({
            "co_uf"   : item.get("uf", ""),
            "cod_ibge": id_ente,
            "no_ente" : item.get("instituicao", ""),
            "ano"     : ano_res,
            "mes"     : mes,
            "valor"   : item.get("valor"),
        })
    return linhas

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    estados = obter_estados()

    # Anos completos (2022-2025): bimestre 6 contém todos os 12 meses do ano
    # Ano atual (2026): bimestres 1, 2, 3 — captura o que já foi publicado
    tarefas: list[tuple] = []
    for est in estados:
        cod = est["cod_ibge"]
        for ano in ANOS_COMPLETOS:
            tarefas.append((cod, est, ano, 6, ano))
        for bim in range(1, 4):
            tarefas.append((cod, est, ANO_ATUAL, bim, ANO_ATUAL))

    print(f"Requisições: {len(tarefas)}")

    todos: dict[tuple, dict] = {}   # (cod_ibge, ano, mes) → linha, deduplicado
    erros = 0

    def processar(args: tuple) -> list[dict]:
        id_ente, _, ano, bimestre, filtrar_ano = args
        return buscar(id_ente, ano, bimestre, filtrar_ano)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {executor.submit(processar, t): t for t in tarefas}
        with tqdm(total=len(tarefas), unit="req", desc="RREO ICMS") as pbar:
            for futuro in as_completed(futuros):
                try:
                    for ln in futuro.result():
                        chave = (ln["cod_ibge"], ln["ano"], ln["mes"])
                        todos[chave] = ln
                except Exception as exc:
                    tqdm.write(f"  Erro: {exc}")
                    erros += 1
                pbar.update(1)

    linhas = sorted(
        todos.values(),
        key=lambda x: (x["co_uf"], x["cod_ibge"], x["ano"], x["mes"]),
    )

    if not linhas:
        print("\nNenhum dado encontrado.")
        return

    for ln in linhas:
        if ln["valor"] is not None:
            ln["valor"] = str(ln["valor"]).replace(".", ",")

    with open(CSV_SAIDA, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["co_uf", "cod_ibge", "no_ente", "ano", "mes", "valor"],
            delimiter=";",
        )
        w.writeheader()
        w.writerows(linhas)

    err_str = f" | erros: {erros}" if erros else ""
    print(f"\n{len(linhas)} registros salvos em {CSV_SAIDA}{err_str}")


if __name__ == "__main__":
    main()
