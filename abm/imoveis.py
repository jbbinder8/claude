"""
Mercado imobiliário endógeno — v3.

Preço:
  Não segue oferta/estoque bruto (que causava colapso), mas converge para um
  preço de equilíbrio baseado em renda:
    preco_eq = aluguel_anual / yield_base
    aluguel = FRACAO_RENDA_ALUGUEL × renda_media_consumidora (cresce com g)

  Pressão de demanda (compradores/turnover esperado) é um componente secundário.

Aluguel (fluxo):
  Desacoplado do preço — baseado na renda dos agentes. Isso evita o loop
  vicioso "preço cai → aluguel cai → menos receita → menos demanda → preço cai".
  Renters pagam; landlords (n_imoveis >= 2) recebem proporcionalmente.

Compra:
  Residência (n_imoveis=0): compra se capital >= preco (não compara com juro)
  Investimento (n_imoveis>=1): compra se yield_ef + apreciação >= r × desconto
"""

import numpy as np
from parametros import (
    N_IMOVEIS_INICIAL, TAXA_CONSTRUCAO, TAXA_CONSTR_MAX, GATILHO_CONSTR,
    PRECO_IMOVEL_INICIAL, YIELD_ALUGUEL_BASE, FRACAO_RENDA_ALUGUEL,
    TAXA_AJUSTE_PRECO, PISO_PRECO_FRAC,
    DESCONTO_TOL_RE, ENTRADA_MINIMA_FRAC, MAX_IMOVEIS_POR_CLASSE,
    PROP_PROPRIETARIO_INI, PROP_2O_IMOVEL_INI, MEDIA_INVEST_RENTISTA,
    R_JUROS, G_RENDA, IDADE_TRABALHO_INICIO, IDADE_APOSENTADORIA,
    RENDA_POR_CLASSE,
    TAXA_HIPOTECA, FRAC_AMORTIZACAO_ANUAL, LIMITE_COMPROMETIMENTO,
)

_TURNOVER_NORMAL = 0.03   # 3% do estoque muda de mãos por ano (referência de equilíbrio)


def criar_mercado() -> dict:
    aluguel_inicial = RENDA_POR_CLASSE[0][0] * FRACAO_RENDA_ALUGUEL
    return {
        'preco':              float(PRECO_IMOVEL_INICIAL),
        'n_total':            N_IMOVEIS_INICIAL,
        'yield_base':         YIELD_ALUGUEL_BASE,
        'apreciacao_recente': 0.0,
        'aluguel_atual':      aluguel_inicial,
        'rent_total_ano':     0.0,   # total aluguel pago no ultimo ano
        'n_renters_ano':      0,     # renters no ultimo ano
        'hist_preco':         [float(PRECO_IMOVEL_INICIAL)],
        'hist_taxa_prop':     [],
        'hist_vacancia':      [],
    }


def _aluguel_anual(pop: dict, ano: int) -> float:
    """Aluguel baseado na renda média dos consumidores em idade ativa."""
    mask = pop['vivo'] & (pop['classe'] == 0) & (pop['idade'] >= IDADE_TRABALHO_INICIO)
    if mask.sum() == 0:
        return RENDA_POR_CLASSE[0][0] * (1 + G_RENDA) ** ano * FRACAO_RENDA_ALUGUEL
    renda_media = (pop['renda_base'][mask] * (1 + G_RENDA) ** ano).mean()
    return float(renda_media * FRACAO_RENDA_ALUGUEL)


