import numpy as np

# Reprodutibilidade
SEMENTE = 42

# Escala
N_AGENTES_INICIAL = 50_000
N_ANOS = 100
BUFFER_AGENTES = 600_000

# Macroeconomia (valores reais anuais)
R_JUROS = 0.07   # retorno real do capital financeiro
G_RENDA = 0.02   # crescimento real da renda do trabalho

# Retorno efetivo por classe de ativo financeiro
RETORNO_POR_CLASSE = {
    0: 0.00,    # consumidora: nao investe capital financeiro
    1: 0.065,   # poupadora: mix fundos + renda fixa
    2: 0.07,    # rentista: carteira otimizada
}

# Taxa de poupanca por classe (fracao da renda do trabalho)
POUPANCA_POR_CLASSE = {
    0: (0.00, 0.10),   # consumidora: quem poupa, poupa entre 0-10%
    1: (0.10, 0.38),   # poupadora: poupa 10-38%
    2: (0.00, 0.00),   # rentista: vive dos juros
}

# Fracao que poupa exatamente zero (complemento sorteia no intervalo acima)
FRAC_POUPANCA_ZERO = {0: 0.50}   # 50% das consumidoras nao poupam nada

# Proporcao inicial das classes
PROPORCAO_CLASSES = [0.75, 0.20, 0.05]

# -------------------------------------------------------------------
# CALIBRACAO BRASIL 2024
# -------------------------------------------------------------------

# Renda anual do trabalho (R$ reais 2024) -- log-normal (mu_real, sigma)
# Fonte: PNAD/IBGE 2023
RENDA_POR_CLASSE = {
    0: (30_000, 0.60),    # consumidora: ~R$2.500/mes (proximo mediana Brasil)
    1: (120_000, 0.50),   # poupadora:  ~R$10.000/mes (servidores / alta renda)
    2: (100_000, 0.70),   # rentista:   renda trabalho secundaria
}

# Capital FINANCEIRO inicial (R$ reais 2024) -- log-normal (mu_real, sigma)
# Consumidora comeca com zero capital financeiro.
CAPITAL_INICIAL_POR_CLASSE = {
    0: None,                    # consumidora: capital financeiro = R$0
    1: (200_000, 0.90),         # poupadora: mediana ~R$200k em aplicacoes
    2: (5_000_000, 1.50),       # rentista: mediana ~R$5M (fat-tail)
}

# -------------------------------------------------------------------
# DEMOGRAFIA BRASIL -- TABUAS IBGE 2022
# -------------------------------------------------------------------

# Tábua de mortalidade anual por grupo quinquenal de idade
# Grupos: 0-4, 5-9, 10-14, ..., 85-89, 90+ (19 grupos)
# Fonte: IBGE Tábua Completa 2022 × 0.85 (ajuste prospectivo para e(0)~82 em 2050).
# CDR implícito ~0.72% para pirâmide brasileira 2026. e(0) implícita ~82 anos.
MORT_ANUAL_POR_GRUPO = np.array([
    0.0022, 0.0001, 0.0001, 0.0006,   # 0-4, 5-9, 10-14, 15-19
    0.0009, 0.0009, 0.0011, 0.0014,   # 20-24, 25-29, 30-34, 35-39
    0.0022, 0.0033, 0.0053, 0.0082,   # 40-44, 45-49, 50-54, 55-59
    0.0126, 0.0196, 0.0311, 0.0479,   # 60-64, 65-69, 70-74, 75-79
    0.0729, 0.1086, 0.1700,            # 80-84, 85-89, 90+
])

# Taxas de fecundidade anuais por grupo quinquenal (por agente, modelo neutro)
# Calibrado para TFR ~1.77/mulher (Brasil 2026 ~1.7) e trajetória IBGE:
#   pico ~2050 (+7-10%), retorno a -20% abaixo de 2026 em ~2100.
# TFR_base = sum × 5 × 2 = 0.163 × 10 = 1.63/mulher (× mult_medio 1.09 → 1.78/mulher)
# Fonte: IBGE PNAD 2023 / SINASC 2022 × 1.20 (ajuste para CBR ~1.52%/ano em 2026)
FERTIL_ANUAL_POR_GRUPO = np.array([
    0.000, 0.000, 0.000,   # 0-4, 5-9, 10-14
    0.018, 0.038, 0.042,   # 15-19, 20-24, 25-29  <- pico 25-29
    0.037, 0.020, 0.006,   # 30-34, 35-39, 40-44
    0.001, 0.000, 0.000,   # 45-49, 50-54, 55-59
    0.000, 0.000, 0.000,   # 60-64, 65-69, 70-74
    0.000, 0.000, 0.000,   # 75-79, 80-84, 85-89
    0.000,                  # 90+
])

# Multiplicadores de fecundidade por classe (0=consumidora,1=poupadora,2=rentista)
# TFR efetivo ponderado: 0.75×1.70 + 0.20×1.41 + 0.05×1.11 = 1.275+0.282+0.056 = 1.61/mulher
FERTIL_MULT_CLASSE = np.array([1.15, 0.95, 0.75])

