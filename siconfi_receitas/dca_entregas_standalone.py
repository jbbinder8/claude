"""
dca_entregas_standalone.py — Datas de entrega da DCA (Balanço Anual) por município × exercício.

Fonte: SICONFI / endpoint `extrato_relatorios`
    GET https://apidatalake.tesouro.gov.br/ords/siconfi/tt/extrato_relatorios
        ?id_ente={cod_ibge}&an_exercicio={ano}
    Filtro: cod_demonstrativo == "QDCC"  (Balanço Anual — DCA)

LIMITAÇÃO DA API: só é publicada a VERSÃO VIGENTE de cada declaração.
  - status "HO" (homologada)  → data = entrega original (nunca retificada)
  - status "RE" (retificada)  → data = ÚLTIMA retificação; a data da entrega
                                original e o nº de retificações NÃO são expostos.
  - sem registro              → DCA não entregue (até a data da consulta)

Prazo legal (LRF art. 51, §1º, I): municípios enviam até 30/04 do ano seguinte.
As datas da API estão em UTC; convertidas para horário de Brasília (UTC-3,
sem horário de verão desde 2019) antes de comparar com o prazo.

Saída:
  output/receitas/dca_entregas.csv   (1 linha por município × exercício)
  output/receitas/dca_entregas.xlsx  (dados + resumos por ano e por UF)

Uso:
  python -m siconfi_receitas.dca_entregas_standalone            # via módulo
  python siconfi_receitas/dca_entregas_standalone.py            # execução direta
  python -m siconfi_receitas.dca_entregas_standalone --teste    # teste (5 municípios do PR)

Retomada: se interrompido, basta rodar de novo — pares (município, ano) já
gravados no CSV não são consultados novamente.
"""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

# Bypassa proxy corporativo para a API do Tesouro (precisa vir antes das requisições)
_np = os.environ.get("NO_PROXY", "")
if "apidatalake.tesouro.gov.br" not in _np:
    os.environ["NO_PROXY"] = ",".join(x for x in (_np, "apidatalake.tesouro.gov.br") if x)

import pandas as pd
from tqdm import tqdm

try:
    from .common import ANOS, IBGE_PARA_ID_ENTE, paginar, obter_entes
except (ImportError, ValueError):
    from common import ANOS, IBGE_PARA_ID_ENTE, paginar, obter_entes

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

DIR_SAIDA   = Path("output/receitas")
CSV_SAIDA   = DIR_SAIDA / "dca_entregas.csv"
XLSX_SAIDA  = DIR_SAIDA / "dca_entregas.xlsx"

MAX_WORKERS   = 4   # 8 provocou muitos HTTP 429 (rate limit) na API do Tesouro
SALVAR_A_CADA = 500

COD_DCA = "QDCC"
FUSO_BRASILIA = timedelta(hours=-3)

COLS = [
    "cod_ibge", "uf", "municipio", "ano",
    "entregue", "status", "retificada",
    "data_versao_atual", "prazo_legal", "dias_apos_prazo", "entregue_no_prazo",
    "orgao", "n_registros_dca", "data_consulta",
]
CHAVE = ["cod_ibge", "ano"]

_MUNICIPIOS_TESTE = [4106902, 4113700, 4115200, 4119905, 4104808]  # Curitiba, Londrina, Maringá, Ponta Grossa, Cascavel


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------

