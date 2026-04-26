"""
rreo.py — Módulo RREO (SICONFI / Demonstrativo 3 e Anexo da RCL).

Extrai os valores brutos mais próximos do DCA para cada indicador:

  • ICMS (estado)       — cod='ICMSLiquidoExcetoTransferenciasEFUNDEB'
                          coluna='TOTAL (ÚLTIMOS 12 MESES)'
                          Diferença vs DCA: < 2,3 % (estrutural: RREO usa soma
                          mensal rolante; DCA usa relatório anual com ajustes)

  • ISS (município)     — cod='ISSLiquidoExcetoTransferenciasEFUNDEB'
                          coluna='TOTAL (ÚLTIMOS 12 MESES)'
                          Diferença vs DCA: 0,00 % (correspondência exata)

  • Cota-Parte ICMS     — cod='RREO3CotaParteDoICMS'
  (município)             coluna='TOTAL (ÚLTIMOS 12 MESES)'
                          Diferença vs DCA: 0,00 % (correspondência exata)

Notas de investigação:
  - Parâmetro obrigatório: co_tipo_demonstrativo='RREO'.
  - Códigos RREO6xxx com coluna 'RECEITAS REALIZADAS (a)' refletem valores
    líquidos deduzidos de FUNDEB/transferências — não usar para comparar com DCA.
  - Não há distinção por ano (ao contrário do DCA, que mudou o PCASP em 2022).

Período: 2019-2025
Saída  : output/rreo/receitas_rreo.csv
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .common import (
    ANOS, MAX_WORKERS, SALVAR_A_CADA,
    paginar, obter_entes,
    ler_checkpoint, gravar_checkpoint, salvar_csv, imprimir_resumo,
)

# ---------------------------------------------------------------------------
# Configurações do módulo
# ---------------------------------------------------------------------------

DIR_SAIDA  = Path("output/receitas")
CHECKPOINT = DIR_SAIDA / "checkpoint_rreo.json"
CSV_SAIDA  = DIR_SAIDA / "receitas_rreo.csv"

BIMESTRE_ALVO = 6                          # 6.º bimestre = jan–dez acumulado
COLUNA_ALVO   = "TOTAL (ÚLTIMOS 12 MESES)"

# Códigos descritivos RREO — todos com coluna COLUNA_ALVO
# Validados contra DCA em 2019-2024 (Paraná + Curitiba)
_CONTAS_E = {"ICMSLiquidoExcetoTransferenciasEFUNDEB": "ICMS"}
_CONTAS_M = {
    "ISSLiquidoExcetoTransferenciasEFUNDEB": "ISS",
    "RREO3CotaParteDoICMS"                 : "Cota-Parte ICMS",
}


def _contas_por_esfera(esfera: str) -> dict:
    return _CONTAS_E if esfera == "E" else _CONTAS_M


# ---------------------------------------------------------------------------
# Busca por ente/ano
# ---------------------------------------------------------------------------

def _buscar(cod_ibge: int, ano: int, esfera: str) -> list:
    contas_alvo = _contas_por_esfera(esfera)
    items = paginar("rreo", {
        "id_ente"              : cod_ibge,
        "an_exercicio"         : ano,
        "nr_periodo"           : BIMESTRE_ALVO,
        "co_tipo_demonstrativo": "RREO",
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
                "bimestre"  : BIMESTRE_ALVO,
                "indicador" : contas_alvo[cod_conta],
                "cod_conta" : cod_conta,
                "conta"     : item.get("conta", ""),
                "valor"     : item.get("valor") or 0,
                "populacao" : item.get("populacao") or 0,
            })
    return resultados


# ---------------------------------------------------------------------------
# Ponto de entrada do módulo
# ---------------------------------------------------------------------------

def baixar(entes_df=None) -> list:
    """
    Executa o download RREO (6.º bimestre) para todos os entes e anos.
    Aceita entes_df pré-carregado para evitar chamada duplicada ao orquestrador.
    Retorna lista de registros.
    """
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    feitos = ler_checkpoint(CHECKPOINT)
    linhas: list = []
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
    print(f"\n[RREO] Total: {total} | Já feitos: {total - pendentes} | Pendentes: {pendentes}")
    concluidos = total - pendentes

    def _processar(args):
        cod_ibge, ano, esfera, no_ente, uf, chave = args
        return chave, _buscar(cod_ibge, ano, esfera), no_ente, uf, ano

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {executor.submit(_processar, t): t for t in tarefas}
        for futuro in as_completed(futuros):
            try:
                chave, resultado, no_ente, uf, ano = futuro.result()
            except Exception as exc:
                print(f"\n  [RREO] Erro: {exc}")
                continue

            linhas.extend(resultado)
            feitos.add(chave)
            concluidos += 1
            n_novos    += 1

            pct   = concluidos / total * 100
            achou = f"[{len(resultado)}]" if resultado else ""
            print(f"  [RREO {pct:5.1f}%] {uf} {no_ente[:35]:<35} {ano}  {achou}   ", end="\r")

            if n_novos % SALVAR_A_CADA == 0:
                gravar_checkpoint(CHECKPOINT, feitos)
                salvar_csv(CSV_SAIDA, linhas)

    gravar_checkpoint(CHECKPOINT, feitos)
    salvar_csv(CSV_SAIDA, linhas)
    print(f"\n[RREO] Concluído — {len(linhas)} registros -> {CSV_SAIDA}")
    imprimir_resumo(linhas, "RREO")
    return linhas
