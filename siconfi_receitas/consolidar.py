"""
consolidar.py — Agrega os CSVs de DCA, RREO e SIOPS em um único arquivo.

Entrada : output/receitas/receitas_{dca,rreo,siops}.csv
Saída   : output/receitas/receitas_consolidadas.csv

Colunas de saída:
    tipo_ente    — "Estado" ou "Município"
    cod_ibge     — código IBGE do ente
    tipo_receita — "ICMS", "ISS" ou "Cota-Parte ICMS"
    ano          — exercício
    fonte        — "DCA", "RREO" ou "SIOPS"
    valor        — receita em reais
"""

from pathlib import Path

import pandas as pd

DIR_RECEITAS = Path("output/receitas")
CSV_SAIDA    = DIR_RECEITAS / "receitas_consolidadas.csv"

_FONTES = {
    "DCA"  : DIR_RECEITAS / "receitas_dca.csv",
    "RREO" : DIR_RECEITAS / "receitas_rreo.csv",
    "SIOPS": DIR_RECEITAS / "receitas_siops.csv",
}

_COLUNAS_SAIDA = ["tipo_ente", "cod_ibge", "tipo_receita", "ano", "fonte", "valor"]


def consolidar() -> pd.DataFrame:
    """
    Lê os três CSVs de receitas, seleciona e renomeia as colunas relevantes,
    concatena e grava o arquivo consolidado.
    Retorna o DataFrame consolidado.
    """
    partes = []
    for fonte, caminho in _FONTES.items():
        if not caminho.exists():
            print(f"  [CONSOLIDAR] {caminho} não encontrado — pulando {fonte}.")
            continue
        df = pd.read_csv(caminho, sep=";", decimal=",",
                         usecols=["esfera", "cod_ibge", "indicador", "ano", "valor"])
        df = df.rename(columns={"esfera": "tipo_ente", "indicador": "tipo_receita"})
        df["fonte"] = fonte
        partes.append(df[_COLUNAS_SAIDA])

    if not partes:
        print("  [CONSOLIDAR] Nenhum CSV encontrado.")
        return pd.DataFrame(columns=_COLUNAS_SAIDA)

    consolidado = (
        pd.concat(partes, ignore_index=True)
        .sort_values(["tipo_ente", "cod_ibge", "tipo_receita", "ano", "fonte"])
        .reset_index(drop=True)
    )
    consolidado.to_csv(CSV_SAIDA, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print(f"\n[CONSOLIDAR] {len(consolidado)} registros -> {CSV_SAIDA}")
    return consolidado