def _para_brasilia(iso_utc: str | None) -> datetime | None:
    if not iso_utc:
        return None
    dt = datetime.strptime(iso_utc.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
    return dt + FUSO_BRASILIA


def _buscar(cod_ibge: int, uf: str, municipio: str, ano: int, hoje: str) -> dict:
    id_ente = IBGE_PARA_ID_ENTE.get(cod_ibge, cod_ibge)
    items = paginar("extrato_relatorios", {"id_ente": id_ente, "an_exercicio": ano})
    dcas = [i for i in items if i.get("cod_demonstrativo") == COD_DCA]

    prazo = date(ano + 1, 4, 30)
    row = {
        "cod_ibge": cod_ibge, "uf": uf, "municipio": municipio, "ano": ano,
        "entregue": False, "status": None, "retificada": None,
        "data_versao_atual": None, "prazo_legal": prazo.isoformat(),
        "dias_apos_prazo": None, "entregue_no_prazo": None,
        "orgao": None, "n_registros_dca": len(dcas), "data_consulta": hoje,
    }
    if not dcas:
        return row

    # Normalmente há 1 registro; se houver mais, fica o mais recente.
    atual = max(dcas, key=lambda i: i.get("data") or "")
    dt = _para_brasilia(atual.get("data"))
    status = atual.get("status")
    row.update({
        "entregue": True,
        "status": status,
        "retificada": status == "RE",
        "data_versao_atual": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None,
        "dias_apos_prazo": (dt.date() - prazo).days if dt else None,
        # Só é possível afirmar se a entrega original foi no prazo quando
        # nunca houve retificação (HO); em RE a data original é desconhecida.
        "entregue_no_prazo": (dt.date() <= prazo) if (dt and status == "HO") else None,
        "orgao": atual.get("orgao"),
    })
    return row


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def _ler_existente() -> list[dict]:
    if not CSV_SAIDA.exists():
        return []
    df = pd.read_csv(CSV_SAIDA, sep=";", decimal=",", dtype={"cod_ibge": "int64", "ano": "int64"})
    return df.drop_duplicates(subset=CHAVE, keep="last").to_dict("records")


def _salvar_csv(linhas: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(linhas, columns=COLS).drop_duplicates(subset=CHAVE, keep="last")
    df = df.sort_values(["uf", "cod_ibge", "ano"])
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    tmp = CSV_SAIDA.with_suffix(".csv.tmp")
    df.to_csv(tmp, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    tmp.replace(CSV_SAIDA)
    return df


def _resumo(df: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    g = df.groupby(por)
    r = pd.DataFrame({
        "municipios": g.size(),
        "entregues": g["entregue"].sum(),
        "nao_entregues": g["entregue"].apply(lambda s: int((~s.astype(bool)).sum())),
        "homologadas_HO": g["status"].apply(lambda s: int((s == "HO").sum())),
        "retificadas_RE": g["status"].apply(lambda s: int((s == "RE").sum())),
        "HO_no_prazo": g["entregue_no_prazo"].apply(lambda s: int((s == True).sum())),   # noqa: E712
        "HO_fora_prazo": g["entregue_no_prazo"].apply(lambda s: int((s == False).sum())),  # noqa: E712
    })
    r["pct_entregues"] = (100 * r.entregues / r.municipios).round(2)
    r["pct_retificadas_s_entregues"] = (100 * r.retificadas_RE / r.entregues.where(r.entregues > 0)).round(2)
    return r.reset_index()


def _salvar_xlsx(df: pd.DataFrame) -> None:
    df = df.copy()
    df["entregue"] = df["entregue"].astype(bool)
    with pd.ExcelWriter(XLSX_SAIDA) as w:
        df.to_excel(w, sheet_name="dca_entregas", index=False)
        _resumo(df, ["ano"]).to_excel(w, sheet_name="resumo_ano", index=False)
        _resumo(df, ["uf", "ano"]).to_excel(w, sheet_name="resumo_uf_ano", index=False)
        pd.DataFrame({"nota": [
            "Fonte: SICONFI/STN, endpoint extrato_relatorios (cod_demonstrativo = QDCC - Balanço Anual DCA).",
            "A API publica apenas a versão vigente de cada DCA.",
            "status HO = homologada, nunca retificada: data_versao_atual = data da entrega original.",
            "status RE = retificada: data_versao_atual = data da ÚLTIMA retificação; data original e nº de retificações não disponíveis.",
            "entregue = False: sem DCA homologada para o exercício na data da consulta.",
            "prazo_legal = 30/04 do ano seguinte (LRF art. 51). Datas convertidas de UTC para horário de Brasília (UTC-3).",
            "dias_apos_prazo > 0 indica data posterior ao prazo (para RE, refere-se à data da retificação).",
            "entregue_no_prazo só é preenchido para status HO.",
            "Brasília (5300108) é consultada com id_ente=53 (convenção do SICONFI).",
        ]}).to_excel(w, sheet_name="notas", index=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def baixar(entes_df: pd.DataFrame | None = None, teste: bool = False) -> pd.DataFrame:
    t0 = time.time()
    hoje = date.today().isoformat()

    if entes_df is None:
        if teste:
            entes_df = pd.DataFrame({"cod_ibge": _MUNICIPIOS_TESTE, "uf": "PR",
                                     "ente": ["Curitiba", "Londrina", "Maringá", "Ponta Grossa", "Cascavel"],
                                     "esfera": "M"})
        else:
            entes_df = obter_entes()
    mun = entes_df[entes_df["esfera"] == "M"].copy()

    linhas = _ler_existente()
    feitos = {(int(l["cod_ibge"]), int(l["ano"])) for l in linhas}

    tarefas = [
        (int(r.cod_ibge), str(r.uf), str(r.ente), ano)
        for r in mun.itertuples() for ano in ANOS
        if (int(r.cod_ibge), ano) not in feitos
    ]
    total = len(mun) * len(ANOS)
    print(f"\n[DCA-ENTREGAS] Municípios: {len(mun)} | Anos: {ANOS[0]}-{ANOS[-1]} | "
          f"Total: {total} | Já feitos: {total - len(tarefas)} | Pendentes: {len(tarefas)}")

    erros = 0
    novos = 0
    if tarefas:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
            futs = {exe.submit(_buscar, *t, hoje): t for t in tarefas}
            with tqdm(total=len(tarefas), desc="DCA-ENTREGAS", unit="req") as pbar:
                for fut in as_completed(futs):
                    t = futs[fut]
                    try:
                        linhas.append(fut.result())
                        novos += 1
                    except Exception as exc:
                        erros += 1
                        tqdm.write(f"  [ERRO] {t} -> {exc}")
                    pbar.update(1)
                    if novos and novos % SALVAR_A_CADA == 0:
                        _salvar_csv(linhas)

    df = _salvar_csv(linhas)
    _salvar_xlsx(df)

    print(f"\n[DCA-ENTREGAS] Concluído — {len(df)} linhas | novos: {novos} | erros: {erros} | "
          f"{(time.time() - t0) / 60:.1f} min")
    print(f"  {CSV_SAIDA}\n  {XLSX_SAIDA}")
    if erros:
        print("  Há erros: rode novamente para tentar só os pendentes.")
    print("\nResumo por ano:")
    print(_resumo(df.assign(entregue=df["entregue"].astype(bool)), ["ano"]).to_string(index=False))
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Datas de entrega da DCA por município (SICONFI)")
    ap.add_argument("--teste", action="store_true", help="roda só 5 municípios do PR")
    args = ap.parse_args()
    if args.teste:
        DIR_SAIDA = Path("output/receitas/teste")  # noqa: F811
        CSV_SAIDA = DIR_SAIDA / "dca_entregas.csv"
        XLSX_SAIDA = DIR_SAIDA / "dca_entregas.xlsx"
    baixar(teste=args.teste)
