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

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from .common import (
    ANOS, MAX_WORKERS, SALVAR_A_CADA,
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
            # `valor` e `populacao` preservam None quando a API não retornou
            # o campo (vira vazio no CSV). Antes usávamos `or 0`, que confundia
            # zero legítimo com ausência. Agora 0 e None são distinguíveis.
            resultados.append({
                "esfera"   : "Estado" if esfera == "E" else "Município",
                "co_uf"    : item.get("uf", ""),
                "cod_ibge" : cod_ibge,
                "no_ente"  : item.get("instituicao", ""),
                "ano"      : ano,
                "indicador": contas_alvo[cod_conta],
                "cod_conta": cod_conta,
                "conta"    : item.get("conta", ""),
                "valor"    : item.get("valor"),
                "populacao": item.get("populacao"),
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

    Robustez:
      - Se uma página da API falhar (APIError), a tarefa NÃO é marcada como
        feita: o try/except em volta de futuro.result() faz `continue` sem
        adicionar a chave em `feitos`, e ela será re-tentada na próxima execução.
      - O CSV é gravado ANTES do checkpoint. Se o processo for interrompido
        entre os dois, na próxima execução `feitos` é reconstruído a partir
        do CSV (linhas presentes ⇒ tarefa concluída), e ler_csv() deduplica.
    """
    t_inicio = time.time()
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    feitos = ler_checkpoint(CHECKPOINT)
    linhas: list = ler_csv(CSV_SAIDA, chaves_unicas=_CHAVES_LINHA)
    # Sincroniza checkpoint com CSV: toda linha presente no CSV implica que a
    # tarefa correspondente já foi concluída. Cobre o caso de queda entre
    # salvar_csv e gravar_checkpoint.
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
    print(f"\n[DCA] Total: {total} | Já feitos: {total - pendentes} | Pendentes: {pendentes}")

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
                    # NÃO adiciona à `feitos`: a tarefa será re-tentada.
                    tqdm.write(f"  [DCA] Erro: {exc}")
                    n_erros += 1
                    pbar.update(1)
                    continue

                linhas.extend(resultado)
                feitos.add(chave)
                n_novos += 1

                pbar.set_postfix(uf=uf, ente=no_ente[:20], ano=ano, n=len(resultado))
                pbar.update(1)

                if n_novos % SALVAR_A_CADA == 0:
                    # Ordem: CSV primeiro, checkpoint depois. Em caso de queda
                    # entre as duas escritas, na re-execução o checkpoint é
                    # reconstruído a partir do CSV (acima); pior caso é tarefa
                    # repetida, cujas linhas duplicadas são removidas pelo
                    # ler_csv(chaves_unicas=...). Nunca há perda de dado.
                    salvar_csv(CSV_SAIDA, linhas)
                    gravar_checkpoint(CHECKPOINT, feitos)

    salvar_csv(CSV_SAIDA, linhas)
    gravar_checkpoint(CHECKPOINT, feitos)
    gravar_log_execucao("DCA", t_inicio, len(linhas), n_erros)
    err_str = f" | erros: {n_erros}" if n_erros else ""
    print(f"\n[DCA] Concluído — {len(linhas)} registros{err_str} -> {CSV_SAIDA}")
    imprimir_resumo(linhas, "DCA")
    return linhas
