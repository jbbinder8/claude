#!/usr/bin/env python3
"""
siconfi_dca_downloader.py
=========================
Extrai do SICONFI / DCA-Anexo I-C (Balanço Orçamentário - Receitas):

  • ICMS dos estados
  • ISS dos municípios
  • Cota-Parte do ICMS dos municípios

Período: 2019-2025  |  Coluna: "Receitas Brutas Realizadas"
Obs: mudança de plano de contas em 2022 — códigos distintos para 2019-2021 e 2022-2025.
Saída  : siconfi_dca/receitas_dca.csv  (sep=;  decimal=,  encoding=utf-8-sig)

Uso:
    pip install requests pandas
    python siconfi_dca_downloader.py

Retomada automática: apague siconfi_dca/checkpoint.json para recomeçar do zero.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

# -- Configurações --------------------------------------------------------------
BASE_URL   = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
ANOS       = list(range(2019, 2026))
DIR_SAIDA  = Path("siconfi_dca")
CHECKPOINT = DIR_SAIDA / "checkpoint.json"
CSV_SAIDA  = DIR_SAIDA / "receitas_dca.csv"

# Houve mudança de plano de contas em 2022; mapeamos por ano
# Apenas a coluna "Receitas Brutas Realizadas" é capturada
_CONTAS_E_ANTES = {"RO1.1.1.8.02.1.0": "ICMS"}
_CONTAS_E_DEPOIS = {"RO1.1.1.4.50.1.0": "ICMS"}
_CONTAS_M_ANTES = {"RO1.1.1.8.02.3.0": "ISS", "RO1.7.2.8.01.1.0": "Cota-Parte ICMS"}
_CONTAS_M_DEPOIS = {"RO1.1.1.4.51.1.0": "ISS", "RO1.7.2.1.50.0.0": "Cota-Parte ICMS"}

def contas_por_ano(esfera: str, ano: int) -> dict:
    if esfera == "E":
        return _CONTAS_E_ANTES if ano <= 2021 else _CONTAS_E_DEPOIS
    return _CONTAS_M_ANTES if ano <= 2021 else _CONTAS_M_DEPOIS

COLUNA_ALVO = "Receitas Brutas Realizadas"

PAUSA          = 0.20   # segundos entre requisições sequenciais
MAX_RETRY      = 3
MAX_WORKERS    = 8      # requisições paralelas (ajuste conforme tolerância da API)
SALVAR_A_CADA  = 200    # persiste CSV parcial a cada N combinações processadas

# -- HTTP helpers ---------------------------------------------------------------

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})


def _get(url: str, params: dict) -> dict:
    """GET com retry e back-off. Retorna dict vazio em falha definitiva."""
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


def _paginar(endpoint: str, params: dict = None) -> list:
    """Itera sobre páginas ORDS (hasMore + offset)."""
    todos, offset, limit = [], 0, 500
    base = {**(params or {}), "limit": limit}
    while True:
        d = _get(BASE_URL + endpoint, {**base, "offset": offset})
        lote = d.get("items", [])
        todos.extend(lote)
        if not d.get("hasMore", False):
            break
        offset += limit
        time.sleep(PAUSA)
    return todos

# -- Entes ----------------------------------------------------------------------

def obter_entes() -> pd.DataFrame:
    print("Carregando lista de entes...")
    items = _paginar("entes")
    df = pd.DataFrame(items)
    # A API retorna esfera já como campo; filtra estados e municípios
    df = df[df["esfera"].isin(["E", "M"])].copy()
    # Remove duplicatas por cod_ibge (mantém exercicio mais recente)
    df = df.sort_values("exercicio", ascending=False).drop_duplicates("cod_ibge")
    print(f"  Estados: {(df.esfera=='E').sum()} | Municípios: {(df.esfera=='M').sum()}")
    return df.reset_index(drop=True)

# -- DCA por ente/ano ------------------------------------------------------------

def buscar_uma_combinacao(cod_ibge: int, ano: int, esfera: str) -> list:
    """
    Retorna lista de dicts com os indicadores encontrados para o ente/ano.
    Chamada individual — pode ser usada em paralelo.
    """
    contas_alvo = contas_por_ano(esfera, ano)
    items = _paginar("dca", {
        "an_exercicio": ano,
        "no_anexo"    : "DCA-Anexo I-C",
        "id_ente"     : cod_ibge,
    })
    resultados = []
    for item in items:
        cod_conta = item.get("cod_conta", "")
        coluna    = item.get("coluna", "")
        if cod_conta in contas_alvo and coluna == COLUNA_ALVO:
            resultados.append({
                "esfera"    : "Estado" if esfera == "E" else "Município",
                "co_uf"     : item.get("uf", ""),
                "cod_ibge"  : cod_ibge,
                "no_ente"   : item.get("instituicao", ""),
                "ano"       : ano,
                "indicador" : contas_alvo[cod_conta],
                "cod_conta" : cod_conta,
                "conta"     : item.get("conta", ""),
                "valor"     : item.get("valor") or 0,
                "populacao" : item.get("populacao") or 0,
            })
    return resultados

# -- Checkpoint + CSV ------------------------------------------------------------

def ler_checkpoint() -> set:
    if CHECKPOINT.exists():
        return set(json.loads(CHECKPOINT.read_text(encoding="utf-8"))["feitos"])
    return set()


def gravar_checkpoint(feitos: set):
    CHECKPOINT.write_text(json.dumps({"feitos": list(feitos)}), encoding="utf-8")


def salvar_csv(linhas: list):
    if linhas:
        pd.DataFrame(linhas).to_csv(
            CSV_SAIDA, sep=";", decimal=",",
            index=False, encoding="utf-8-sig"
        )

# -- Main ------------------------------------------------------------------------

def main():
    DIR_SAIDA.mkdir(exist_ok=True)
    feitos = ler_checkpoint()
    linhas: list = []
    n_novos = 0

    entes_df = obter_entes()

    # Monta lista de tarefas pendentes: (cod_ibge, ano, esfera, no_ente, uf)
    tarefas = []
    for _, row in entes_df.iterrows():
        for ano in ANOS:
            chave = f"{row['esfera']}_{row['cod_ibge']}_{ano}"
            if chave not in feitos:
                tarefas.append((row["cod_ibge"], ano, row["esfera"],
                                row.get("ente", ""), row.get("uf", ""), chave))

    total     = len(entes_df) * len(ANOS)
    pendentes = len(tarefas)
    print(f"\nTotal combinações: {total} | Já processadas: {total-pendentes} | Pendentes: {pendentes}")
    print(f"Workers paralelos: {MAX_WORKERS}  |  Estimativa: ~{pendentes*PAUSA/MAX_WORKERS/60:.0f} min\n")

    concluidos = total - pendentes  # já feitos antes desta execução

    def _processar(args):
        cod_ibge, ano, esfera, no_ente, uf, chave = args
        resultado = buscar_uma_combinacao(cod_ibge, ano, esfera)
        return chave, resultado, no_ente, uf, ano

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {executor.submit(_processar, t): t for t in tarefas}

        for futuro in as_completed(futuros):
            try:
                chave, resultado, no_ente, uf, ano = futuro.result()
            except Exception as exc:
                print(f"\n  Erro em future: {exc}")
                continue

            linhas.extend(resultado)
            feitos.add(chave)
            concluidos += 1
            n_novos    += 1

            pct = concluidos / total * 100
            achou = f"[{len(resultado)} registro(s)]" if resultado else ""
            print(
                f"  [{pct:5.1f}%] {uf} {no_ente[:35]:<35} {ano}  {achou}   ",
                end="\r",
            )

            if n_novos % SALVAR_A_CADA == 0:
                gravar_checkpoint(feitos)
                salvar_csv(linhas)

    gravar_checkpoint(feitos)
    salvar_csv(linhas)

    print(f"\n\n{'-'*70}")
    print(f"Concluido!  {len(linhas)} registros -> {CSV_SAIDA}")

    if linhas:
        df = pd.DataFrame(linhas)
        resumo = df.groupby(["indicador", "ano"]).agg(
            entes=("cod_ibge", "nunique"),
            total_reais=("valor", "sum")
        )
        print("\nResumo por indicador × ano (Receitas Brutas Realizadas):")
        print(resumo.to_string())


if __name__ == "__main__":
    main()
