"""
Parâmetros e cenários do ABM de famílias brasileiras.

Implementa as seções 4 (calibração), 6 (política/cenários) e 8 (exógenas) da
especificação `abm-fam-br.md`.

================================================================================
DESVIOS DELIBERADOS DA SPEC (decisões de implementação documentadas)
================================================================================

[D1] Cauda Pareto do patrimônio — x_min_p (spec §4.2)
    A spec lista x_min_p = R$ 2,3M (limiar empírico do top 1%) e afirma "não há
    saltos artificiais entre corpo e cauda". Isso é inconsistente: o P99 do corpo
    log-normal é exp(μ_p + 2,326·σ_p) ≈ R$ 4,97M > 2,3M. Usar 2,3M criaria uma
    INVERSÃO de ranking (a base do top 1% cairia de ~4,9M para ~2,3M).
    DECISÃO: x_min_p = P99 do corpo log-normal = exp(μ_p + 2,326·σ_p), garantindo
    continuidade exata corpo→cauda, igual ao tratamento já usado para a renda
    (§4.1). O parâmetro permanece configurável (PARETO_X_MIN_P_MODO).

[D2] Diluição sucessória — E[1 - 1/n] (spec §5.6)
    A spec afirma E[1 - 1/n_herdeiros] = 0,604 para n ~ Uniform{1,2,3,4}. O valor
    correto é 0,479 (E[1/n] = 25/48 = 0,5208). Logo a diluição média real é
    0,03 × 0,479 ≈ 1,44%/ano, não 1,8%.
    DECISÃO: manter n ~ Uniform{1,2,3,4} e p_sucessao = 3% (defaults da spec);
    apenas corrigir o número reportado. A diluição efetiva fica ~1,44%/ano. Quem
    quiser ~1,8% pode usar p_sucessao ≈ 0,0376.

[D3] Elegibilidade de transferência — unidade (spec §5.1)
    A fórmula da spec compara renda_trabalho_i/2,79 (renda ANUAL per capita) com
    LIMIAR (R$/MÊS per capita) — faltava dividir por 12, o que tornaria ~ninguém
    elegível (quebrando o cenário S3).
    DECISÃO: comparar renda_per_capita_MENSAL = renda_anual / 2,79 / 12 < LIMIAR.

[D4] Política de calibração — alvos §4.5 mutuamente inconsistentes
    A verificação empírica (n=10.000) mostrou que vários alvos da §4.5 NÃO são
    conjuntamente satisfazíveis com a família lognormal+Pareto:
      (i) Gini de renda 0,52 vs share top 1% de renda 27%: para atingir 27% o
          Gini sobe a ~0,60. Conceitos de renda distintos (PNAD domiciliar vs
          WID nacional pré-imposto). DECISÃO DO USUÁRIO: priorizar o Gini (PNAD)
          → α_r = 1,5; o share top 1% de renda fica ~14% (informativo).
      (ii) Gini patrimonial 0,82 vs share top 1% patrimônio 40-50% vs % faixa 4
          (0,4-0,6%): idem. Aplicando coerentemente a mesma política (priorizar
          a dispersão/Gini, que é a métrica-título do modelo, §1), usamos
          α_p = 1,35 → Gini patr ≈ 0,82-0,83 (no alvo); share top 1% patr ≈ 0,36
          e % faixa 4 ≈ 1% ficam informativos.
      (iii) Pearson(ln) 0,55-0,65 vs sobreposição top1/top10 (≥25%/≥50%): a cópula
          gaussiana com ρ que respeita o Pearson (~0,60) gera sobreposição de
          cauda menor que os alvos (≈19%/39%). DECISÃO: manter ρ = 0,60 (valor-
          título da spec; Pearson/Spearman no alvo); sobreposição fica informativa
          (seria preciso uma cópula com dependência de cauda, não especificada).
    μ_r ajustado de 10,65 -> 10,66 para a mediana de renda passar o piso de R$42k.
    Em validar_inicializacao(), os indicadores são classificados como GATE
    (precisam passar) ou INFO (desvio documentado); 'aprovado' usa só os GATE.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import numpy as np


# ============================================================================
# Constantes de calibração (seção 4) — não mudam entre cenários
# ============================================================================

MORADORES_POR_FAMILIA = 2.79          # Censo 2022 (§4.0)

# --- Renda do trabalho: log-normal + cauda Pareto (§4.1) -------------------
MU_R = 10.66                          # média ~R$ 68.300/ano (10,65 da spec + nudge [D4])
SIGMA_R = 0.97                        # Gini renda ≈ 0,506
ALPHA_R = 1.5                         # expoente Pareto da renda (top 1%) — ver [D4](i)

# --- Patrimônio: log-normal correlacionado + cauda Pareto (§4.2) -----------
MU_P = 11.00                          # mediana ≈ R$ 60.000
SIGMA_P = 1.90                        # Gini patrimonial ≈ 0,82
RHO_RENDA_PATRIMONIO = 0.60           # correlação log-renda × log-patrimônio
ALPHA_P = 1.35                        # expoente Pareto do patrimônio — ver [D4](ii)

# x_min_p da cauda Pareto patrimonial (ver [D1]). Com o splice contínuo de
# inicializacao.py qualquer valor preserva continuidade; usamos o limiar empírico
# do top 1% patrimonial (R$ 2,3M, Monsieur-Lifestyle 2024), que é o que reproduz
# o alvo de §4.5 para a faixa 4 (% famílias > R$ 5M).
#   "empirico"   -> PARETO_X_MIN_P_EMPIRICO (default)
#   "p99_corpo"  -> exp(mu_p + 2,326*sigma_p) ≈ R$ 4,97M
PARETO_X_MIN_P_MODO = "empirico"
PARETO_X_MIN_P_EMPIRICO = 2_300_000.0
Z_P99 = 2.326                         # quantil 99% da Normal padrão

FRACAO_TOPO_PARETO = 0.01             # top 1% substituído pela cauda Pareto

# --- Faixas de patrimônio (§4.4 / §5.2) ------------------------------------
# Limites em R$ de 2026 entre faixas: 1↔2, 2↔3, 3↔4
LIMITES_FAIXA_INICIAL = np.array([50_000.0, 500_000.0, 5_000_000.0])
BANDA_HISTERESE = 0.10                # ±10% (§5.2)

# Retorno real por faixa: Normal(média, dp) truncada em [lo, hi]  (§4.4)
RETORNO_MEDIA_FAIXA = np.array([0.010, 0.030, 0.050, 0.050])
RETORNO_DP_FAIXA    = np.array([0.010, 0.015, 0.025, 0.025])
RETORNO_TRUNC_LO    = np.array([-0.02, -0.01, -0.01, -0.01])
RETORNO_TRUNC_HI    = np.array([ 0.03,  0.05,  0.11,  0.11])

# --- Propensão a consumir por faixa de decil de renda total (§4.3) ---------
# c_k ~ Uniform(lo, hi) para faixas: 1(D1-3) 2(D4-7) 3(D8-9) 4(D10) 5(top1%)
CONSUMO_UNIF_LO = np.array([0.97, 0.88, 0.75, 0.55, 0.30])
CONSUMO_UNIF_HI = np.array([1.00, 0.97, 0.88, 0.75, 0.55])

# --- Choque de emprego: cadeia de Markov (§5.3) ----------------------------
# P(desempregar | empregado) por grupo de decil de renda_trabalho_base
P_DEMITIR_D1_3 = 0.080
P_DEMITIR_D4_9 = 0.040
P_DEMITIR_D10  = 0.015
P_REEMPREGAR   = 0.50                 # duração esperada ≈ 2 anos

# Desemprego inicial por grupo de decil (§4.5)
U_INICIAL_D1_3 = 0.11
U_INICIAL_D4_9 = 0.06
U_INICIAL_D10  = 0.025

# --- Choque de educação (§5.4) ---------------------------------------------
P_EDU_D1_3 = 0.012
P_EDU_D4_6 = 0.015
P_EDU_D7_9 = 0.008
P_EDU_D10  = 0.002
EDU_GANHO_LO = 1.15
EDU_GANHO_HI = 1.35
MAX_CHOQUES_EDU = 3

# --- Choque de sucessão (§5.6) ---------------------------------------------
P_SUCESSAO = 0.03                     # ver [D2]
N_HERDEIROS_OPCOES = np.array([1, 2, 3, 4])

# --- Período da simulação (§2) ---------------------------------------------
ANO_INICIAL = 2026
ANO_FINAL = 2126
N_ANOS = ANO_FINAL - ANO_INICIAL + 1  # 101 pontos (2026..2126)

# --- Monte Carlo (§6.2) ----------------------------------------------------
N_RUNS = 30
SEED_BASE = 1000                      # seed = SEED_BASE + i

# --- Tolerâncias de validação da inicialização (§4.5) ----------------------
ALVOS_VALIDACAO = {
    "gini_renda_trabalho": (0.52, 0.02),
    "gini_patrimonio":     (0.82, 0.02),
    "mediana_renda":       (45_000.0, 0.10),   # faixa R$42-48k -> centro 45k ±10%
    "mediana_patrimonio":  (62_500.0, 0.15),   # faixa R$55-70k -> centro 62,5k ±15%
    # checagens de faixa/correlação são intervalos, tratadas à parte em inicializacao.py
}


# ============================================================================
# Cenário (seção 6) — parâmetros que variam entre execuções
# ============================================================================

@dataclass
class Cenario:
    """Conjunto de parâmetros de política/exógenos de uma execução (§6)."""
    id: str = "S0"
    nome: str = "baseline"

    n_familias: int = 1000
    g: float = 0.0                                  # crescimento real da renda (§5.1)

    # Vetores de retorno por faixa (default = calibração §4.4)
    retorno_media_faixa: np.ndarray = field(
        default_factory=lambda: RETORNO_MEDIA_FAIXA.copy())
    retorno_dp_faixa: np.ndarray = field(
        default_factory=lambda: RETORNO_DP_FAIXA.copy())

    # Política de transferência (§5.1)
    transferencia_base: float = 0.0                 # R$/mês per capita
    limiar: float = float("inf")                    # R$/mês per capita
    limiar_usa_renda_total: bool = False

    # Demais parâmetros de política (§6)
    alpha_seguro: float = 0.70                       # perda de renda no desemprego
    max_choques_edu: int = MAX_CHOQUES_EDU
    p_sucessao: float = P_SUCESSAO
    banda_histerese: float = BANDA_HISTERESE

    def to_dict(self) -> dict:
        """Serializável para params.json (§7.1)."""
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, np.ndarray):
                d[k] = v.tolist()
        return d


# ---- Conjunto mínimo de cenários (§6.1) -----------------------------------

def cenarios_base(n_familias: int = 1000) -> dict[str, Cenario]:
    """Retorna o dicionário S0–S7 da seção 6.1."""
    return {
        "S0": Cenario(id="S0", nome="baseline", n_familias=n_familias),
        "S1": Cenario(id="S1", nome="selic_baixa", n_familias=n_familias,
                      retorno_media_faixa=np.array([0.010, 0.030, 0.035, 0.035])),
        "S2": Cenario(id="S2", nome="renda_basica_universal", n_familias=n_familias,
                      transferencia_base=600.0, limiar=float("inf")),
        "S3": Cenario(id="S3", nome="renda_basica_focalizada", n_familias=n_familias,
                      transferencia_base=600.0, limiar=218.0,
                      limiar_usa_renda_total=True),
        "S4": Cenario(id="S4", nome="selic_baixa+renda_basica", n_familias=n_familias,
                      retorno_media_faixa=np.array([0.010, 0.030, 0.035, 0.035]),
                      transferencia_base=600.0, limiar=218.0,
                      limiar_usa_renda_total=True),
        "S5": Cenario(id="S5", nome="crescimento_alto", n_familias=n_familias,
                      g=0.02),
        "S6": Cenario(id="S6", nome="sem_sucessao", n_familias=n_familias,
                      p_sucessao=0.0),
        "S7": Cenario(id="S7", nome="sucessao_forte", n_familias=n_familias,
                      p_sucessao=0.05),
    }
