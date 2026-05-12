"""
consolidar.py — Agrega os CSVs de DCA, RREO, SIOPS, SIOPE e DCA2 em um único arquivo.

Entrada : output/receitas/receitas_{dca,rreo,siops,siope}.csv
          output/receitas/receitas_dca_detalhado.csv   (opcional — gera fonte "DCA2")
Saídas  :
    output/receitas/receitas_consolidadas.csv  — formato longo (uma linha por fonte)
    output/receitas/receitas_pivot.csv         — formato pivotado (uma coluna por fonte)

Colunas de saída (longo):
    tipo_ente    — "Estado" ou "Município"
    cod_ibge     — código IBGE do ente (7 dígitos para municípios)
    tipo_receita — "ICMS", "ISS", "Cota-Parte ICMS" ou "LC194"
    ano          — exercício
    fonte        — "DCA", "RREO", "SIOPS", "SIOPE" ou "DCA2"
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
CSV_DCA2     = DIR_RECEITAS / "receitas_dca_detalhado.csv"

_FONTES = {
    "DCA"  : DIR_RECEITAS / "receitas_dca.csv",
    "RREO" : DIR_RECEITAS / "receitas_rreo.csv",
    "SIOPS": DIR_RECEITAS / "receitas_siops.csv",
    "SIOPE": DIR_RECEITAS / "receitas_siope.csv",
}

_COLUNAS_SAIDA = ["tipo_ente", "cod_ibge", "tipo_receita", "ano", "fonte", "valor"]

_COLUNAS_ENTRADA = ["esfera", "cod_ibge", "indicador", "ano", "valor"]

# Termos de cada tipo_receita calculado a partir do DCA detalhado (wide):
#   (coluna, sinal)  →  valor += sinal * abs(coluna)
_FORMULAS_DCA2 = {
    "ICMS": [
        ("e_icms_rbr", +1), ("e_icms_odr", -1),
        ("e_adicional_icms_fcp_rbr", +1), ("e_adicional_icms_fcp_odr", -1),
    ],
    "LC194": [
        ("e_comp_lc194_rbr", +1), ("e_comp_lc194_odr", -1),
        ("m_comp_lc194_mun_rbr", +1), ("m_comp_lc194_mun_odr", -1),
        ("m_cota_parte_comp_lc194_rbr", +1), ("m_cota_parte_comp_lc194_odr", -1),
    ],
    "ISS": [
        ("m_iss_rbr", +1), ("m_iss_odr", -1),
        ("m_adicional_iss_fcp_rbr", +1), ("m_adicional_iss_fcp_odr", -1),
    ],
    "Cota-Parte ICMS": [
        ("m_cota_parte_icms_rbr", +1), ("m_cota_parte_icms_odr", -1),
    ],
}


def _calcular_tipo_dca2(df: pd.DataFrame, tipo_receita: str, termos: list) -> pd.DataFrame:
    """
    A partir do DCA detalhado (wide), calcula um tipo_receita para fonte DCA2.
    Inclui apenas linhas com pelo menos um valor não-NaN nos termos da fórmula,
    evitando gerar linhas artificialmente zeradas para esferas sem aquela rubrica.
    """
    tem_dado = pd.Series(False, index=df.index)
    for col, _ in termos:
        if col in df.columns:
            tem_dado |= df[col].notna()

    df_sub = df.loc[tem_dado].copy()
    if df_sub.empty:
        return pd.DataFrame(columns=_COLUNAS_SAIDA)

    valor = pd.Series(0.0, index=df_sub.index)
    for col, sinal in termos:
        if col in df_sub.columns:
            valor = valor + sinal * df_sub[col].fillna(0).abs()

    df_out = df_sub[["esfera", "cod_ibge", "ano"]].copy()
    df_out = df_out.rename(columns={"esfera": "tipo_ente"})
    df_out["tipo_receita"] = tipo_receita
    df_out["fonte"] = "DCA2"
    df_out["valor"] = valor.values
    return df_out[_COLUNAS_SAIDA]


def _carregar_dca2() -> pd.DataFrame:
    """
    Lê receitas_dca_detalhado.csv (formato wide) e retorna DataFrame no formato longo
    com fonte="DCA2". Retorna DataFrame vazio se o arquivo não existir ou der erro.
    """
    if not CSV_DCA2.exists():
        return pd.DataFrame(columns=_COLUNAS_SAIDA)
    try:
        df = pd.read_csv(CSV_DCA2, sep=";", decimal=",")
    except Exception as exc:
        print(f"  [CONSOLIDAR] Erro ao ler {CSV_DCA2}: {exc} — pulando DCA2.")
        return pd.DataFrame(columns=_COLUNAS_SAIDA)

    partes = [
        _calcular_tipo_dca2(df, tipo, termos)
        for tipo, termos in _FORMULAS_DCA2.items()
    ]
    return pd.concat(partes, ignore_index=True)


def consolidar() -> pd.DataFrame:
    """
    Lê os CSVs de receitas, seleciona e renomeia as colunas relevantes,
    concatena e grava o arquivo consolidado.
    Retorna o DataFrame consolidado.

    Robustez:
      - Valida que cada CSV contém as colunas esperadas antes de usar usecols
        (evita ValueError se o arquivo foi gerado por uma versão anterior do schema).
      - Deduplica por chave natural após concatenação, tolerando duplicatas
        residuais causadas por queda entre salvar_csv e gravar_checkpoint.
      - Inclui fonte "DCA2" se receitas_dca_detalhado.csv existir.
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

    dca2 = _carregar_dca2()
    if not dca2.empty:
        partes.append(dca2)
        print(f"  [CONSOLIDAR] {len(dca2)} registros DCA2 carregados de {CSV_DCA2.name}")

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
    uma coluna por fonte (DCA, RREO, SIOPS, SIOPE, DCA2).

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

    for fonte in ["DCA", "RREO", "SIOPS", "SIOPE", "DCA2"]:
        if fonte not in pivot.columns:
            pivot[fonte] = pd.NA

    pivot = (
        pivot[["tipo_ente", "cod_ibge", "tipo_receita", "ano", "DCA", "RREO", "SIOPS", "SIOPE", "DCA2"]]
        .sort_values(["tipo_ente", "cod_ibge", "tipo_receita", "ano"])
        .reset_index(drop=True)
    )

    pivot.to_csv(CSV_PIVOT, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print(f"[CONSOLIDAR] {len(pivot)} linhas (pivô)  -> {CSV_PIVOT}")
    return pivot
