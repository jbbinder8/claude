"""
Dinâmica anual do modelo (seção 5 da spec), na ordem de eventos da §3.1.

A função `passo_ano` avança o estado de t para t+1 e devolve as variáveis de
fluxo do ano (renda_total, consumo, etc.) para registro de métricas.

Vetorização (§6.2): todas as operações são sobre arrays de tamanho n; o único
laço interno é a varredura de faixas na histerese (3 níveis, sobre arrays — não
sobre famílias).
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

import parametros as P
import metricas as M
from inicializacao import Estado, sortear_retorno_por_faixa


@dataclass
class FluxosAno:
    """Variáveis de fluxo de um ano (para métricas §7.2 e decomposição §7.3)."""
    ano: int
    renda_trabalho: np.ndarray
    retorno_patrimonio: np.ndarray
    transferencia: np.ndarray
    renda_total: np.ndarray
    consumo: np.ndarray
    poupanca: np.ndarray
    transferencia_total: float
    teve_edu: np.ndarray            # choque de educação neste ano
    desempregado: np.ndarray        # status pós-atualização (True = desempregado)
    dpatrimonio: np.ndarray         # patrimônio_i(t+1) − patrimônio_i(t)


def _faixa_com_histerese(patrimonio: np.ndarray, faixa_ant: np.ndarray,
                         limites_t: np.ndarray, banda: float) -> np.ndarray:
    """Nova faixa (0..3) com histerese de ±banda (§5.2), vetorizada.

    Sobe para k+1 só se patrimônio > limite_k·(1+banda); desce para k-1 só se
    patrimônio < limite_{k-1}·(1−banda); caso contrário permanece.

    Implementação sem laço por família:
      faixa_up   = nº de bordas SUPERIORES (limite·(1+banda)) ultrapassadas
                   -> faixa mínima justificada por promoção
      faixa_down = nº de bordas INFERIORES (limite·(1−banda)) ultrapassadas
                   -> faixa máxima ainda sustentada (sem rebaixamento forçado)
      nova       = clip(faixa_ant, faixa_up, faixa_down)
    """
    sup = limites_t * (1.0 + banda)
    inf = limites_t * (1.0 - banda)
    faixa_up = (patrimonio[:, None] > sup[None, :]).sum(axis=1).astype(np.int8)
    faixa_down = (patrimonio[:, None] > inf[None, :]).sum(axis=1).astype(np.int8)
    return np.clip(faixa_ant, faixa_up, faixa_down).astype(np.int8)


def passo_ano(est: Estado, ano: int, cen: P.Cenario,
              rng: np.random.Generator) -> FluxosAno:
    """Executa as 10 etapas da §3.1 para o ano `ano`. Muta `est` in-place."""
    n = est.n
    t_rel = ano - P.ANO_INICIAL
    fator_g = (1.0 + cen.g) ** t_rel
    patr_inicio = est.patrimonio.copy()        # patrimônio_i(t), p/ Δ e decomposição

    # Grupo de decil de renda_trabalho_base do ANO ANTERIOR (capital humano).
    # Usado tanto para desemprego (1) quanto educação (2) — ancoragem da §5.2/§5.3.
    grupo = M.grupo_decil_emprego(est.renda_trabalho_base)  # 0=D1-3,1=D4-6,2=D7-9,3=D10

    # ---- 1. status_emprego (cadeia de Markov, §5.3) -----------------------
    p_demitir = np.empty(n)
    p_demitir[grupo == 0] = P.P_DEMITIR_D1_3
    p_demitir[(grupo == 1) | (grupo == 2)] = P.P_DEMITIR_D4_9
    p_demitir[grupo == 3] = P.P_DEMITIR_D10

    u = rng.random(n)
    empregado = est.status_emprego
    novo_status = empregado.copy()
    # empregados -> podem demitir
    novo_status[empregado] = ~(u[empregado] < p_demitir[empregado])
    # desempregados -> podem reempregar
    novo_status[~empregado] = u[~empregado] < P.P_REEMPREGAR
    est.status_emprego = novo_status

    # ---- 2. choque de educação (§5.4) -------------------------------------
    p_edu = np.empty(n)
    p_edu[grupo == 0] = P.P_EDU_D1_3
    p_edu[grupo == 1] = P.P_EDU_D4_6
    p_edu[grupo == 2] = P.P_EDU_D7_9
    p_edu[grupo == 3] = P.P_EDU_D10
    pode_edu = est.n_choques_edu < cen.max_choques_edu
    sorteia_edu = (rng.random(n) < p_edu) & pode_edu
    fator_edu = rng.uniform(P.EDU_GANHO_LO, P.EDU_GANHO_HI, size=n)
    est.renda_trabalho_base = np.where(
        sorteia_edu, est.renda_trabalho_base * fator_edu, est.renda_trabalho_base)
    est.n_choques_edu = est.n_choques_edu + sorteia_edu.astype(np.int16)

    # ---- 3. renda do trabalho do ano (§5.1) -------------------------------
    choque_emprego = np.where(est.status_emprego, 1.0, 1.0 - cen.alpha_seguro)
    renda_trabalho = est.renda_trabalho_base * fator_g * choque_emprego

    # ---- 4. retorno do patrimônio (§5.2) ----------------------------------
    retorno_patrimonio = est.retorno_real * est.patrimonio

    # ---- 5. transferência (§5.1) — ver [D3] no cabeçalho de parametros.py --
    if cen.limiar_usa_renda_total:
        base_eleg = renda_trabalho + retorno_patrimonio
    else:
        base_eleg = renda_trabalho
    renda_pc_mensal = base_eleg / P.MORADORES_POR_FAMILIA / 12.0
    elegivel = renda_pc_mensal < cen.limiar
    valor_transf = cen.transferencia_base * P.MORADORES_POR_FAMILIA * 12.0
    transferencia = np.where(elegivel, valor_transf, 0.0)

    # ---- 6. renda total ---------------------------------------------------
    renda_total = renda_trabalho + transferencia + retorno_patrimonio

    # ---- 7. faixa de decil de renda total -> propensão (§4.3) -------------
    faixa_dec = M.faixa_decil_renda_total(renda_total)
    propensao = est.c_faixa_decil[np.arange(n), faixa_dec]

    # ---- 8. consumo, poupança e patrimônio pós-poupança (§5.5) ------------
    consumo = propensao * renda_total
    poupanca = renda_total - consumo
    patrimonio_pos = np.maximum(0.0, est.patrimonio + poupanca)

    # ---- 9. choque de sucessão (§5.6) -------------------------------------
    if cen.p_sucessao > 0:
        ocorre = rng.random(n) < cen.p_sucessao
        n_herd = rng.integers(1, 5, size=n)              # {1,2,3,4}
        fator_dil = np.where(ocorre, 1.0 / n_herd, 1.0)
        patrimonio_prox = patrimonio_pos * fator_dil
    else:
        patrimonio_prox = patrimonio_pos

    # ---- 10. faixa de patrimônio (t+1) com histerese; re-sorteio (§5.2) ---
    limites_t1 = P.LIMITES_FAIXA_INICIAL * ((1.0 + cen.g) ** (t_rel + 1))
    nova_faixa = _faixa_com_histerese(
        patrimonio_prox, est.faixa_patrimonio, limites_t1, cen.banda_histerese)
    mudou = nova_faixa != est.faixa_patrimonio
    if mudou.any():
        idx = np.where(mudou)[0]
        novos = sortear_retorno_por_faixa(
            rng, nova_faixa[idx], cen.retorno_media_faixa, cen.retorno_dp_faixa)
        est.retorno_real = est.retorno_real.copy()
        est.retorno_real[idx] = novos
    est.faixa_patrimonio = nova_faixa
    est.patrimonio = patrimonio_prox

    return FluxosAno(
        ano=ano, renda_trabalho=renda_trabalho,
        retorno_patrimonio=retorno_patrimonio, transferencia=transferencia,
        renda_total=renda_total, consumo=consumo, poupanca=poupanca,
        transferencia_total=float(transferencia.sum()),
        teve_edu=sorteia_edu, desempregado=~est.status_emprego,
        dpatrimonio=est.patrimonio - patr_inicio,
    )
