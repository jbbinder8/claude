"""
Inicialização do modelo (seção 4 da spec) e validação do passo zero (§4.5).

Toda a amostragem usa uma única instância `rng = numpy.random.default_rng(seed)`
propagada explicitamente (§6.2). Nenhuma chamada a numpy.random.* global.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.stats import truncnorm, norm

import parametros as P
import metricas as M


# ============================================================================
# Estado da simulação (atributos persistentes da família, §3)
# ============================================================================

@dataclass
class Estado:
    """Vetores de estado família × (instante corrente). Tudo 1-D de tamanho n."""
    renda_trabalho_base: np.ndarray   # R$/ano de 2026 (cresce só por educação)
    c_faixa_decil: np.ndarray         # [n, 5] propensões pré-sorteadas (fixo)
    retorno_real: np.ndarray          # taxa real por família (re-sorteia em transição)
    faixa_patrimonio: np.ndarray      # 0..3 (1..4 na spec), com histerese
    patrimonio: np.ndarray            # R$ de 2026
    status_emprego: np.ndarray        # True = empregado
    n_choques_edu: np.ndarray         # contador (<= max_choques_edu)
    # Auxiliares fixos para ancoragem de decil de emprego/educação:
    #   o grupo de decil é recomputado a cada ano a partir de renda_trabalho_base.

    @property
    def n(self) -> int:
        return self.patrimonio.size


# ============================================================================
# Amostragem auxiliar
# ============================================================================

def _pareto_quantil(u: np.ndarray, x_min: float, alpha: float) -> np.ndarray:
    """Quantil da Pareto tipo I: Q(u) = x_min · (1 − u)^(−1/α)."""
    return x_min * np.power(1.0 - u, -1.0 / alpha)


def _x_min_patrimonio() -> float:
    """x_min da cauda Pareto patrimonial — ver decisão [D1] em parametros.py."""
    if P.PARETO_X_MIN_P_MODO == "empirico":
        return P.PARETO_X_MIN_P_EMPIRICO
    # default "p99_corpo": continuidade exata com o P99 da log-normal
    return float(np.exp(P.MU_P + P.Z_P99 * P.SIGMA_P))


def _splice_pareto(valor_corpo: np.ndarray, ln_aux: np.ndarray,
                   mu: float, sigma: float, x_min: float, alpha: float
                   ) -> np.ndarray:
    """Splice contínuo corpo log-normal → cauda Pareto em `x_min`, preservando
    ranking (§4.2 passos 2 e 3, na versão sem descontinuidade — ver [D1]).

    Procedimento: todas as famílias cujo corpo log-normal excede `x_min` (fração
    de cauda q1 = 1 − Φ((ln x_min − μ)/σ)) são remapeadas para a Pareto condicional
    a `x > x_min`, no MESMO percentil-dentro-da-cauda. Assim:
      - a família exatamente no limiar recebe ≈ x_min (continuidade exata);
      - o ranking é preservado, propagando a correlação à cauda;
      - para a renda (x_min = P99 do corpo) isso recai em "substituir o top 1%",
        exatamente como na spec; para o patrimônio (x_min empírico = R$ 2,3M) a
        fração substituída é a massa da cauda log-normal acima de 2,3M (~2,7%).
    """
    n = valor_corpo.size
    resultado = valor_corpo.copy()

    q0 = float(norm.cdf((np.log(x_min) - mu) / sigma))   # massa do corpo abaixo de x_min
    na_cauda = valor_corpo > x_min
    if not na_cauda.any():
        return resultado

    # percentil global de cada família por ln_aux (ranking 0..n-1)
    ordem = np.argsort(ln_aux, kind="stable")
    rank = np.empty(n, dtype=np.int64)
    rank[ordem] = np.arange(n)
    p_global = (rank + 1.0) / (n + 1.0)

    idx = np.where(na_cauda)[0]
    w = (p_global[idx] - q0) / (1.0 - q0)        # percentil dentro da cauda
    w = np.clip(w, 1e-9, 1.0 - 1e-12)
    resultado[idx] = _pareto_quantil(w, x_min, alpha)
    return resultado


def amostrar_renda_patrimonio(rng: np.random.Generator, n: int
                              ) -> tuple[np.ndarray, np.ndarray]:
    """Amostragem conjunta renda–patrimônio (§4.2 passos 1–3).

    Retorna (renda_trabalho_base, patrimonio), ambos em R$ de 2026.
    """
    media = np.array([P.MU_R, P.MU_P])
    cov = np.array([
        [P.SIGMA_R ** 2,                       P.RHO_RENDA_PATRIMONIO * P.SIGMA_R * P.SIGMA_P],
        [P.RHO_RENDA_PATRIMONIO * P.SIGMA_R * P.SIGMA_P, P.SIGMA_P ** 2],
    ])
    aux = rng.multivariate_normal(media, cov, size=n)
    ln_renda_aux = aux[:, 0]
    ln_patr_aux = aux[:, 1]

    # Corpo log-normal
    renda = np.exp(ln_renda_aux)
    patr = np.exp(ln_patr_aux)

    # Cauda Pareto via splice contínuo (preserva ranking e a correlação na cauda)
    x_min_r = float(np.exp(P.MU_R + P.Z_P99 * P.SIGMA_R))   # = P99 do corpo
    renda = _splice_pareto(renda, ln_renda_aux, P.MU_R, P.SIGMA_R, x_min_r, P.ALPHA_R)
    patr = _splice_pareto(patr, ln_patr_aux, P.MU_P, P.SIGMA_P,
                          _x_min_patrimonio(), P.ALPHA_P)
    return renda, patr


def faixa_de_patrimonio(patrimonio: np.ndarray, limites: np.ndarray) -> np.ndarray:
    """Faixa 0..3 a partir do patrimônio (sem histerese; usada na inicialização)."""
    return np.digitize(patrimonio, limites).astype(np.int8)


def sortear_retorno_por_faixa(rng: np.random.Generator, faixa: np.ndarray,
                              media_faixa: np.ndarray, dp_faixa: np.ndarray
                              ) -> np.ndarray:
    """Retorno real por família, Normal(média_faixa, dp_faixa) truncada (§4.4).

    Vetorizado: usa scipy.stats.truncnorm com parâmetros por família. `faixa` em 0..3.
    Famílias com qualquer faixa são suportadas; o subconjunto a re-sortear pode ser
    passado já filtrado pelo chamador (dinâmica).
    """
    media = media_faixa[faixa]
    dp = dp_faixa[faixa]
    lo = P.RETORNO_TRUNC_LO[faixa]
    hi = P.RETORNO_TRUNC_HI[faixa]
    a = (lo - media) / dp
    b = (hi - media) / dp
    return truncnorm.rvs(a, b, loc=media, scale=dp, size=faixa.size,
                         random_state=rng)


def sortear_propensao(rng: np.random.Generator, n: int) -> np.ndarray:
    """Vetor c_faixa_decil_i de 5 propensões por família (§4.3). Shape [n, 5]."""
    u = rng.random((n, 5))
    return P.CONSUMO_UNIF_LO + u * (P.CONSUMO_UNIF_HI - P.CONSUMO_UNIF_LO)


def sortear_emprego_inicial(rng: np.random.Generator,
                            renda_base: np.ndarray) -> np.ndarray:
    """status_emprego(0) por grupo de decil de renda_base (§4.5).

    Retorna True = empregado. Probabilidade de estar desempregado calibrada por
    grupo: D1-3 ~11%, D4-9 ~6%, D10 ~2,5%.
    """
    grupo = M.grupo_decil_emprego(renda_base)   # 0=D1-3,1=D4-6,2=D7-9,3=D10
    u_alvo = np.empty(renda_base.size)
    u_alvo[grupo == 0] = P.U_INICIAL_D1_3
    u_alvo[(grupo == 1) | (grupo == 2)] = P.U_INICIAL_D4_9
    u_alvo[grupo == 3] = P.U_INICIAL_D10
    desempregado = rng.random(renda_base.size) < u_alvo
    return ~desempregado


# ============================================================================
# Inicialização completa
# ============================================================================

def inicializar(cenario: P.Cenario, seed: int) -> Estado:
    """Constrói o estado em 2026 conforme seção 4."""
    rng = np.random.default_rng(seed)
    n = cenario.n_familias

    renda_base, patrimonio = amostrar_renda_patrimonio(rng, n)
    c_faixa = sortear_propensao(rng, n)
    faixa = faixa_de_patrimonio(patrimonio, P.LIMITES_FAIXA_INICIAL)
    retorno = sortear_retorno_por_faixa(
        rng, faixa, cenario.retorno_media_faixa, cenario.retorno_dp_faixa)
    status = sortear_emprego_inicial(rng, renda_base)
    n_edu = np.zeros(n, dtype=np.int16)

    return Estado(
        renda_trabalho_base=renda_base,
        c_faixa_decil=c_faixa,
        retorno_real=retorno,
        faixa_patrimonio=faixa,
        patrimonio=patrimonio,
        status_emprego=status,
        n_choques_edu=n_edu,
    )


# ============================================================================
# Validação do passo zero (§4.5)
# ============================================================================

def validar_inicializacao(estado: Estado) -> dict:
    """Calcula os indicadores de 2026 e compara com os alvos da §4.5.

    Retorna um dict com {indicador: {valor, alvo, ok}} e a chave 'aprovado'.
    """
    renda = estado.renda_trabalho_base
    patr = estado.patrimonio

    ln_r = np.log(renda)
    ln_p = np.log(np.maximum(patr, 1.0))

    pearson = float(np.corrcoef(ln_r, ln_p)[0, 1])
    spearman = float(np.corrcoef(M.decil(renda), M.decil(patr))[0, 1])

    # sobreposição de topos
    n = renda.size
    def _frac_overlap_top(frac):
        k = max(1, int(round(frac * n)))
        top_r = set(np.argpartition(renda, n - k)[n - k:].tolist())
        top_p = set(np.argpartition(patr, n - k)[n - k:].tolist())
        return len(top_r & top_p) / k
    overlap_top10 = _frac_overlap_top(0.10)
    overlap_top1 = _frac_overlap_top(0.01)

    frac_faixa1 = float(np.mean(patr < P.LIMITES_FAIXA_INICIAL[0]))
    frac_faixa4 = float(np.mean(patr > P.LIMITES_FAIXA_INICIAL[2]))
    desemprego = float(np.mean(~estado.status_emprego))

    def _check(valor, alvo, tol_rel=None, tol_abs=None):
        if tol_rel is not None:
            return abs(valor - alvo) <= tol_rel * alvo
        return abs(valor - alvo) <= tol_abs

    # tipo: "gate" = precisa passar para aprovar; "info" = desvio documentado [D4]
    ind = {}

    def add(nome, valor, alvo, ok, tipo, nota=""):
        ind[nome] = {"valor": valor, "alvo": alvo, "ok": bool(ok),
                     "tipo": tipo, "nota": nota}

    g_renda = M.gini(renda)
    add("gini_renda_trabalho", g_renda, "0,52 ±0,02",
        _check(g_renda, 0.52, tol_abs=0.02), "gate")

    g_patr = M.gini(patr)
    add("gini_patrimonio", g_patr, "0,82 ±0,02",
        _check(g_patr, 0.82, tol_abs=0.02), "gate")

    # Bandas com as tolerâncias que a §4.5 define (renda ±10%, patrimônio ±15%)
    med_r = float(np.median(renda))
    add("mediana_renda", med_r, "R$42-48k ±10%", 42_000 * 0.90 <= med_r <= 48_000 * 1.10, "gate")

    med_p = float(np.median(patr))
    add("mediana_patrimonio", med_p, "R$55-70k ±15%", 55_000 * 0.85 <= med_p <= 70_000 * 1.15, "gate")

    razao_med = M.razao_media_top10_bottom40(renda)
    add("razao_media_top10_bottom40", razao_med, "11-16x",
        11 <= razao_med <= 16, "gate")

    add("frac_faixa1", frac_faixa1, "0,45-0,55", 0.45 <= frac_faixa1 <= 0.55, "gate")
    add("desemprego_inicial", desemprego, "0,05-0,10", 0.05 <= desemprego <= 0.10, "gate")
    add("pearson_ln", pearson, "0,55-0,65", 0.55 <= pearson <= 0.65, "gate")
    add("spearman", spearman, "0,55-0,68", 0.55 <= spearman <= 0.68, "gate")

    # --- Informativos: desvios documentados em [D4] -------------------------
    s1r = M.top_share(renda, 0.01)
    add("share_top1_renda", s1r, "25-30%*", 0.25 <= s1r <= 0.30, "info",
        "[D4](i) priorizou Gini PNAD; ~14% e' o consistente c/ Gini 0,52")

    s1p = M.top_share(patr, 0.01)
    add("share_top1_patrimonio", s1p, "40-50%*", 0.40 <= s1p <= 0.50, "info",
        "[D4](ii) priorizou Gini patr; conflita c/ faixa4")

    add("frac_faixa4", frac_faixa4, "0,004-0,006*", 0.004 <= frac_faixa4 <= 0.006,
        "info", "[D4](ii) inconsistente c/ share top1 patr p/ lognormal+Pareto unico")

    add("overlap_top10", overlap_top10, ">=0,50*", overlap_top10 >= 0.50, "info",
        "[D4](iii) limite da copula gaussiana p/ Pearson no alvo")
    add("overlap_top1", overlap_top1, ">=0,25*", overlap_top1 >= 0.25, "info",
        "[D4](iii) idem")

    gates = {k: v for k, v in ind.items() if v["tipo"] == "gate"}
    aprovado = all(v["ok"] for v in gates.values())
    return {"indicadores": ind, "aprovado": aprovado}


def imprimir_validacao(rel: dict) -> None:
    """Imprime o relatório de validação. Alvos com * são informativos ([D4])."""
    print(f"{'indicador':<28} {'valor':>11}  {'alvo':<14} {'tipo':<5} ok")
    print("-" * 70)
    for nome, d in rel["indicadores"].items():
        v = d["valor"]
        vs = f"{v:,.4f}" if abs(v) < 100 else f"{v:,.0f}"
        marca = "OK" if d["ok"] else ("--" if d["tipo"] == "info" else "XX")
        print(f"{nome:<28} {vs:>11}  {d['alvo']:<14} {d['tipo']:<5} {marca}")
    print("-" * 70)
    print(f"APROVADO (gates): {rel['aprovado']}   (* = informativo, ver [D4])")
