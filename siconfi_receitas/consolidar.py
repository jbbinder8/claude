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


_COLUNAS_ENTRADA = ["esfera", "cod_ibge", "indicador", "ano", "valor"]


def consolidar() -> pd.DataFrame:
    """
    Lê os três CSVs de receitas, seleciona e renomeia as colunas relevantes,
    concatena e grava o arquivo consolidado.
    Retorna o DataFrame consolidado.

    Robustez:
      - Valida que cada CSV contém as colunas esperadas antes de usar usecols
        (evita ValueError se o arquivo foi gerado por uma versão anterior do schema).
      - Deduplica por chave natural após concatenação, tolerando duplicatas
        residuais causadas por queda entre salvar_csv e gravar_checkpoint.
    """
    partes = []
    for fonte, caminho in _FONTES.items():
        if not caminho.exists():
            print(f"  [CONSOLIDAR] {caminho} não encontrado — pulando {fonte}.")
            continue
        try:
            df_raw = pd.read_csv(caminho, sep=";", decimal=",")
        except Exception as exc:
            print(f"  [CONSOLIDAR] Erro ao ler {caminho}: {exc} — pulando {fonte}.")
            continue
        faltantes = [c for c in _COLUNAS_ENTRADA if c not in df_raw.columns]
        if faltantes:
            print(f"  [CONSOLIDAR] {caminho} sem colunas {faltantes} "
                  f"(colunas presentes: {list(df_raw.columns)}) — pulando {fonte}.")
            continue
        df = df_raw[_COLUNAS_ENTRADA].copy()
        df = df.rename(columns={"esfera": "tipo_ente", "indicador": "tipo_receita"})
        df["fonte"] = fonte
        partes.append(df[_COLUNAS_SAIDA])

    if not partes:
        print("  [CONSOLIDAR] Nenhum CSV encontrado.")
        return pd.DataFrame(columns=_COLUNAS_SAIDA)

    consolidado = (
        pd.concat(partes, ignore_index=True)
        .drop_duplicates(
            subset=["tipo_ente", "cod_ibge", "tipo_receita", "ano", "fonte"],
            keep="last",
        )
        .sort_values(["tipo_ente", "cod_ibge", "tipo_receita", "ano", "fonte"])
        .reset_index(drop=True)
    )
    consolidado.to_csv(CSV_SAIDA, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print(f"\n[CONSOLIDAR] {len(consolidado)} registros -> {CSV_SAIDA}")
    return consolidado
