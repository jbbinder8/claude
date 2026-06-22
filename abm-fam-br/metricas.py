"""
Métricas de desigualdade e distribuição (seção 7.2 da spec).

Todas as funções operam sobre arrays numpy 1-D (uma observação por família) e
são puras/vetorizadas.
"""

from __future__ import annotations

import numpy as np


def gini(x: np.ndarray) -> float:
    """Coeficiente de Gini de um array não-negativo.

    Usa a fórmula da diferença média absoluta normalizada, calculada em O(n log n)
    via ordenação:  G = (2·Σ i·x_(i)) / (n·Σ x) − (n+1)/n .
    Valores são deslocados para garantir não-negatividade (patrimônio tem piso 0,
    mas a guarda evita NaN se algum cenário gerar negativos).
    """
    x = np.asarray(x, dtype=float)
    n = x.size
    if n == 0:
        return float("nan")
    if np.amin(x) < 0:
        x = x - np.amin(x)
    s = x.sum()
    if s == 0:
        return 0.0
    xs = np.sort(x)
    idx = np.arange(1, n + 1)
    return float((2.0 * np.sum(idx * xs)) / (n * s) - (n + 1.0) / n)


def top_share(x: np.ndarray, frac: float) -> float:
    """Fração do total detida pelas `frac` (ex.: 0,01) maiores observações."""
    x = np.asarray(x, dtype=float)
    s = x.sum()
    if s <= 0:
        return float("nan")
    n = x.size
    k = max(1, int(round(frac * n)))
    maiores = np.partition(x, n - k)[n - k:]
    return float(maiores.sum() / s)


def bottom_share(x: np.ndarray, frac: float) -> float:
    """Fração do total detida pelas `frac` menores observações."""
    x = np.asarray(x, dtype=float)
    s = x.sum()
    if s <= 0:
        return float("nan")
    n = x.size
    k = max(1, int(round(frac * n)))
    menores = np.partition(x, k - 1)[:k]
    return float(menores.sum() / s)


def razao_palma(x: np.ndarray) -> float:
    """Razão de Palma: share do top 10% / share do bottom 40%."""
    b40 = bottom_share(x, 0.40)
    t10 = top_share(x, 0.10)
    if b40 <= 0:
        return float("nan")
    return float(t10 / b40)


def razao_media_top10_bottom40(x: np.ndarray) -> float:
    """Razão da MÉDIA do top 10% pela MÉDIA do bottom 40% (§4.0/§4.5; alvo 13,4×).

    Diferente da razão de Palma (que é razão de SHARES, ~3,3): aqui é a razão dos
    rendimentos médios, como nas tabelas da PNAD citadas na spec.
    """
    x = np.asarray(x, dtype=float)
    n = x.size
    k10 = max(1, int(round(0.10 * n)))
    k40 = max(1, int(round(0.40 * n)))
    media_top10 = np.partition(x, n - k10)[n - k10:].mean()
    media_bot40 = np.partition(x, k40 - 1)[:k40].mean()
    if media_bot40 <= 0:
        return float("nan")
    return float(media_top10 / media_bot40)


def razao_top1_bottom50(x: np.ndarray) -> float:
    t1 = top_share(x, 0.01)
    b50 = bottom_share(x, 0.50)
    if b50 <= 0:
        return float("nan")
    return float(t1 / b50)


PERCENTIS_PADRAO = [5, 10, 25, 50, 75, 90, 95, 99, 99.9]


def percentis(x: np.ndarray, qs: list[float] | None = None) -> dict[float, float]:
    """Percentis de `x` (§7.2). Chaves são os percentis em 0–100."""
    if qs is None:
        qs = PERCENTIS_PADRAO
    vals = np.percentile(np.asarray(x, dtype=float), qs)
    return {q: float(v) for q, v in zip(qs, vals)}


def faixa_decil_renda_total(renda_total: np.ndarray) -> np.ndarray:
    """Mapeia cada família à faixa de decil de renda total (§4.3): índices 0–4.

    Faixas: 0=D1-3, 1=D4-7, 2=D8-9, 3=D10(excl. top1%), 4=top1%.
    Empates resolvidos por posição de ranking (argsort estável) para evitar que
    muitos valores idênticos distorçam os cortes.
    """
    n = renda_total.size
    # rank 0..n-1 (0 = menor); usa argsort duplo para ranking denso por posição
    ordem = np.argsort(renda_total, kind="stable")
    rank = np.empty(n, dtype=np.int64)
    rank[ordem] = np.arange(n)
    pct = rank / n                       # posição relativa em [0,1)

    faixa = np.empty(n, dtype=np.int8)
    faixa[pct < 0.30] = 0                # decil 1-3
    faixa[(pct >= 0.30) & (pct < 0.70)] = 1  # decil 4-7
    faixa[(pct >= 0.70) & (pct < 0.90)] = 2  # decil 8-9
    faixa[pct >= 0.90] = 3               # decil 10
    faixa[pct >= 0.99] = 4               # top 1%
    return faixa


