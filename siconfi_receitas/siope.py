"""Módulo SIOPE — Receitas de municípios via API FNDE/SIOPE.

Extrai ISS e Cota-Parte ICMS por UF×ano para todos os municípios.
Scope: municípios apenas.

Plano de contas muda a cada geração:
  2019-2020  formato com vírgulas; ISS é composto por múltiplos códigos
             (principal + multas/juros + dívida ativa) que são somados
             por município antes de retornar — mesma metodologia do DCA.
  2021-2022  ISS=11180230  Cota=17280110  (8 dígitos, série 118/172)
  2023+      ISS=11145110  Cota=17215000  (8 dígitos, série 114/172)

Nota: COD_MUNI retornado pela API é o código IBGE de 6 dígitos
(sem o dígito verificador). Os demais módulos usam 7 dígitos.
"""

from __future__ import annotations

import io
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

from . import common
from .common import (
    ANOS,
    ler_checkpoint, gravar_checkpoint, ler_csv, salvar_csv,
    imprimir_resumo, gravar_log_execucao,
)

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
DIR_SAIDA  = Path("output/receitas")
CHECKPOINT = DIR_SAIDA / "checkpoint_siope.json"
CSV_SAIDA  = DIR_SAIDA / "receitas_siope.csv"

_BASE_URL = (
    "https://www.fnde.gov.br/olinda-ide/servico/DADOS_ABERTOS_SIOPE"
    "/versao/v1/odata/"
    "Receita_Siope(Ano_Consulta=@Ano_Consulta,Num_Peri=@Num_Peri,Sig_UF=@Sig_UF)"
)
_PERIODO = 6  # bimestre anual

# Plano de contas por geração
#
# 2019-2020: múltiplos códigos compõem o ISS total (mesmo critério do DCA).
#   O código principal (4,11,13,05,00,00) captura só o ISS bruto; para
#   igualar o DCA é preciso somar também multas, juros e dívida ativa.
#   Como os códigos contêm vírgulas, o filtro OData no servidor falha —
#   a filtragem é feita em Python após busca geral (url_contas=None).
#   Após coletar as linhas individuais, _buscar() agrega por município.
_CONTAS_2019_2020 = {
    "4,11,13,05,00,00": "ISS",   # ISS principal
    "4,19,11,40,00,00": "ISS",   # Multas e Juros de Mora sobre ISS
    "4,19,13,13,00,00": "ISS",   # Multas e Juros de Mora da Dívida Ativa sobre ISS
    "4,19,31,13,00,00": "ISS",   # Dívida Ativa de ISS
    "4,17,22,01,01,00": "Cota-Parte ICMS",
}
# Código sintético gravado no CSV para o ISS agregado de 2019-2020
# (usado na chave de deduplicação no lugar dos múltiplos códigos-fonte)
_COD_ISS_AGREGADO_2019_2020 = "4,11,13,05,agregado"

_CONTAS_2021_2022 = {
    "11180230": "ISS",
    "17280110": "Cota-Parte ICMS",
}
_CONTAS_2023_PLUS = {
    "11145110": "ISS",
    "17215000": "Cota-Parte ICMS",
}


def _contas_por_ano(ano: int) -> dict:
    if ano <= 2020:
        return _CONTAS_2019_2020
    if ano <= 2022:
        return _CONTAS_2021_2022
    return _CONTAS_2023_PLUS

_UF_LIST = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]

# Chave natural de uma linha no CSV (cod_ibge aqui é 6 dígitos)
_CHAVES_LINHA = ["cod_ibge", "ano", "cod_conta"]

_MAX_WORKERS   = 4
_SALVAR_A_CADA = 27   # ~1 rodada de UFs
_PAUSA         = 0.3  # segundos de espera dentro de cada worker após a requisição

# ---------------------------------------------------------------------------
# Sessão HTTP dedicada (SIOPE retorna CSV, não JSON)
# ---------------------------------------------------------------------------
_thread_local = threading.local()


