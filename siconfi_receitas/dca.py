"""
dca.py — Módulo DCA (SICONFI / DCA-Anexo I-C, Balanço Orçamentário de Receitas).

Extrai:
  • ICMS                — estados
  • ISS                 — municípios
  • Cota-Parte do ICMS  — municípios

Coluna alvo: "Receitas Brutas Realizadas"
Período    : 2019-2025
Saída      : output/dca/receitas_dca.csv
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from .common import (
    ANOS, MAX_WORKERS, SALVAR_A_CADA,
    paginar, obter_entes,
    ler_checkpoint, gravar_checkpoint, ler_csv, salvar_csv, imprimir_resumo,
)

# ---------------------------------------------------------------------------
# Configurações do módulo
# ---------------------------------------------------------------------------

DIR_SAIDA  = Path("output/receitas")
CHECKPOINT = DIR_SAIDA / "checkpoint_dca.json"
CSV_SAIDA  = DIR_SAIDA / "receitas_dca.csv"

COLUNA_ALVO = "Receitas Brutas Realizadas"

# Mudança de plano de contas em 2022
_CONTAS_E_ANTES  = {"RO1.1.1.8.02.1.0": "ICMS"}
_CONTAS_E_DEPOIS = {"RO1.1.1.4.50.1.0": "ICMS"}
_CONTAS_M_ANTES  = {"RO1.1.1.8.02.3.0": "ISS", "RO1.7.2.8.01.1.0": "Cota-Parte ICMS"}
_CONTAS_M_DEPOIS = {"RO1.1.1.4.51.1.0": "ISS", "RO1.7.2.1.50.0.0": "Cota-Parte ICMS"}


def _contas_por_ano(esfera: str, ano: int) -> dict:
    if esfera == "E":
        return _CONTAS_E_ANTES if ano <= 2021 else _CONTAS_E_DEPOIS
    return _CONTAS_M_ANTES if ano <= 2021 else _CONTAS_M_DEPOIS


# ---------------------------------------------------------------------------
# Busca por ente/ano
# ---------------------------------------------------------------------------

def _buscar(cod_ibge: int, ano: int, esfera: str) -> list:
    contas_alvo = _contas_por_ano(esfera, ano)
    items = paginar("dca", {
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
                "esfera"   : "Estado" if esfera == "E" else "Município",
                "co_uf"    : item.get("uf", ""),
                "cod_ibge" : cod_ibge,
                "no_ente"  : item.get("instituicao", ""),
                "ano"      : ano,
                "indicador": contas_alvo[cod_conta],
                "cod_conta": cod_conta,
                "conta"    : item.get("conta", ""),
                "valor"    : item.get("valor") or 0,
                "populacao": item.get("populacao") or 0,
            })
    return resultados


# ---------------------------------------------------------------------------
# Ponto de entrada do módulo
# ---------------------------------------------------------------------------

def baixar(entes_df=None) -> list:
    """
    Executa o download completo do DCA para todos os entes e anos.
    Aceita entes_df pré-carregado para evitar chamada duplicada ao orquestrador.
    Retorna lista de registros.
    """
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    feitos = ler_checkpoint(CHECKPOINT)
    linhas: list = ler_csv(CSV_SAIDA)
    n_novos = 0

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
    print(f"\n[DCA] Total: {total} | Já feitos: {total - pendentes} | Pendentes: {pendentes}")
    concluidos = total - pendentes

    def _processar(args):
        cod_ibge, ano, esfera, no_ente, uf, chave = args
        return chave, _buscar(cod_ibge, ano, esfera), no_ente, uf, ano

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {executor.submit(_processar, t): t for t in tarefas}
        with tqdm(total=pendentes, desc="DCA", unit="req", disable=not tarefas) as pbar:
            for futuro in as_completed(futuros):
                try:
                    chave, resultado, no_ente, uf, ano = futuro.result()
                except Exception as exc:
                    tqdm.write(f"  [DCA] Erro: {exc}")
                    continue

                linhas.extend(resultado)
                feitos.add(chave)
                n_novos += 1

                pbar.set_postfix(uf=uf, ente=no_ente[:20], ano=ano, n=len(resultado))
                pbar.update(1)

                if n_novos % SALVAR_A_CADA == 0:
                    gravar_checkpoint(CHECKPOINT, feitos)
                    salvar_csv(CSV_SAIDA, linhas)

    gravar_checkpoint(CHECKPOINT, feitos)
    salvar_csv(CSV_SAIDA, linhas)
    print(f"\n[DCA] Concluído — {len(linhas)} registros -> {CSV_SAIDA}")
    imprimir_resumo(linhas, "DCA")
    return linhas
