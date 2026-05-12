"""
dca_detalhado.py — Extração detalhada DCA (SICONFI / DCA-Anexo I-C).

Para cada ente × ano gera UMA linha com todas as rubricas como colunas separadas,
duas colunas por rubrica (Receitas Brutas Realizadas e Outras Deduções da Receita).

Estados — 3 rubricas × 2 = 6 colunas (e_*):
  e_icms_rbr / e_icms_odr
  e_adicional_icms_fcp_rbr / e_adicional_icms_fcp_odr
  e_comp_lc194_rbr / e_comp_lc194_odr

Municípios — 5 rubricas × 2 = 10 colunas (m_*):
  m_iss_rbr / m_iss_odr
  m_adicional_iss_fcp_rbr / m_adicional_iss_fcp_odr
  m_cota_parte_icms_rbr / m_cota_parte_icms_odr
  m_cota_parte_comp_lc194_rbr / m_cota_parte_comp_lc194_odr
  m_comp_lc194_mun_rbr / m_comp_lc194_mun_odr

Rubricas do grupo oposto ficam None (vazio no CSV).

Fontes (NR → cod_conta API com prefixo "RO"):
  Estados:
    ICMS principal       2019-2021: RO1.1.1.8.02.1.0 | 2022-2025: RO1.1.1.4.50.1.0
    Adicional ICMS FCP   2019-2021: RO1.1.1.8.02.2.0 | 2022-2025: RO1.1.1.4.50.2.0
    Comp LC 194/2022     todos: RO1.7.1.9.62.0.0

  Municípios:
    ISS principal        2019-2021: RO1.1.1.8.02.3.0 | 2022-2025: RO1.1.1.4.51.1.0
    Adicional ISS FCP    2019-2021: RO1.1.1.8.02.4.0 | 2022-2025: RO1.1.1.4.51.2.0
    Cota-Parte ICMS      2019-2021: RO1.7.2.8.01.1.0 | 2022-2025: RO1.7.2.1.50.0.0
    Cota-Parte Comp LC194  todos: RO1.7.2.9.53.0.0
    Comp LC 194 (mun)    todos: RO1.7.1.9.62.0.0

Período : 2019-2025
Saída   : output/receitas/receitas_dca_detalhado.csv
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from .common import (
    ANOS, MAX_WORKERS, SALVAR_A_CADA, IBGE_PARA_ID_ENTE,
    paginar, obter_entes,
    ler_checkpoint, gravar_checkpoint, ler_csv, salvar_csv,
    gravar_log_execucao,
)

# ---------------------------------------------------------------------------
# Caminhos de saída
# ---------------------------------------------------------------------------

DIR_SAIDA  = Path("output/receitas")
CHECKPOINT = DIR_SAIDA / "checkpoint_dca_detalhado.json"
CSV_SAIDA  = DIR_SAIDA / "receitas_dca_detalhado.csv"

# ---------------------------------------------------------------------------
# Chave natural de cada linha no CSV (1 linha por ente × ano)
# ---------------------------------------------------------------------------

_CHAVES_LINHA = ["cod_ibge", "ano"]

_ESFERA_TXT_PARA_COD = {"Estado": "E", "Município": "M"}

# ---------------------------------------------------------------------------
# Colunas de valor
# ---------------------------------------------------------------------------

# rbr = Receitas Brutas Realizadas | odr = Outras Deduções da Receita
_COLUNAS_E = [
    "e_icms_rbr", "e_icms_odr",
    "e_adicional_icms_fcp_rbr", "e_adicional_icms_fcp_odr",
    "e_comp_lc194_rbr", "e_comp_lc194_odr",
]
_COLUNAS_M = [
    "m_iss_rbr", "m_iss_odr",
    "m_adicional_iss_fcp_rbr", "m_adicional_iss_fcp_odr",
    "m_cota_parte_icms_rbr", "m_cota_parte_icms_odr",
    "m_cota_parte_comp_lc194_rbr", "m_cota_parte_comp_lc194_odr",
    "m_comp_lc194_mun_rbr", "m_comp_lc194_mun_odr",
]

_SUFIXO_COLUNA = {
    "Receitas Brutas Realizadas": "rbr",
    "Outras Deduções da Receita": "odr",
}

# ---------------------------------------------------------------------------
# Mapeamentos cod_conta → nome interno da rubrica (sem prefixo e_/m_)
# Mudança de plano de contas em 2022; rubricas LC 194 valem todos os anos.
# ---------------------------------------------------------------------------

_CONTAS_E_ANTES = {
    "RO1.1.1.8.02.1.0": "icms",
    "RO1.1.1.8.02.2.0": "adicional_icms_fcp",
}
_CONTAS_E_DEPOIS = {
    "RO1.1.1.4.50.1.0": "icms",
    "RO1.1.1.4.50.2.0": "adicional_icms_fcp",
}
_CONTAS_E_FIXAS = {
    "RO1.7.1.9.62.0.0": "comp_lc194",
}

_CONTAS_M_ANTES = {
    "RO1.1.1.8.02.3.0": "iss",
    "RO1.1.1.8.02.4.0": "adicional_iss_fcp",
    "RO1.7.2.8.01.1.0": "cota_parte_icms",
}
_CONTAS_M_DEPOIS = {
    "RO1.1.1.4.51.1.0": "iss",
    "RO1.1.1.4.51.2.0": "adicional_iss_fcp",
    "RO1.7.2.1.50.0.0": "cota_parte_icms",
}
_CONTAS_M_FIXAS = {
    "RO1.7.2.9.53.0.0": "cota_parte_comp_lc194",
    "RO1.7.1.9.62.0.0": "comp_lc194_mun",
}


def _contas_por_ano(esfera: str, ano: int) -> dict:
    if esfera == "E":
        base = _CONTAS_E_ANTES if ano <= 2021 else _CONTAS_E_DEPOIS
        return {**base, **_CONTAS_E_FIXAS}
    base = _CONTAS_M_ANTES if ano <= 2021 else _CONTAS_M_DEPOIS
    return {**base, **_CONTAS_M_FIXAS}


# ---------------------------------------------------------------------------
# Busca por ente/ano — retorna sempre exatamente uma linha (dict)
# ---------------------------------------------------------------------------

def _buscar(
    cod_ibge: int, ano: int, esfera: str,
    fallback_uf: str = "", fallback_no_ente: str = "",
) -> dict:
    contas_alvo = _contas_por_ano(esfera, ano)
    id_ente = IBGE_PARA_ID_ENTE.get(cod_ibge, cod_ibge)
    items = paginar("dca", {
        "an_exercicio": ano,
        "no_anexo"    : "DCA-Anexo I-C",
        "id_ente"     : id_ente,
    })

    row = {
        "esfera"   : "Estado" if esfera == "E" else "Município",
        "co_uf"    : fallback_uf,    # sobrescrito pela API se disponível
        "cod_ibge" : cod_ibge,
        "no_ente"  : fallback_no_ente,
        "ano"      : ano,
        "populacao": None,
        **{col: None for col in _COLUNAS_E},
        **{col: None for col in _COLUNAS_M},
    }

    _meta_ok = False
    for item in items:
        # Metadados da API têm precedência sobre o fallback (trazem populacao)
        if not _meta_ok and item.get("uf"):
            row["co_uf"]     = item["uf"]
            row["no_ente"]   = item.get("instituicao", fallback_no_ente)
            row["populacao"] = item.get("populacao")
            _meta_ok = True

        cod_conta = item.get("cod_conta", "")
        coluna    = item.get("coluna", "")
        sufixo    = _SUFIXO_COLUNA.get(coluna)
        if cod_conta not in contas_alvo or sufixo is None:
            continue

        rubrica  = contas_alvo[cod_conta]
        col_name = f"{'e' if esfera == 'E' else 'm'}_{rubrica}_{sufixo}"
        if col_name in row:
            row[col_name] = item.get("valor")

    return row


# ---------------------------------------------------------------------------
# Resumo simples (não usa a função genérica que espera formato longo)
# ---------------------------------------------------------------------------

def _imprimir_resumo(linhas: list):
    if not linhas:
        return
    df = pd.DataFrame(linhas)
    n_e = int((df["esfera"] == "Estado").sum())
    n_m = int((df["esfera"] == "Município").sum())
    anos_str = f"{df['ano'].min()}-{df['ano'].max()}" if len(df) else "—"
    print(f"\nResumo DCA Detalhado — {len(df)} registros | Estados: {n_e} | Municípios: {n_m} | Anos: {anos_str}")


# ---------------------------------------------------------------------------
# Ponto de entrada do módulo (autônomo — não chamado pelo main/consolidar)
# ---------------------------------------------------------------------------

def baixar(entes_df=None) -> list:
    """
    Executa o download completo do DCA detalhado para todos os entes e anos.
    Retorna lista de registros no formato wide (uma linha por ente × ano).

    Aceita entes_df pré-carregado; se None, chama obter_entes() internamente.
    """
    t_inicio = time.time()
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    feitos = ler_checkpoint(CHECKPOINT)
    linhas: list = ler_csv(CSV_SAIDA, chaves_unicas=_CHAVES_LINHA)

    # Sincroniza checkpoint com CSV (mesma estratégia do dca.py)
    for ln in linhas:
        esfera_cod = _ESFERA_TXT_PARA_COD.get(ln.get("esfera"))
        if esfera_cod and ln.get("cod_ibge") is not None and ln.get("ano") is not None:
            feitos.add(f"{esfera_cod}_{ln['cod_ibge']}_{ln['ano']}")

    n_novos = 0
    n_erros = 0

    if entes_df is None:
        entes_df = obter_entes()

    tarefas = []
    for _, row in entes_df.iterrows():
        for ano in ANOS:
            chave = f"{row['esfera']}_{row['cod_ibge']}_{ano}"
            if chave not in feitos:
                tarefas.append((
                    row["cod_ibge"], ano, row["esfera"],
                    row.get("ente", ""), row.get("uf", ""), chave,
                ))

    total     = len(entes_df) * len(ANOS)
    pendentes = len(tarefas)
    print(f"\n[DCA-DET] Total: {total} | Já feitos: {total - pendentes} | Pendentes: {pendentes}")

    def _processar(args):
        cod_ibge, ano, esfera, no_ente, uf, chave = args
        return chave, _buscar(cod_ibge, ano, esfera, fallback_uf=uf, fallback_no_ente=no_ente), no_ente, uf, ano

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {executor.submit(_processar, t): t for t in tarefas}
        with tqdm(total=pendentes, desc="DCA-DET", unit="req", disable=not tarefas) as pbar:
            for futuro in as_completed(futuros):
                try:
                    chave, resultado, no_ente, uf, ano = futuro.result()
                except Exception as exc:
                    tqdm.write(f"  [DCA-DET] Erro: {exc}")
                    n_erros += 1
                    pbar.update(1)
                    continue

                val_cols = _COLUNAS_E if resultado["esfera"] == "Estado" else _COLUNAS_M
                if any(resultado.get(c) is not None for c in val_cols):
                    linhas.append(resultado)
                feitos.add(chave)
                n_novos += 1

                pbar.set_postfix(uf=uf, ente=no_ente[:20], ano=ano)
                pbar.update(1)

                if n_novos % SALVAR_A_CADA == 0:
                    salvar_csv(CSV_SAIDA, linhas)
                    gravar_checkpoint(CHECKPOINT, feitos)

    salvar_csv(CSV_SAIDA, linhas)
    gravar_checkpoint(CHECKPOINT, feitos)
    gravar_log_execucao("DCA-DET", t_inicio, len(linhas), n_erros)
    err_str = f" | erros: {n_erros}" if n_erros else ""
    print(f"\n[DCA-DET] Concluído — {len(linhas)} registros{err_str} -> {CSV_SAIDA}")
    _imprimir_resumo(linhas)
    return linhas


# ---------------------------------------------------------------------------
# Execução direta:  python -m siconfi_receitas.dca_detalhado
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    baixar()