def _get_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        adapter = HTTPAdapter(
            max_retries=Retry(
                total=3,
                backoff_factor=2,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            )
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _thread_local.session = s
    return s


# ---------------------------------------------------------------------------
# Consulta única: UF × ano → lista de registros
# ---------------------------------------------------------------------------
def _construir_url(sig_uf: str, ano: int, contas: dict | None) -> str:
    """
    Monta a URL de consulta.

    Quando `contas` é None, omite o filtro por COD_EXIB_FORMATADO — necessário
    para 2019-2020, cujos códigos contêm vírgulas que o servidor OData interpreta
    como separadores e ignora o filtro. Nesses anos a filtragem é feita em Python.
    """
    if contas is not None:
        codigos = " or ".join(f"COD_EXIB_FORMATADO eq '{c}'" for c in contas)
        filtro  = f"IDN_CLAS eq 'RR' and ({codigos})"
    else:
        filtro  = "IDN_CLAS eq 'RR'"

    selecao = (
        "TIPO,NUM_ANO,NUM_PERI,COD_UF,SIG_UF,"
        "COD_MUNI,NOM_MUNI,COD_EXIB_FORMATADO,NOM_ITEM,"
        "IDN_CLAS,NOM_COLU,NUM_NIVE,NUM_ORDE,VAL_DECL"
    )
    return (
        f"{_BASE_URL}"
        f"?@Ano_Consulta={ano}"
        f"&@Num_Peri={_PERIODO}"
        f"&@Sig_UF='{sig_uf}'"
        f"&$filter={urllib.parse.quote(filtro)}"
        f"&$format=text/csv"
        f"&$select={selecao}"
    )


def _buscar(sig_uf: str, ano: int) -> list[dict]:
    """Retorna registros de ISS e Cota-Parte ICMS de uma UF/ano. [] se sem dados."""
    contas = _contas_por_ano(ano)
    # 2019-2020: códigos com vírgulas quebram o filtro OData no servidor →
    # busca tudo e filtra em Python.
    url_contas = None if ano <= 2020 else contas
    resp = _get_session().get(_construir_url(sig_uf, ano, url_contas), timeout=60)
    resp.raise_for_status()

    time.sleep(_PAUSA)  # rate-limit no worker, não no orquestrador

    texto = resp.text.strip()
    if not texto:
        return []

    # Auto-detecção do separador (API pode retornar CSV com vírgula)
    try:
        df = pd.read_csv(io.StringIO(texto), sep=",", dtype=str)
        if df.shape[1] < 5:
            df = pd.read_csv(io.StringIO(texto), sep=";", dtype=str)
    except Exception:
        return []

    if df.empty or "COD_MUNI" not in df.columns:
        return []

    registros: list[dict] = []
    for _, row in df.iterrows():
        cod_conta = str(row.get("COD_EXIB_FORMATADO", "")).strip()
        indicador = contas.get(cod_conta)
        if not indicador:
            continue

        raw_cod = str(row.get("COD_MUNI", "")).strip().split(".")[0]
        if raw_cod.isdigit():
            cod_ibge = raw_cod.zfill(6)
        elif sig_uf == "DF":
            # A API FNDE não preenche COD_MUNI para o DF — usamos o código
            # de Brasília (6 dígitos, sem dígito verificador).
            cod_ibge = "530010"
        else:
            continue  # município sem código IBGE válido — descarta a linha

        raw_no_ente = str(row.get("NOM_MUNI", "")).strip()
        no_ente = "Brasília" if (not raw_no_ente or raw_no_ente == "nan") and sig_uf == "DF" else raw_no_ente

        raw_valor = str(row.get("VAL_DECL", "")).strip().replace(",", ".")
        try:
            valor: float | None = float(raw_valor)
        except ValueError:
            valor = None

        registros.append({
            "esfera"   : "Município",
            "co_uf"    : str(row.get("SIG_UF", sig_uf)).strip(),
            "cod_ibge" : cod_ibge,
            "no_ente"  : no_ente,
            "ano"      : ano,
            "indicador": indicador,
            "cod_conta": cod_conta,
            "conta"    : str(row.get("NOM_ITEM", "")).strip(),
            "valor"    : valor,
            "populacao": None,
        })

    # 2019-2020: ISS é composto por múltiplos códigos → agregar por município,
    # igual à metodologia do DCA (Receitas Brutas Realizadas inclui tudo).
    # Cota-Parte ICMS tem um único código e não precisa de agregação.
    if ano <= 2020 and registros:
        df_r = pd.DataFrame(registros)
        # Separar ISS (multi-código) da Cota-Parte (único código)
        df_cota = df_r[df_r["indicador"] != "ISS"]
        df_iss  = df_r[df_r["indicador"] == "ISS"]
        if not df_iss.empty:
            agg = (
                df_iss
                .groupby(["esfera", "co_uf", "cod_ibge", "no_ente", "ano", "indicador"],
                         as_index=False)
                .agg(valor=("valor", "sum"))
            )
            agg["cod_conta"]  = _COD_ISS_AGREGADO_2019_2020
            agg["conta"]      = "ISS (principal + multas/juros + dívida ativa)"
            agg["populacao"]  = None
            registros = df_cota.to_dict("records") + agg.to_dict("records")

    return registros


# ---------------------------------------------------------------------------
# Ponto de entrada do módulo
# ---------------------------------------------------------------------------
def baixar(entes_df=None) -> list:
    """
    Executa o download completo do SIOPE para todos os municípios e anos.
    Aceita entes_df para compatibilidade com o orquestrador (não utilizado;
    SIOPE é consultado por UF×ano, não por ente individual).
    Retorna lista de registros.

    Robustez (mesmo padrão dos demais módulos):
      - Tarefa não marcada como feita se _buscar() levantar exceção.
      - CSV gravado antes do checkpoint. Em queda entre os dois, o checkpoint
        é reconstruído a partir do CSV na próxima execução.
    """
    t_inicio = time.time()
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)

    uf_list = ["PR", "DF"] if common.MODO_TESTE else _UF_LIST

    feitos = ler_checkpoint(CHECKPOINT)
    linhas: list = ler_csv(CSV_SAIDA, chaves_unicas=_CHAVES_LINHA)

    # Reconstrói checkpoint a partir do CSV (cobre queda entre salvar e gravar_checkpoint)
    for ln in linhas:
        uf  = ln.get("co_uf")
        ano = ln.get("ano")
        if uf and ano is not None:
            feitos.add(f"{uf}_{ano}")

    tarefas = [
        (uf, ano)
        for uf  in uf_list
        for ano in ANOS
        if f"{uf}_{ano}" not in feitos
    ]

    total     = len(uf_list) * len(ANOS)
    pendentes = len(tarefas)
    print(f"\n[SIOPE] Total: {total} UF×ano | Já feitos: {total - pendentes} | Pendentes: {pendentes}")

    n_novos = 0
    n_erros = 0

    def _processar(args):
        uf, ano = args
        return uf, ano, _buscar(uf, ano)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futuros = {executor.submit(_processar, t): t for t in tarefas}
        with tqdm(total=pendentes, desc="SIOPE", unit="req", disable=not tarefas) as pbar:
            for futuro in as_completed(futuros):
                try:
                    uf, ano, resultado = futuro.result()
                except Exception as exc:
                    tqdm.write(f"  [SIOPE] Erro: {exc}")
                    n_erros += 1
                    pbar.update(1)
                    continue

                linhas.extend(resultado)
                feitos.add(f"{uf}_{ano}")
                n_novos += 1

                pbar.set_postfix(uf=uf, ano=ano, n=len(resultado))
                pbar.update(1)

                if n_novos % _SALVAR_A_CADA == 0:
                    salvar_csv(CSV_SAIDA, linhas)
                    gravar_checkpoint(CHECKPOINT, feitos)

    salvar_csv(CSV_SAIDA, linhas)
    gravar_checkpoint(CHECKPOINT, feitos)
    gravar_log_execucao("SIOPE", t_inicio, len(linhas), n_erros)
    err_str = f" | erros: {n_erros}" if n_erros else ""
    print(f"\n[SIOPE] Concluído — {len(linhas)} registros{err_str} -> {CSV_SAIDA}")
    imprimir_resumo(linhas, "SIOPE")
    return linhas
