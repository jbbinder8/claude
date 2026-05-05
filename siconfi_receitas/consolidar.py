"""
consolidar.py — Agrega os CSVs de DCA, RREO, SIOPS e SIOPE em um único arquivo.

Entrada : output/receitas/receitas_{dca,rreo,siops,siope}.csv
Saídas  :
    output/receitas/receitas_consolidadas.csv  — formato longo (uma linha por fonte)
    output/receitas/receitas_pivot.csv         — formato pivotado (uma coluna por fonte)

Colunas de saída (longo):
    tipo_ente    — "Estado" ou "Município"
    cod_ibge     — código IBGE do ente (7 dígitos para municípios)
    tipo_receita — "ICMS", "ISS" ou "Cota-Parte ICMS"
    ano          — exercício
    fonte        — "DCA", "RREO", "SIOPS" ou "SIOPE"
    valor        — receita em reais

Nota: SIOPE usa cod_ibge de 6 dígitos (sem dígito verificador).
No pivô, a correspondência é feita pelos 6 primeiros dígitos; a chave
usada na tabela final é sempre o cod_ibge de 7 dígitos das demais fontes.
"""

from pathlib import Path

import pandas as pd

DIR_RECEITAS = Path("output/receitas")
CSV_SAIDA    = DIR_RECEITAS / "receitas_consolidadas.csv"
CSV_PIVOT    = DIR_RECEITAS / "receitas_pivot.csv"

_FONTES = {
    "DCA"  : DIR_RECEITAS / "receitas_dca.csv",
    "RREO" : DIR_RECEITAS / "receitas_rreo.csv",
    "SIOPS": DIR_RECEITAS / "receitas_siops.csv",
    "SIOPE": DIR_RECEITAS / "receitas_siope.csv",
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
    print(f"[CONSOLIDAR] {len(consolidado)} registros -> {CSV_SAIDA}")

    _pivotar(consolidado)
    return consolidado


def _pivotar(consolidado: pd.DataFrame) -> pd.DataFrame:
    """
    Gera receitas_pivot.csv: uma linha por (tipo_ente, cod_ibge, tipo_receita, ano),
    uma coluna por fonte (DCA, RREO, SIOPS, SIOPE).

    SIOPE fornece cod_ibge de 6 dígitos; os demais usam 7. A normalização
    é feita casando os 6 primeiros dígitos com o cod_ibge de 7 dígitos
    encontrado nas outras fontes. Se não houver correspondência, o código
    de 6 dígitos é mantido como está.
    """
    df = consolidado.copy()
    df["cod_ibge"] = df["cod_ibge"].astype(str)

    # Lookup: 6 primeiros dígitos → cod_ibge completo (7 dígitos), de fontes não-SIOPE
    mask_ref = (df["fonte"] != "SIOPE") & (df["cod_ibge"].str.len() == 7)
    lookup = {v[:6]: v for v in df.loc[mask_ref, "cod_ibge"].unique()}

    # Normaliza registros SIOPE com 6 dígitos para o cod_ibge de 7 dígitos correspondente
    mask_siope6 = (df["fonte"] == "SIOPE") & (df["cod_ibge"].str.len() == 6)
    df.loc[mask_siope6, "cod_ibge"] = df.loc[mask_siope6, "cod_ibge"].map(
        lambda c: lookup.get(c, c)
    )

    pivot = (
        df.pivot_table(
            index=["tipo_ente", "cod_ibge", "tipo_receita", "ano"],
            columns="fonte",
            values="valor",
            aggfunc="first",
        )
        .reset_index()
    )
    pivot.columns.name = None

    for fonte in ["DCA", "RREO", "SIOPS", "SIOPE"]:
        if fonte not in pivot.columns:
            pivot[fonte] = pd.NA

    pivot = (
        pivot[["tipo_ente", "cod_ibge", "tipo_receita", "ano", "DCA", "RREO", "SIOPS", "SIOPE"]]
        .sort_values(["tipo_ente", "cod_ibge", "tipo_receita", "ano"])
        .reset_index(drop=True)
    )

    pivot.to_csv(CSV_PIVOT, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print(f"[CONSOLIDAR] {len(pivot)} linhas (pivô)  -> {CSV_PIVOT}")
    return pivot
