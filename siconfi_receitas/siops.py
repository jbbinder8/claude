"""
siops.py — Módulo SIOPS (DATASUS — siops.datasus.gov.br).

Extrai via scraping do relatório LRF-Fiscal (POST):
  • ISS                — municípios
  • Cota-Parte do ICMS — municípios

Período : 2019-2025  (ANOS definido em common.py)
Saída   : output/siops/receitas_siops.csv
"""

import time
from pathlib import Path

import requests
from tqdm import tqdm
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter, Retry

from .common import (
    ANOS, SALVAR_A_CADA,
    obter_entes,
    ler_checkpoint, gravar_checkpoint, salvar_csv, imprimir_resumo,
)

# ---------------------------------------------------------------------------
# Configurações do módulo
# ---------------------------------------------------------------------------

DIR_SAIDA  = Path("output/receitas")
CHECKPOINT = DIR_SAIDA / "checkpoint_siops.json"
CSV_SAIDA  = DIR_SAIDA / "receitas_siops.csv"

_URL_POST = "http://siops.datasus.gov.br/rel_LRF.php"
_PERIODO  = "2"
_PAUSA    = 0.5   # mais conservador que a API SICONFI — servidor legado

_ROTULOS_ISS = [
    "Receita Resultante do Imposto sobre Serviços de Qualquer Natureza - ISS",
    "Receita Resultante do Imposto sobre Serviços de Qualquer Natureza",
]
_ROTULOS_ICMS = ["Cota-Parte do ICMS"]

# UF (sigla) → código numérico SIOPS  (= código IBGE do estado, 2 dígitos)
_UF_COD = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17",
}


# ---------------------------------------------------------------------------
# Sessão HTTP — sem concorrência (servidor legado, frágil)
# ---------------------------------------------------------------------------

def _criar_sessao() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
    )
    s.mount("http://",  HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({
        "Accept"         : "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection"     : "keep-alive",
        "User-Agent"     : (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
    })
    return s


# ---------------------------------------------------------------------------
# Parsing HTML
# ---------------------------------------------------------------------------

def _extrair_valor(soup: BeautifulSoup, rotulos: list, idx: int = 3) -> str | None:
    """Retorna o texto da célula de índice `idx` no primeiro <tr> cujo texto contenha algum dos rótulos."""
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        texto = " ".join(td.get_text(" ", strip=True) for td in tds)
        if any(r in texto for r in rotulos):
            if len(tds) > idx:
                return tds[idx].get_text(" ", strip=True)
    return None


def _parse_valor(texto: str | None) -> float:
    """Converte '1.234.567,89' → 1234567.89. Retorna 0.0 se ausente ou inválido."""
    if not texto:
        return 0.0
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Consulta por município/ano
# ---------------------------------------------------------------------------

def _buscar(sessao: requests.Session, uf: str, cod_ibge: int, no_ente: str, ano: int) -> list:
    cod_uf  = _UF_COD.get(uf, "")
    cod_mun = str(cod_ibge)[:-1]   # SIOPS usa 6 dígitos (IBGE 7d sem o dígito verificador)

    payload = {
        "cmbAno"         : str(ano),
        "cmbUF"          : cod_uf,
        "cmbPeriodo"     : _PERIODO,
        "cmbMunicipio[]" : cod_mun,
        "BtConsultar"    : "Consultar",
    }
    headers_extra = {
        "Content-Type"             : "application/x-www-form-urlencoded",
        "Host"                     : "siops.datasus.gov.br",
        "Origin"                   : "http://siops.datasus.gov.br",
        "Referer"                  : (
            f"http://siops.datasus.gov.br/consleirespfiscal.php?"
            f"S=1&UF={cod_uf};&Municipio={cod_mun};&Ano={ano}&Periodo={_PERIODO}"
        ),
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        r = sessao.post(_URL_POST, data=payload, headers=headers_extra, timeout=60)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    base = {
        "esfera"   : "Município",
        "co_uf"    : uf,
        "cod_ibge" : cod_ibge,
        "no_ente"  : no_ente,
        "ano"      : ano,
        "populacao": 0,
    }

    resultados = []

    txt_icms = _extrair_valor(soup, _ROTULOS_ICMS)
    if txt_icms is not None:
        resultados.append({**base,
            "indicador": "Cota-Parte ICMS",
            "cod_conta": "SIOPS_COTA_ICMS",
            "conta"    : "Cota-Parte do ICMS",
            "valor"    : _parse_valor(txt_icms),
        })

    txt_iss = _extrair_valor(soup, _ROTULOS_ISS)
    if txt_iss is not None:
        resultados.append({**base,
            "indicador": "ISS",
            "cod_conta": "SIOPS_ISS",
            "conta"    : "Receita Resultante do ISS",
            "valor"    : _parse_valor(txt_iss),
        })

    return resultados


# ---------------------------------------------------------------------------
# Ponto de entrada do módulo
# ---------------------------------------------------------------------------

def baixar(entes_df=None) -> list:
    """
    Executa o scraping do SIOPS/LRF para municípios e anos configurados.
    Aceita entes_df pré-carregado para evitar chamada duplicada ao orquestrador.
    Retorna lista de registros.
    """
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    feitos = ler_checkpoint(CHECKPOINT)
    linhas: list = []
    n_novos = 0

    if entes_df is None:
        entes_df = obter_entes()

    # SIOPS/LRF cobre apenas municípios
    muns_df = entes_df[entes_df["esfera"] == "M"].copy()

    tarefas = []
    for _, row in muns_df.iterrows():
        for ano in ANOS:
            chave = f"M_{row['cod_ibge']}_{ano}"
            if chave not in feitos:
                tarefas.append((
                    row.get("uf", ""), int(row["cod_ibge"]),
                    row.get("ente", ""), ano, chave,
                ))

    total     = len(muns_df) * len(ANOS)
    pendentes = len(tarefas)
    print(f"\n[SIOPS] Total: {total} | Já feitos: {total - pendentes} | Pendentes: {pendentes}")
    concluidos = total - pendentes

    sessao = _criar_sessao()
    try:
        with tqdm(total=pendentes, desc="SIOPS", unit="req", disable=not tarefas) as pbar:
            for uf, cod_ibge, no_ente, ano, chave in tarefas:
                resultado = _buscar(sessao, uf, cod_ibge, no_ente, ano)

                linhas.extend(resultado)
                feitos.add(chave)
                n_novos += 1

                pbar.set_postfix(uf=uf, ente=no_ente[:20], ano=ano, n=len(resultado))
                pbar.update(1)

                if n_novos % SALVAR_A_CADA == 0:
                    gravar_checkpoint(CHECKPOINT, feitos)
                    salvar_csv(CSV_SAIDA, linhas)

                time.sleep(_PAUSA)
    finally:
        sessao.close()

    gravar_checkpoint(CHECKPOINT, feitos)
    salvar_csv(CSV_SAIDA, linhas)
    print(f"\n[SIOPS] Concluído — {len(linhas)} registros -> {CSV_SAIDA}")
    imprimir_resumo(linhas, "SIOPS")
    return linhas