def inicializar_propriedades(pop: dict, n: int, mercado: dict,
                              rng: np.random.Generator) -> None:
    """Atribui propriedades por probabilidade calibrada (PNAD 2022 ~73%)."""
    for c in range(3):
        idx_c = np.where((pop['classe'][:n] == c) & pop['vivo'][:n])[0]
        if len(idx_c) == 0:
            continue

        # Residência principal
        n_prop = int(PROP_PROPRIETARIO_INI[c] * len(idx_c))
        proprietarios = rng.choice(idx_c, size=n_prop, replace=False)
        pop['n_imoveis'][proprietarios] = 1

        # 2o imóvel (investimento)
        frac_2o = PROP_2O_IMOVEL_INI[c]
        if frac_2o > 0 and len(proprietarios) > 0:
            n_2o = int(frac_2o * len(idx_c))
            n_2o = min(n_2o, len(proprietarios))
            com_2o = rng.choice(proprietarios, size=n_2o, replace=False)
            pop['n_imoveis'][com_2o] += 1

            # Rentistas: imóveis extras além do 2o (Poisson)
            if c == 2:
                max_c = MAX_IMOVEIS_POR_CLASSE[c]
                for idx in com_2o:
                    extras = int(rng.poisson(MEDIA_INVEST_RENTISTA - 1))
                    pop['n_imoveis'][idx] = min(int(pop['n_imoveis'][idx]) + extras, max_c)

    # Garantir que o estoque total comporte os imóveis atribuídos
    n_detidos = int(pop['n_imoveis'][:n].sum())
    mercado['n_total'] = max(mercado['n_total'], n_detidos + 500)


