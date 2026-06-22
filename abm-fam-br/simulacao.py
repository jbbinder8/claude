"""
Loop de simulação e Monte Carlo (seção 6 da spec).

`simular_run` roda um cenário com uma semente e devolve as séries anuais de
métricas (§7.2) e os artefatos para figuras/outputs (§7.1, §7.3). `simular_cenario`
agrega N_RUNS repetições com média e IC95% (§6.2).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import parametros as P
import metricas as M
import inicializacao as I
from dinamica import passo_ano, FluxosAno

ANOS_SNAPSHOT = (2026, 2076, 2126)          # distribuições (§7.3, figs 9-14, 18)
ANOS_DECADA = tuple(range(P.ANO_INICIAL, P.ANO_FINAL + 1, 10))  # mobilidade
N_TRAJETORIAS = 10                          # famílias acompanhadas (§7.3, fig 19)


def _metricas_ano(ano, patrimonio, fluxos: FluxosAno, status_emprego,
                  retorno_real, faixa, n_edu) -> dict:
    """Métricas registradas anualmente (§7.2)."""
    rt = fluxos.renda_total
    d = {
        "ano": ano,
        "gini_patrimonio": M.gini(patrimonio),
        "gini_renda_total": M.gini(rt),
        "gini_renda_trabalho": M.gini(fluxos.renda_trabalho),
        "top01_patrimonio": M.top_share(patrimonio, 0.001),
        "top1_patrimonio": M.top_share(patrimonio, 0.01),
        "top5_patrimonio": M.top_share(patrimonio, 0.05),
        "top10_patrimonio": M.top_share(patrimonio, 0.10),
        "bottom50_patrimonio": M.bottom_share(patrimonio, 0.50),
        "top1_renda_total": M.top_share(rt, 0.01),
        "top10_renda_total": M.top_share(rt, 0.10),
        "palma_patrimonio": M.razao_palma(patrimonio),
        "palma_renda": M.razao_palma(rt),
        "razao_top1_bottom50_patr": M.razao_top1_bottom50(patrimonio),
        "patrimonio_medio": float(patrimonio.mean()),
        "patrimonio_mediano": float(np.median(patrimonio)),
        "desemprego": float(np.mean(~status_emprego)),
        "frac_com_edu": float(np.mean(n_edu > 0)),
        "retorno_medio_agregado": float(
            np.average(retorno_real, weights=np.maximum(patrimonio, 1e-9))),
        "renda_trabalho_agreg": float(fluxos.renda_trabalho.sum()),
        "renda_patrimonio_agreg": float(fluxos.retorno_patrimonio.sum()),
        "transferencia_total": fluxos.transferencia_total,
    }
    for q, v in M.percentis(patrimonio).items():
        d[f"patr_p{q}"] = v
    for q, v in M.percentis(rt).items():
        d[f"rendatot_p{q}"] = v
    for k in range(4):
        d[f"frac_faixa{k+1}"] = float(np.mean(faixa == k))
    # decomposição da variância do crescimento patrimonial (§7.3, fig 20; ver [D5])
    dec = M.decomposicao_variancia_crescimento(
        fluxos.dpatrimonio, fluxos.retorno_patrimonio, fluxos.renda_trabalho,
        fluxos.transferencia, fluxos.poupanca, fluxos.renda_total)
    for c, v in dec.items():
        d[f"vardec_{c}"] = v
    return d


def simular_run(cen: P.Cenario, seed: int, coletar_painel: bool = False) -> dict:
    """Roda um cenário do início ao fim. Retorna séries + artefatos para figuras."""
    est = I.inicializar(cen, seed)
    rng = np.random.default_rng(seed + 1)    # rng da dinâmica, distinto do de init

    # famílias acompanhadas: amostradas por percentil de patrimônio inicial
    ordem0 = np.argsort(est.patrimonio)
    idx_traj = ordem0[np.linspace(0, est.n - 1, N_TRAJETORIAS).astype(int)]

    linhas = []
    snapshots: dict[int, dict] = {}
    decis_decada: dict[int, np.ndarray] = {}
    traj = {"ano": [], **{f"fam{j}": [] for j in range(N_TRAJETORIAS)}}
    painel = [] if coletar_painel else None

    for ano in range(P.ANO_INICIAL, P.ANO_FINAL + 1):
        patr_ini = est.patrimonio.copy()
        faixa_ini = est.faixa_patrimonio.copy()
        retorno_ini = est.retorno_real.copy()
        fluxos = passo_ano(est, ano, cen, rng)

        linhas.append(_metricas_ano(
            ano, patr_ini, fluxos, est.status_emprego, retorno_ini,
            faixa_ini, est.n_choques_edu))

        if ano in ANOS_SNAPSHOT:
            snapshots[ano] = {
                "patrimonio": patr_ini.copy(),
                "renda_total": fluxos.renda_total.copy(),
                "renda_trabalho": fluxos.renda_trabalho.copy(),
            }
        if ano in ANOS_DECADA:
            decis_decada[ano] = M.decil(patr_ini)

        traj["ano"].append(ano)
        for j, fam in enumerate(idx_traj):
            traj[f"fam{j}"].append(float(patr_ini[fam]))

        if coletar_painel:
            painel.append(pd.DataFrame({
                "ano": ano,
                "familia": np.arange(est.n),
                "patrimonio": patr_ini,
                "renda_total": fluxos.renda_total,
                "renda_trabalho": fluxos.renda_trabalho,
                "retorno_patrimonio": fluxos.retorno_patrimonio,
                "faixa": faixa_ini,
                "desempregado": fluxos.desempregado,
            }))

    return {
        "series": pd.DataFrame(linhas).set_index("ano"),
        "snapshots": snapshots,
        "decis_decada": decis_decada,
        "trajetorias": pd.DataFrame(traj).set_index("ano"),
        "n_edu_final": est.n_choques_edu.copy(),
        "retorno_final": est.retorno_real.copy(),
        "faixa_final": est.faixa_patrimonio.copy(),
        "painel": (pd.concat(painel, ignore_index=True)
                   if coletar_painel else None),
    }


def simular_cenario(cen: P.Cenario, n_runs: int = P.N_RUNS,
                    seed_base: int = P.SEED_BASE,
                    coletar_painel_run0: bool = True) -> dict:
    """Monte Carlo de um cenário (§6.2): média e IC95% das séries entre runs.

    Mantém os artefatos do run 0 (snapshots, mobilidade, trajetórias, painel)
    para as figuras por cenário.
    """
    runs = []
    for i in range(n_runs):
        runs.append(simular_run(cen, seed_base + i,
                                coletar_painel=(coletar_painel_run0 and i == 0)))

    painel_series = np.stack([r["series"].values for r in runs])
    media = painel_series.mean(axis=0)
    sem = painel_series.std(axis=0, ddof=1) / np.sqrt(n_runs)
    cols, idx = runs[0]["series"].columns, runs[0]["series"].index
    return {
        "media": pd.DataFrame(media, index=idx, columns=cols),
        "ic95": pd.DataFrame(1.96 * sem, index=idx, columns=cols),
        "run0": runs[0],
        "n_runs": n_runs,
    }