# Ciclo de vida (limites de idades)
IDADE_TRABALHO_INICIO = 18
IDADE_APOSENTADORIA   = 65

# Piramide etaria brasileira 2024
# Probabilidades por grupo quinquenal: 0-4, 5-9, ..., 85-89 (18 grupos)
# Fonte: IBGE Projecoes 2024 (aproximado)
_PIRAMIDE_PROBS_RAW = np.array([
    4.5, 5.0, 5.5, 6.0,   # 0-4, 5-9, 10-14, 15-19
    7.5, 8.0, 8.0, 7.5,   # 20-24, 25-29, 30-34, 35-39
    7.0, 6.5, 6.0, 5.0,   # 40-44, 45-49, 50-54, 55-59
    4.0, 3.5, 2.5, 2.0,   # 60-64, 65-69, 70-74, 75-79
    1.0, 0.5,              # 80-84, 85-89
])
PIRAMIDE_ETARIA_BR = _PIRAMIDE_PROBS_RAW / _PIRAMIDE_PROBS_RAW.sum()

# -------------------------------------------------------------------
# MERCADO IMOBILIARIO
# -------------------------------------------------------------------

# Preco inicial calibrado para media nacional Brasil 2024
PRECO_IMOVEL_INICIAL    = 300_000      # R$300k media nacional
N_IMOVEIS_INICIAL       = 50_000       # ~1 unidade por agente inicial
TAXA_CONSTRUCAO         = 0.015        # 1.5%/ano (realista Brasil: 1-2%/ano)
TAXA_CONSTR_MAX         = 0.040        # teto quando precos muito acima do equilibrio
GATILHO_CONSTR          = 1.30         # preco/eq que dispara construcao adicional

YIELD_ALUGUEL_BASE      = 0.035        # 3.5% yield bruto de aluguel
FRACAO_RENDA_ALUGUEL    = 0.35         # consumidor gasta 35% da renda com moradia

TAXA_AJUSTE_PRECO       = 0.08
PISO_PRECO_FRAC         = 0.40
DESCONTO_TOL_RE         = 0.80         # compra investimento se yield_ef >= r * desconto
ENTRADA_MINIMA_FRAC     = 0.25         # 25% de entrada (hipoteca simplificada)

# Maximo de imoveis por classe — diferenciados por perfil de investimento real:
#   C0 (consumidora): 2 — residencia + eventual 1 emergencia (sem perfil de investidor)
#   C1 (poupadora):   5 — residencia + ate 4 alugueis (classe media nao diversifica em dezenas)
#   C2 (rentista):    sem cap pratico — diversifica em real estate como portfolio (rentista
#                     real possui dezenas/centenas de unidades). Limite tecnico: 10000.
MAX_IMOVEIS_POR_CLASSE  = {0: 2, 1: 5, 2: 10_000}

# Taxa de propriedade inicial por classe (meta: ~73% global -- PNAD 2022)
PROP_PROPRIETARIO_INI   = {0: 0.68, 1: 0.88, 2: 1.00}
# Imoveis de investimento na inicializacao
PROP_2O_IMOVEL_INI      = {0: 0.00, 1: 0.22, 2: 0.55}
MEDIA_INVEST_RENTISTA   = 1.50   # media de imoveis extras alem do principal p/ rentistas

# -------------------------------------------------------------------
# APOSENTADORIA / PENSAO / CONSUMO
# -------------------------------------------------------------------
# Piso publico — atualmente vinculado ao salario minimo (~R$1.412/mes em 2024).
# Cresce com g (acompanha produtividade real, como o SM brasileiro historicamente).
PENSAO_ANUAL = 15_000

# Aposentado consome fracao da renda pre-aposentadoria (taxa de reposicao).
# 70% e' o consenso da literatura previdenciaria (replacement rate alvo).
# Aplicado sobre renda_base × (1+g)^t, ou seja, mantem padrao de vida proporcional.
TAXA_REPOSICAO_APOS = 0.70

# -------------------------------------------------------------------
# HIPOTECA RESIDENCIAL — rastreamento de divida (item 5)
# -------------------------------------------------------------------
TAXA_HIPOTECA           = R_JUROS        # custo do financiamento = r real (sem spread)
FRAC_AMORTIZACAO_ANUAL  = 1.0 / 30.0     # ~3.33% do saldo amortizado/ano (~30 anos)
# Comprometimento maximo da renda em servico de divida (regra Bacen ~30-35%).
LIMITE_COMPROMETIMENTO  = 0.35

# -------------------------------------------------------------------
# MONTE CARLO
# -------------------------------------------------------------------
N_RUNS_MC = 20    # numero de sementes para reportar bandas de incerteza

# Referencia de poder de compra
PRECO_BIG_MAC = 30      # R$ reais 2024 (constante em termos reais)

