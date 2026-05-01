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

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from .common import (
    ANOS, MAX_WORKERS, SALVAR_A_CADA, IBGE_PARA_ID_ENTE,
    paginar, obter_entes,
    ler_checkpoint, gravar_checkpoint, ler_csv, salvar_csv, imprimir_resumo,
    gravar_log_execucao,
)

# Chave natural de uma linha no CSV — usada para deduplicar ao reler.
_CHAVES_LINHA = ["cod_ibge", "ano", "cod_conta"]

# Mapa de "esfera" (texto salvo no CSV) → código de uma letra (usado nas chaves
# do checkpoint). Permite reconstruir o checkpoint a partir do CSV.
_ESFERA_TXT_PARA_COD = {"Estado": "E", "Município": "M"}

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
    id_ente = IBGE_PARA_ID_ENTE.get(cod_ibge, cod_ibge)
    items = paginar("rreo", {
        "id_ente"              : id_ente,
        "an_exercicio"         : ano,
        "nr_periodo"           : BIMESTRE_ALVO,
        "co_tipo_demonstrativo": "RREO",
    })
    resultados = []
    for item in items:
        cod_conta = item.get("cod_conta", "")
        coluna    = item.get("coluna", "")
        if cod_conta in contas_alvo and coluna == COLUNA_ALVO:
            # `valor` e `populacao` preservam None quando a API não retornou
            # o campo (vira vazio no CSV). Antes usávamos `or 0`, que confundia
            # zero legítimo com ausência. Agora 0 e None são distinguíveis.
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
                "valor"     : item.get("valor"),
                "populacao" : item.get("populacao"),
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

    Robustez: mesma estratégia de dca.py — ver docstring lá para detalhes.
    """
    t_inicio = time.time()
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    feitos = ler_checkpoint(CHECKPOINT)
    linhas: list = ler_csv(CSV_SAIDA, chaves_unicas=_CHAVES_LINHA)
    # Sincroniza checkpoint com CSV (cobre queda entre salvar_csv e gravar_checkpoint).
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
    print(f"\n[RREO] Total: {total} | Já feitos: {total - pendentes} | Pendentes: {pendentes}")

    def _processar(args):
        cod_ibge, ano, esfera, no_ente, uf, chave = args
        return chave, _buscar(cod_ibge, ano, esfera), no_ente, uf, ano

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {executor.submit(_processar, t): t for t in tarefas}
        with tqdm(total=pendentes, desc="RREO", unit="req", disable=not tarefas) as pbar:
            for futuro in as_completed(futuros):
                try:
                    chave, resultado, no_ente, uf, ano = futuro.result()
                except Exception as exc:
                    # NÃO adiciona à `feitos`: a tarefa será re-tentada.
                    tqdm.write(f"  [RREO] Erro: {exc}")
                    n_erros += 1
                    pbar.update(1)
                    continue

                linhas.extend(resultado)
                feitos.add(chave)
                n_novos += 1

                pbar.set_postfix(uf=uf, ente=no_ente[:20], ano=ano, n=len(resultado))
                pbar.update(1)

                if n_novos % SALVAR_A_CADA == 0:
                    salvar_csv(CSV_SAIDA, linhas)
                    gravar_checkpoint(CHECKPOINT, feitos)

    salvar_csv(CSV_SAIDA, linhas)
    gravar_checkpoint(CHECKPOINT, feitos)
    gravar_log_execucao("RREO", t_inicio, len(linhas), n_erros)
    err_str = f" | erros: {n_erros}" if n_erros else ""
    print(f"\n[RREO] Concluído — {len(linhas)} registros{err_str} -> {CSV_SAIDA}")
    imprimir_resumo(linhas, "RREO")
    return linhas
