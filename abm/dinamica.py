import numpy as np
from parametros import (
    G_RENDA, IDADE_TRABALHO_INICIO, IDADE_APOSENTADORIA,
    PENSAO_ANUAL, TAXA_REPOSICAO_APOS,
    TAXA_HIPOTECA, FRAC_AMORTIZACAO_ANUAL,
)


def calcular_renda_anual(pop: dict, t: int) -> np.ndarray:
    """Renda total (trabalho + pensao). Cresce com g em termos reais."""
    fator = (1 + G_RENDA) ** t
    em_atividade = (
        pop['vivo'] &
        (pop['idade'] >= IDADE_TRABALHO_INICIO) &
        (pop['idade'] < IDADE_APOSENTADORIA)
    )
    aposentado = pop['vivo'] & (pop['idade'] >= IDADE_APOSENTADORIA)
    renda_trabalho = np.where(em_atividade, pop['renda_base'] * fator, 0.0)
    pensao = np.where(aposentado, PENSAO_ANUAL * fator, 0.0)
    return renda_trabalho + pensao


def _pagar_hipoteca(pop: dict) -> None:
    """Servico anual da hipoteca residencial: juros + amortizacao linear.

    - Tomado do capital do agente.
    - Se o capital nao cobre, paga o maximo possivel; juros nao pagos somam a divida.
    - Na morte do agente (ciclo_vida), a divida e' cancelada.
    """
    em_divida = pop['vivo'] & (pop['divida_imovel'] > 0)
    if not em_divida.any():
        return
    divida = pop['divida_imovel']
    juros_h = divida * TAXA_HIPOTECA
    amort_alvo = divida * FRAC_AMORTIZACAO_ANUAL
    total = juros_h + amort_alvo
    pode_pagar = np.minimum(total, np.maximum(pop['capital'], 0.0))
    # Aplica pagamento (so' onde ha divida)
    pop['capital'][em_divida] -= pode_pagar[em_divida]
    # Evolucao da divida: divida_next = divida + juros - pago
    divida_next = divida + juros_h - pode_pagar
    pop['divida_imovel'][em_divida] = np.maximum(divida_next[em_divida], 0.0)


def evoluir_capital(pop: dict, t: int) -> None:
    vivo = pop['vivo']
    fator = (1 + G_RENDA) ** t

    em_atividade = (
        vivo &
        (pop['idade'] >= IDADE_TRABALHO_INICIO) &
        (pop['idade'] < IDADE_APOSENTADORIA)
    )
    aposentado = vivo & (pop['idade'] >= IDADE_APOSENTADORIA)

    # 1) Renda do trabalho (so' ativos) — sera poupada na fracao s
    renda_trabalho = np.where(em_atividade, pop['renda_base'] * fator, 0.0)
    poupanca = renda_trabalho * pop['taxa_poupanca'].astype(np.float64)

    # 2) Pensao publica e consumo do aposentado
    pensao = np.where(aposentado, PENSAO_ANUAL * fator, 0.0)
    # Consumo do aposentado = taxa de reposicao × renda pre-aposentadoria.
    # Mantem padrao de vida proporcional ao que tinha trabalhando.
    consumo_apos = np.where(aposentado, TAXA_REPOSICAO_APOS * pop['renda_base'] * fator, 0.0)
    fluxo_apos = pensao - consumo_apos   # tipicamente negativo

    # 3) Rendimento do capital
    juros = pop['capital'] * pop['retorno'].astype(np.float64)

    # 4) Aplicar fluxo total ao capital, clamp em 0
    delta = juros + poupanca + fluxo_apos
    pop['capital'][vivo] += delta[vivo]
    np.maximum(pop['capital'], 0.0, out=pop['capital'])

    # 5) Servico de hipoteca residencial
    _pagar_hipoteca(pop)


def envelhecer(pop: dict) -> None:
    pop['idade'][pop['vivo']] += 1