def grupo_decil_emprego(renda_base: np.ndarray) -> np.ndarray:
    """Grupos de decil de renda_trabalho_base para emprego/educação (§5.3/§5.4).

    Retorna índices: 0 = D1-3, 1 = D4-6, 2 = D7-9, 3 = D10.
    (Educação usa os 4 grupos; emprego agrupa D4-9 — feito no chamador.)
    """
    n = renda_base.size
    ordem = np.argsort(renda_base, kind="stable")
    rank = np.empty(n, dtype=np.int64)
    rank[ordem] = np.arange(n)
    pct = rank / n

    grupo = np.empty(n, dtype=np.int8)
    grupo[pct < 0.30] = 0                # D1-3
    grupo[(pct >= 0.30) & (pct < 0.60)] = 1  # D4-6
    grupo[(pct >= 0.60) & (pct < 0.90)] = 2  # D7-9
    grupo[pct >= 0.90] = 3               # D10
    return grupo


def decil(x: np.ndarray) -> np.ndarray:
    """Decil de cada observação (1..10) por ranking; usado em mobilidade."""
    n = x.size
    ordem = np.argsort(x, kind="stable")
    rank = np.empty(n, dtype=np.int64)
    rank[ordem] = np.arange(n)
    return np.minimum((rank * 10) // n, 9).astype(np.int8) + 1


def matriz_transicao(decil_ini: np.ndarray, decil_fim: np.ndarray,
                     k: int = 10) -> np.ndarray:
    """Matriz k×k de transição entre decis (linhas=origem, colunas=destino).

    Cada linha é normalizada para somar 1 (probabilidade condicional de destino
    dado o decil de origem). Usada nos heatmaps de mobilidade (§7.3, fig.15).
    """
    m = np.zeros((k, k), dtype=float)
    np.add.at(m, (decil_ini - 1, decil_fim - 1), 1.0)
    soma = m.sum(axis=1, keepdims=True)
    soma[soma == 0] = 1.0
    return m / soma


def decomposicao_variancia_crescimento(dpatr, retorno_patr, renda_trabalho,
                                       transferencia, poupanca, renda_total
                                       ) -> dict:
    """Decompõe a variância cross-section do crescimento patrimonial Δw do ano.

    NOTA DE IMPLEMENTAÇÃO [D5]: a spec (§7.3, fig.20) pede a decomposição em
    "retorno desigual / poupança desigual / desemprego / educação". Como a
    poupança já EMBUTE a renda do patrimônio (poupança = (1−c)·renda_total e
    renda_total inclui o retorno), não há identidade aditiva limpa com aquelas 4
    rubricas. Usamos a identidade exata Δw = comp_retorno + comp_trabalho +
    comp_sucessao, com:
        taxa_poup       = poupança / renda_total
        comp_retorno    = taxa_poup · retorno_patrimônio        (retorno desigual)
        comp_trabalho   = taxa_poup · (renda_trabalho + transf.) (trabalho×propensão;
                          embute desemprego e educação, que atuam via renda_trab)
        comp_sucessao   = Δw − comp_retorno − comp_trabalho     (sucessão + piso 0)
    Contribuição de cada componente = Cov(comp_c, Δw)/Var(Δw); soma = 1 por
    construção. Desemprego e educação aparecem em figuras próprias (figs 6 e 24).
    """
    var = float(np.var(dpatr))
    if var <= 0:
        return {"retorno": np.nan, "trabalho": np.nan, "sucessao": np.nan}
    rt_safe = np.where(renda_total > 0, renda_total, 1.0)
    taxa_poup = poupanca / rt_safe
    comp_retorno = taxa_poup * retorno_patr
    comp_trabalho = taxa_poup * (renda_trabalho + transferencia)
    comp_sucessao = dpatr - comp_retorno - comp_trabalho
    cov = lambda a: float(np.cov(a, dpatr, ddof=0)[0, 1] / var)
    return {
        "retorno": cov(comp_retorno),
        "trabalho": cov(comp_trabalho),
        "sucessao": cov(comp_sucessao),
    }
