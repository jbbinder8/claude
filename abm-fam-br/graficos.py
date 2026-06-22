"""
Visualizações (seção 7.3–7.5 da spec).

`figuras_cenario` gera as figuras 1–25 de um cenário (em output/<id>/figs/).
`figuras_comparativas` gera as figuras 26–34 (em output/comparativos/).

Padrões (§7.5): matplotlib/Agg, 150 dpi, PNG, paleta viridis/tab10, bandas IC95%
translúcidas, eixos rotulados. Plotly (sankey interativo) é opcional e não é usado
aqui — a fig.16 usa uma aproximação aluvial em matplotlib.
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import metricas as M

DPI = 150
COR = plt.get_cmap("tab10").colors
ANOS_SNAP = (2026, 2076, 2126)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ax(titulo, xlabel, ylabel, figsize=(8, 5)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_title(titulo)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    return fig, ax


def _salvar(fig, outdir, nome):
    os.makedirs(outdir, exist_ok=True)
    caminho = os.path.join(outdir, nome)
    fig.tight_layout()
    fig.savefig(caminho, dpi=DPI)
    plt.close(fig)
    return caminho


def _banda(ax, media, ic, col, label, cor):
    x = media.index
    ax.plot(x, media[col], color=cor, label=label, lw=1.8)
    ax.fill_between(x, media[col] - ic[col], media[col] + ic[col],
                    color=cor, alpha=0.20)


def _lorenz(x):
    xs = np.sort(np.asarray(x, dtype=float))
    xs = xs - min(0.0, xs.min())
    cum = np.cumsum(xs)
    cum = cum / cum[-1] if cum[-1] > 0 else cum
    pop = np.linspace(0, 1, len(xs) + 1)
    return pop, np.concatenate([[0.0], cum])


# ---------------------------------------------------------------------------
# Figuras por cenário (1–25)
# ---------------------------------------------------------------------------

def figuras_cenario(res: dict, cen, outdir: str) -> list[str]:
    media, ic, run0 = res["media"], res["ic95"], res["run0"]
    figs_dir = os.path.join(outdir, "figs")
    saidas = []

    # 1. Gini patrimonial e Gini de renda total
    fig, ax = _ax(f"[{cen.id}] Gini patrimonial e de renda total", "ano", "Gini")
    _banda(ax, media, ic, "gini_patrimonio", "Gini patrimônio", COR[0])
    _banda(ax, media, ic, "gini_renda_total", "Gini renda total", COR[1])
    ax.legend(); saidas.append(_salvar(fig, figs_dir, "01_gini.png"))

    # 2. Top shares e bottom 50%
    fig, ax = _ax(f"[{cen.id}] Top shares e bottom 50% (patrimônio)", "ano", "share")
    _banda(ax, media, ic, "top01_patrimonio", "top 0,1%", COR[3])
    _banda(ax, media, ic, "top1_patrimonio", "top 1%", COR[0])
    _banda(ax, media, ic, "top10_patrimonio", "top 10%", COR[2])
    _banda(ax, media, ic, "bottom50_patrimonio", "bottom 50%", COR[4])
    ax.legend(); saidas.append(_salvar(fig, figs_dir, "02_top_shares.png"))

    # 3. Percentis patrimoniais (log)
    fig, ax = _ax(f"[{cen.id}] Percentis patrimoniais", "ano", "R$ (log)")
    for p, c in [("patr_p10", COR[4]), ("patr_p50", COR[0]),
                 ("patr_p90", COR[2]), ("patr_p99", COR[3])]:
        ax.plot(media.index, media[p], label=p.replace("patr_p", "P"), color=c)
    ax.set_yscale("log"); ax.legend(); saidas.append(_salvar(fig, figs_dir, "03_percentis_patr.png"))

    # 4. Razão Palma e top1/bottom50
    fig, ax = _ax(f"[{cen.id}] Razão de Palma e top1%/bottom50% (patrimônio)", "ano", "razão")
    _banda(ax, media, ic, "palma_patrimonio", "Palma (patr.)", COR[0])
    _banda(ax, media, ic, "razao_top1_bottom50_patr", "top1%/bottom50%", COR[3])
    ax.legend(); saidas.append(_salvar(fig, figs_dir, "04_palma.png"))

    # 5. % famílias em cada faixa (stacked area)
    fig, ax = _ax(f"[{cen.id}] Composição por faixa de patrimônio", "ano", "fração das famílias")
    fr = [media[f"frac_faixa{k+1}"] for k in range(4)]
    ax.stackplot(media.index, *fr, labels=[f"faixa {k+1}" for k in range(4)],
                 colors=[COR[i] for i in range(4)], alpha=0.85)
    ax.legend(loc="upper right"); ax.set_ylim(0, 1)
    saidas.append(_salvar(fig, figs_dir, "05_faixas.png"))

    # 6. Taxa de desemprego
    fig, ax = _ax(f"[{cen.id}] Taxa de desemprego agregada", "ano", "taxa")
    _banda(ax, media, ic, "desemprego", "desemprego", COR[1])
    ax.axhline(0.079, ls="--", color="gray", label="PNAD 2024 (7,9%)")
    ax.legend(); saidas.append(_salvar(fig, figs_dir, "06_desemprego.png"))

    # 7. Razão renda do patrimônio / renda do trabalho (r vs g)
    fig, ax = _ax(f"[{cen.id}] Renda do patrimônio / renda do trabalho", "ano", "razão agregada")
    razao = media["renda_patrimonio_agreg"] / media["renda_trabalho_agreg"]
    ax.plot(media.index, razao, color=COR[5])
    saidas.append(_salvar(fig, figs_dir, "07_r_vs_g.png"))

    # 8. Retorno real agregado realizado vs alvo
    fig, ax = _ax(f"[{cen.id}] Retorno real agregado realizado", "ano", "retorno a.a.")
    _banda(ax, media, ic, "retorno_medio_agregado", "realizado", COR[2])
    alvo = float(np.average(cen.retorno_media_faixa))
    ax.axhline(alvo, ls="--", color="gray", label=f"média das faixas ({alvo:.1%})")
    ax.legend(); saidas.append(_salvar(fig, figs_dir, "08_retorno.png"))

    # 9–10. Histograma+KDE de log(patrimônio) e log(renda total), 3 anos
    for nfig, chave, nome in [("09", "patrimonio", "patrimônio"),
                              ("10", "renda_total", "renda total")]:
        fig, ax = _ax(f"[{cen.id}] Distribuição de log({nome})", f"log10({nome})", "densidade")
        for i, ano in enumerate(ANOS_SNAP):
            v = run0["snapshots"][ano][chave]
            v = np.log10(np.maximum(v, 1.0))
            ax.hist(v, bins=50, density=True, alpha=0.4, color=COR[i], label=str(ano))
        ax.legend(); saidas.append(_salvar(fig, figs_dir, f"{nfig}_dist_{chave}.png"))

    # 11–12. Curvas de Lorenz (patrimônio, renda), 3 anos
    for nfig, chave, nome in [("11", "patrimonio", "patrimônio"),
                              ("12", "renda_total", "renda total")]:
        fig, ax = _ax(f"[{cen.id}] Curva de Lorenz — {nome}", "população acumulada", "share acumulado")
        ax.plot([0, 1], [0, 1], ls=":", color="gray")
        for i, ano in enumerate(ANOS_SNAP):
            pop, cum = _lorenz(run0["snapshots"][ano][chave])
            ax.plot(pop, cum, color=COR[i], label=str(ano))
        ax.legend(); saidas.append(_salvar(fig, figs_dir, f"{nfig}_lorenz_{chave}.png"))

    # 13. Pareto plot (log-log da cauda) do patrimônio em 2126
    fig, ax = _ax(f"[{cen.id}] Pareto plot — cauda do patrimônio 2126", "log10 patrimônio", "log10 P(X>x)")
    v = np.sort(run0["snapshots"][2126]["patrimonio"])
    v = v[v > np.percentile(v, 90)]
    surv = 1.0 - np.arange(len(v)) / len(v)
    ax.plot(np.log10(v), np.log10(surv), ".", ms=3, color=COR[0])
    saidas.append(_salvar(fig, figs_dir, "13_pareto_patr.png"))

    # 14. Composição da distribuição por faixa em 2126 (stacked bar do patrimônio total)
    fig, ax = _ax(f"[{cen.id}] Patrimônio total por faixa (2126)", "faixa", "fração do patrimônio total")
    patr = run0["snapshots"][2126]["patrimonio"]
    faixa = run0["faixa_final"]
    tot = patr.sum()
    fr = [patr[faixa == k].sum() / tot for k in range(4)]
    ax.bar([f"faixa {k+1}" for k in range(4)], fr, color=[COR[i] for i in range(4)])
    saidas.append(_salvar(fig, figs_dir, "14_patr_por_faixa.png"))

    # 15. Heatmaps de matriz de transição de decis (3 janelas)
    janelas = [(2026, 2076), (2076, 2126), (2026, 2126)]
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, (a0, a1) in zip(axs, janelas):
        m = M.matriz_transicao(run0["decis_decada"][a0], run0["decis_decada"][a1])
        im = ax.imshow(m, cmap="viridis", origin="lower", vmin=0, vmax=m.max())
        ax.set_title(f"{a0}→{a1}"); ax.set_xlabel("decil destino"); ax.set_ylabel("decil origem")
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle(f"[{cen.id}] Matrizes de transição entre decis patrimoniais")
    saidas.append(_salvar(fig, figs_dir, "15_transicao.png"))

    # 16. Aluvial (aprox.) da mobilidade entre faixas ao longo das décadas
    fig, ax = _ax(f"[{cen.id}] Mobilidade entre faixas (composição decadal)", "ano", "fração")
    anos_dec = sorted(run0["decis_decada"])
    # reconstrói faixa por década a partir do painel não disponível; usa fração por faixa da série
    fr = [media[f"frac_faixa{k+1}"].reindex(anos_dec) for k in range(4)]
    ax.stackplot(anos_dec, *fr, labels=[f"faixa {k+1}" for k in range(4)],
                 colors=[COR[i] for i in range(4)], alpha=0.85)
    ax.legend(loc="upper right"); ax.set_ylim(0, 1)
    saidas.append(_salvar(fig, figs_dir, "16_aluvial_faixas.png"))

    # 17. Boxplot do patrimônio 2126 por decil de renda inicial
    fig, ax = _ax(f"[{cen.id}] Patrimônio 2126 por decil de renda inicial", "decil renda 2026", "patrimônio 2126 (log)")
    dec_renda0 = M.decil(run0["snapshots"][2026]["renda_total"])
    patr2126 = run0["snapshots"][2126]["patrimonio"]
    dados = [np.log10(np.maximum(patr2126[dec_renda0 == d], 1.0)) for d in range(1, 11)]
    ax.boxplot(dados, showfliers=False)
    saidas.append(_salvar(fig, figs_dir, "17_box_patr_por_decil.png"))

    # 18. Scatter renda × patrimônio (2026 e 2126), log-log
    fig, axs = plt.subplots(1, 2, figsize=(13, 5.5))
    for ax, ano in zip(axs, (2026, 2126)):
        r = run0["snapshots"][ano]["renda_total"]
        p = run0["snapshots"][ano]["patrimonio"]
        lr, lp = np.log10(np.maximum(r, 1.0)), np.log10(np.maximum(p, 1.0))
        ax.scatter(lr, lp, s=5, alpha=0.3, color=COR[0])
        per = float(np.corrcoef(lr, lp)[0, 1])
        spe = float(np.corrcoef(M.decil(r), M.decil(p))[0, 1])
        ax.set_title(f"{ano} | Pearson={per:.2f} Spearman={spe:.2f}")
        ax.set_xlabel("log10 renda total"); ax.set_ylabel("log10 patrimônio")
    fig.suptitle(f"[{cen.id}] Renda × patrimônio")
    saidas.append(_salvar(fig, figs_dir, "18_scatter_renda_patr.png"))

    # 18b. Heatmap conjunto de decis renda × patrimônio em 2026
    fig, ax = _ax(f"[{cen.id}] Decis renda × patrimônio (2026)", "decil renda", "decil patrimônio")
    dr = M.decil(run0["snapshots"][2026]["renda_total"])
    dp = M.decil(run0["snapshots"][2026]["patrimonio"])
    h = np.zeros((10, 10))
    np.add.at(h, (dp - 1, dr - 1), 1.0)
    im = ax.imshow(h, cmap="viridis", origin="lower"); fig.colorbar(im, ax=ax)
    saidas.append(_salvar(fig, figs_dir, "18b_heatmap_decis.png"))

    # 19. Trajetórias individuais de 10 famílias
    fig, ax = _ax(f"[{cen.id}] Trajetórias de 10 famílias (por percentil inicial)", "ano", "patrimônio (log)")
    for j in range(run0["trajetorias"].shape[1]):
        ax.plot(run0["trajetorias"].index, np.maximum(run0["trajetorias"].iloc[:, j], 1.0),
                lw=1, alpha=0.8)
    ax.set_yscale("log"); saidas.append(_salvar(fig, figs_dir, "19_trajetorias.png"))

    # 20. Decomposição da variância do crescimento patrimonial (stacked area)
    fig, ax = _ax(f"[{cen.id}] Decomposição da variância do crescimento (Δpatrimônio)", "ano", "share da variância")
    comps = ["vardec_retorno", "vardec_trabalho", "vardec_sucessao"]
    dados = [media[c].clip(-0.5, 1.5).fillna(0) for c in comps]
    ax.stackplot(media.index, *dados, labels=["retorno", "trabalho×poupança", "sucessão"],
                 colors=[COR[0], COR[1], COR[3]], alpha=0.8)
    ax.legend(loc="upper right"); saidas.append(_salvar(fig, figs_dir, "20_var_decomp.png"))

    # 21. Contribuição marginal de cada mecanismo para o Gini (proxy: vardec × ΔGini)
    fig, ax = _ax(f"[{cen.id}] Contribuição dos mecanismos ao longo do tempo", "ano", "share da variância (suavizado)")
    for c, lab, cor in [("vardec_retorno", "retorno", COR[0]),
                        ("vardec_trabalho", "trabalho", COR[1]),
                        ("vardec_sucessao", "sucessão", COR[3])]:
        ax.plot(media.index, media[c].rolling(5, min_periods=1).mean(), label=lab, color=cor)
    ax.legend(); saidas.append(_salvar(fig, figs_dir, "21_contrib_mecanismos.png"))

    # 22. Histograma da propensão a consumir efetiva por faixa (2126, via snapshot de renda)
    fig, ax = _ax(f"[{cen.id}] Propensão a consumir por faixa de decil (calibração)", "propensão", "densidade")
    for k in range(5):
        amostra = np.random.default_rng(0).uniform(
            __import__("parametros").CONSUMO_UNIF_LO[k],
            __import__("parametros").CONSUMO_UNIF_HI[k], 2000)
        ax.hist(amostra, bins=30, density=True, alpha=0.4, color=plt.get_cmap("viridis")(k / 4),
                label=f"faixa {k+1}")
    ax.legend(); saidas.append(_salvar(fig, figs_dir, "22_propensao.png"))

    # 23. Distribuição empírica do retorno real por faixa (final)
    fig, ax = _ax(f"[{cen.id}] Retorno real realizado por faixa (2126)", "retorno a.a.", "densidade")
    for k in range(4):
        v = run0["retorno_final"][run0["faixa_final"] == k]
        if v.size > 5:
            ax.hist(v, bins=30, density=True, alpha=0.45,
                    color=plt.get_cmap("viridis")(k / 3), label=f"faixa {k+1}")
    ax.legend(); saidas.append(_salvar(fig, figs_dir, "23_retorno_por_faixa.png"))

    # 24. Densidade de choques de educação acumulados (final)
    fig, ax = _ax(f"[{cen.id}] Choques de educação acumulados (2126)", "nº de choques", "fração das famílias")
    vals, cont = np.unique(run0["n_edu_final"], return_counts=True)
    ax.bar(vals, cont / cont.sum(), color=COR[2])
    saidas.append(_salvar(fig, figs_dir, "24_choques_edu.png"))

    # 25. Gini intra-faixa (4 painéis) — usando snapshots por faixa em 2126
    fig, axs = plt.subplots(2, 2, figsize=(11, 8))
    patr = run0["snapshots"][2126]["patrimonio"]; faixa = run0["faixa_final"]
    for k, ax in enumerate(axs.ravel()):
        v = patr[faixa == k]
        g = M.gini(v) if v.size > 2 else float("nan")
        ax.hist(np.log10(np.maximum(v, 1.0)), bins=30, color=COR[k], alpha=0.7)
        ax.set_title(f"faixa {k+1} — Gini intra={g:.3f} (n={v.size})")
        ax.set_xlabel("log10 patrimônio")
    fig.suptitle(f"[{cen.id}] Gini intra-faixa (2126)")
    saidas.append(_salvar(fig, figs_dir, "25_gini_intra_faixa.png"))

    return saidas


# ---------------------------------------------------------------------------
# Figuras comparativas entre cenários (26–34)
# ---------------------------------------------------------------------------

def figuras_comparativas(resultados: dict, outdir: str) -> list[str]:
    """resultados: {cenario_id: res_dict}. Gera figs 26–34 em output/comparativos/."""
    saidas = []
    ids = list(resultados)
    cores = {cid: COR[i % len(COR)] for i, cid in enumerate(ids)}

    def _traj(col, titulo, nome, ylog=False):
        fig, ax = _ax(titulo, "ano", col)
        for cid in ids:
            m = resultados[cid]["media"]
            ax.plot(m.index, m[col], label=cid, color=cores[cid])
        if ylog:
            ax.set_yscale("log")
        ax.legend(); return _salvar(fig, outdir, nome)

    # 26–28. trajetórias sobrepostas
    saidas.append(_traj("gini_patrimonio", "Gini patrimonial por cenário", "26_gini_patr.png"))
    saidas.append(_traj("top1_patrimonio", "Share top 1% (patrimônio) por cenário", "27_top1.png"))
    saidas.append(_traj("bottom50_patrimonio", "Share bottom 50% (patrimônio) por cenário", "28_bottom50.png"))

    # 29. distribuição patrimonial 2126 (KDE/hist) entre cenários
    fig, ax = _ax("Distribuição de log(patrimônio) em 2126 por cenário", "log10 patrimônio", "densidade")
    for cid in ids:
        v = resultados[cid]["run0"]["snapshots"][2126]["patrimonio"]
        ax.hist(np.log10(np.maximum(v, 1.0)), bins=50, density=True,
                histtype="step", color=cores[cid], label=cid)
    ax.legend(); saidas.append(_salvar(fig, outdir, "29_dist_2126.png"))

    # 30. Razão de Palma final por cenário (bar)
    fig, ax = _ax("Razão de Palma patrimonial em 2126 por cenário", "cenário", "Palma")
    vals = [resultados[cid]["media"]["palma_patrimonio"].iloc[-1] for cid in ids]
    ax.bar(ids, vals, color=[cores[c] for c in ids]); saidas.append(_salvar(fig, outdir, "30_palma_final.png"))

    # 31. % famílias na faixa 1 em 2126
    fig, ax = _ax("% famílias na faixa 1 em 2126 por cenário", "cenário", "fração faixa 1")
    vals = [resultados[cid]["media"]["frac_faixa1"].iloc[-1] for cid in ids]
    ax.bar(ids, vals, color=[cores[c] for c in ids]); saidas.append(_salvar(fig, outdir, "31_faixa1_final.png"))

    # 32. Curva de Lorenz 2126 sobreposta
    fig, ax = _ax("Curva de Lorenz patrimonial 2126 por cenário", "população acumulada", "share acumulado")
    ax.plot([0, 1], [0, 1], ls=":", color="gray")
    for cid in ids:
        pop, cum = _lorenz(resultados[cid]["run0"]["snapshots"][2126]["patrimonio"])
        ax.plot(pop, cum, label=cid, color=cores[cid])
    ax.legend(); saidas.append(_salvar(fig, outdir, "32_lorenz_2126.png"))

    # 33. Custo da política vs ganho de Gini (scatter eficiência)
    fig, ax = _ax("Custo da transferência vs. variação do Gini patrimonial (2126)",
                  "transferência total acumulada (R$)", "Gini patr. 2126 − baseline")
    base_gini = resultados["S0"]["media"]["gini_patrimonio"].iloc[-1] if "S0" in resultados else 0.0
    for cid in ids:
        m = resultados[cid]["media"]
        custo = m["transferencia_total"].sum()
        ax.scatter(custo, m["gini_patrimonio"].iloc[-1] - base_gini, color=cores[cid])
        ax.annotate(cid, (custo, m["gini_patrimonio"].iloc[-1] - base_gini))
    saidas.append(_salvar(fig, outdir, "33_eficiencia_politica.png"))

    # 34. Resumo executivo (tabela como imagem)
    fig, ax = plt.subplots(figsize=(11, 0.5 + 0.4 * len(ids)))
    ax.axis("off")
    linhas = []
    for cid in ids:
        m = resultados[cid]["media"]
        linhas.append([cid,
                       f"{m['gini_patrimonio'].loc[2076]:.3f}", f"{m['gini_patrimonio'].iloc[-1]:.3f}",
                       f"{m['top1_patrimonio'].iloc[-1]:.1%}", f"{m['bottom50_patrimonio'].iloc[-1]:.1%}"])
    tab = ax.table(cellText=linhas,
                   colLabels=["cenário", "Gini patr. 2076", "Gini patr. 2126",
                              "top1% 2126", "bottom50% 2126"],
                   loc="center", cellLoc="center")
    tab.scale(1, 1.5)
    ax.set_title("Resumo executivo por cenário")
    saidas.append(_salvar(fig, outdir, "34_resumo_executivo.png"))

    return saidas