def passo_mercado(pop: dict, mercado: dict, ano: int,
                  rng: np.random.Generator) -> None:
    """Executa um passo anual do mercado imobiliário."""

    # 1. Oferta (construção incremental + resposta a preços)
    n_detidos     = int(pop['n_imoveis'][pop['vivo']].sum())
    preco_ant_step = mercado['preco']   # será atualizado abaixo; usar antes do ajuste

    # Taxa efetiva de construção: base + bônus se preço > equilíbrio × gatilho
    ratio_preco = preco_ant_step / max(mercado.get('preco_eq_ant', preco_ant_step), 1.0)
    if ratio_preco > GATILHO_CONSTR:
        bonus = min(TAXA_CONSTRUCAO * (ratio_preco - GATILHO_CONSTR) * 2, TAXA_CONSTR_MAX - TAXA_CONSTRUCAO)
    else:
        bonus = 0.0
    taxa_ef = min(TAXA_CONSTRUCAO + bonus, TAXA_CONSTR_MAX)
    mercado['n_total'] += max(1, int(mercado['n_total'] * taxa_ef))

    n_disponiveis = max(0, mercado['n_total'] - n_detidos)

    # 2. Aluguel de mercado (baseado em renda — independente do preço)
    aluguel_unit = _aluguel_anual(pop, ano)
    mercado['aluguel_atual'] = aluguel_unit

    # 3. Preço de equilíbrio implícito (renda / yield)
    preco_eq = aluguel_unit / mercado['yield_base']

    # 4. Yield efetivo (aluguel atual / preço atual) para decisão de investimento
    yield_ef = aluguel_unit / max(mercado['preco'], 1.0)
    retorno_re = yield_ef + mercado['apreciacao_recente']

    # 5. Demanda
    max_im = np.zeros(len(pop['vivo']), dtype=np.int16)
    for c, m in MAX_IMOVEIS_POR_CLASSE.items():
        max_im[pop['classe'] == c] = m

    entrada = mercado['preco'] * ENTRADA_MINIMA_FRAC   # 25% de entrada
    divida_hipoteca = mercado['preco'] - entrada
    # Servico anual da hipoteca (juros + amortizacao linear sobre o saldo).
    # Para qualificacao, usamos o valor no primeiro ano da divida.
    servico_anual = divida_hipoteca * (TAXA_HIPOTECA + FRAC_AMORTIZACAO_ANUAL)

    # Renda corrente do trabalho (para checagem de credito)
    fator_g = (1 + G_RENDA) ** ano
    em_atividade = (
        pop['vivo'] &
        (pop['idade'] >= IDADE_TRABALHO_INICIO) &
        (pop['idade'] < IDADE_APOSENTADORIA)
    )
    renda_corrente = np.where(em_atividade, pop['renda_base'] * fator_g, 0.0)

    # Residencia: precisa de entrada + renda suficiente para servir o financiamento
    # (credito so' concedido a quem comprovar capacidade — analogo a regra Bacen).
    quer_residencia = (
        pop['vivo'] &
        (pop['n_imoveis'] == 0) &
        (pop['capital'] >= entrada) &
        (max_im > 0) &
        (renda_corrente * LIMITE_COMPROMETIMENTO >= servico_anual)
    )
    # Investimento: preco integral (sem alavancagem) E retorno competitivo
    quer_investir = (
        pop['vivo'] &
        (pop['n_imoveis'] >= 1) &
        (pop['n_imoveis'] < max_im) &
        (pop['capital'] >= mercado['preco']) &
        (retorno_re >= R_JUROS * DESCONTO_TOL_RE)
    )
    compradores   = np.where(quer_residencia | quer_investir)[0]
    n_demanda     = len(compradores)

    # 6. Transacoes
    #    - Residencia: paga entrada, recebe imovel + assume divida = preco - entrada
    #    - Investimento: paga preco integral, sem divida (sem alavancagem em invest.)
    n_trans = min(n_demanda, n_disponiveis)
    if n_trans > 0:
        escolhidos = rng.choice(compradores, size=n_trans, replace=False)
        for idx in escolhidos:
            if pop['n_imoveis'][idx] == 0:
                pop['capital'][idx]      -= entrada
                pop['divida_imovel'][idx] = divida_hipoteca
            else:
                pop['capital'][idx] -= mercado['preco']
            pop['n_imoveis'][idx] += 1
        np.maximum(pop['capital'], 0.0, out=pop['capital'])

    # 7. Ajuste de preço:
    #    60% pull em direção ao equilíbrio de renda
    #    40% pressão de demanda relativa ao turnover normal esperado
    pressao_eq = (preco_eq / max(mercado['preco'], 1.0)) - 1.0
    turnover_esp = max(int(_TURNOVER_NORMAL * n_detidos), 5)
    pressao_dem  = (n_trans - turnover_esp) / turnover_esp

    variacao = float(np.clip(
        TAXA_AJUSTE_PRECO * (0.6 * pressao_eq + 0.4 * pressao_dem),
        -0.08, 0.15,
    ))
    preco_ant = mercado['preco']
    mercado['preco'] = max(
        mercado['preco'] * (1.0 + variacao),
        PRECO_IMOVEL_INICIAL * PISO_PRECO_FRAC,
    )
    mercado['apreciacao_recente'] = (mercado['preco'] - preco_ant) / preco_ant
    mercado['preco_eq_ant'] = preco_eq   # usado no próximo passo para gatilho de construção

    # 8. Fluxo de aluguel — CONSERVACAO MONETARIA
    #    Cada renter paga ate o limite do seu capital disponivel.
    #    Landlords recebem apenas o total efetivamente pago (sem aluguel fantasma).
    renters = (
        pop['vivo'] &
        (pop['n_imoveis'] == 0) &
        (pop['idade'] >= IDADE_TRABALHO_INICIO)
    )
    n_renters = int(renters.sum())

    if n_renters > 0:
        cap_renters = pop['capital'][renters]
        pago_indiv = np.minimum(cap_renters, aluguel_unit)
        pop['capital'][renters] = cap_renters - pago_indiv
        total_rent = float(pago_indiv.sum())
    else:
        total_rent = 0.0

    # Landlords recebem proporcional ao numero de unidades de investimento.
    investimento = np.maximum(pop['n_imoveis'].astype(np.int32) - 1, 0)
    investimento[~pop['vivo']] = 0
    n_inv = int(investimento.sum())
    if n_inv > 0 and total_rent > 0:
        renda_unit_inv = total_rent / n_inv
        pop['capital'] += investimento * renda_unit_inv

    mercado['rent_total_ano'] = total_rent
    mercado['n_renters_ano']  = n_renters

    # 9. Histórico
    vivo = pop['vivo']
    n_vivos = int(vivo.sum())
    n_prop  = int((pop['n_imoveis'][vivo] > 0).sum())
    mercado['hist_preco'].append(mercado['preco'])
    mercado['hist_taxa_prop'].append(n_prop / max(n_vivos, 1))
    mercado['hist_vacancia'].append(n_disponiveis / max(mercado['n_total'], 1))


def convert_imoveis_para_heranca(pop: dict, i: int, mercado: dict) -> None:
    """Liquida propriedades ao preço de mercado antes de herança."""
    pop['capital'][i] += int(pop['n_imoveis'][i]) * mercado['preco']
    pop['n_imoveis'][i] = 0
