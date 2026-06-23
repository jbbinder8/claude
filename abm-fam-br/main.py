"""
CLI do ABM de famílias brasileiras (orquestra seções 4–7 da spec).

Uso:
    python main.py                      # roda S0..S7, n=1000, 30 runs, com figuras
    python main.py --cenarios S0 S2     # só alguns cenários
    python main.py --n-familias 10000 --n-runs 30
    python main.py --rapido             # n=500, 5 runs, sem microdados (teste)
    python main.py --sem-figuras

Saídas em abm-fam-br/output/ (§7.1):
    <id>/series_agregadas.csv, params.json, calibracao_inicial.json,
    <id>/microdados_run0.parquet, mobilidade_run0.parquet, decomposicao_variancia.csv,
    <id>/figs/*.png  e  comparativos/*.png
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

import parametros as P
import inicializacao as I
import simulacao as S
import graficos as G

AQUI = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(AQUI, "output")


def _json_default(o):
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    raise TypeError(type(o))


def _gravar_outputs(cid: str, cen: P.Cenario, res: dict, seed_base: int,
                    com_microdados: bool) -> None:
    outdir = os.path.join(OUTPUT, cid)
    os.makedirs(outdir, exist_ok=True)

    # params.json
    with open(os.path.join(outdir, "params.json"), "w", encoding="utf-8") as f:
        json.dump(cen.to_dict(), f, ensure_ascii=False, indent=2, default=_json_default)

    # calibracao_inicial.json (§4.5)
    rel = I.validar_inicializacao(I.inicializar(cen, seed_base))
    with open(os.path.join(outdir, "calibracao_inicial.json"), "w", encoding="utf-8") as f:
        json.dump(rel, f, ensure_ascii=False, indent=2, default=_json_default)

    # series_agregadas.csv (média + IC95%)
    media, ic = res["media"], res["ic95"]
    series = media.join(ic, rsuffix="_ic95")
    series.to_csv(os.path.join(outdir, "series_agregadas.csv"), encoding="utf-8")

    # decomposicao_variancia.csv
    cols_dec = [c for c in media.columns if c.startswith("vardec_")]
    media[cols_dec].to_csv(os.path.join(outdir, "decomposicao_variancia.csv"), encoding="utf-8")

    # mobilidade_run0.parquet — matrizes de transição (3 janelas)
    import metricas as M
    dd = res["run0"]["decis_decada"]
    regs = []
    for a0, a1 in [(2026, 2076), (2076, 2126), (2026, 2126)]:
        m = M.matriz_transicao(dd[a0], dd[a1])
        for i in range(10):
            for j in range(10):
                regs.append({"janela": f"{a0}-{a1}", "decil_origem": i + 1,
                             "decil_destino": j + 1, "prob": m[i, j]})
    pd.DataFrame(regs).to_parquet(os.path.join(outdir, "mobilidade_run0.parquet"))

    # microdados_run0.parquet (painel família × ano)
    if com_microdados and res["run0"]["painel"] is not None:
        res["run0"]["painel"].to_parquet(os.path.join(outdir, "microdados_run0.parquet"))


def _gravar_params_raiz(cenarios_rodados: list[str], todos: dict,
                        n_familias: int, n_runs: int) -> None:
    """Salva tabela CSV com os parâmetros de todos os cenários (S0–S7) no output raiz.

    Grava output/cenarios_params_<timestamp>.csv — uma linha por cenário, uma coluna
    por parâmetro — para rastreabilidade histórica mesmo que a spec mude.
    """
    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    ids = list(todos.keys())
    colunas = {}
    for cid in ids:
        d = todos[cid].to_dict()
        rm = d["retorno_media_faixa"]
        rd = d["retorno_dp_faixa"]
        limiar_str = "universal" if d["limiar"] == float("inf") else str(d["limiar"])
        colunas[cid] = {
            "nome":                  d["nome"],
            "rodado":                "sim" if cid in cenarios_rodados else "nao",
            "n_familias":            str(n_familias),
            "n_runs":                str(n_runs),
            "g_%aa":                 f"{d['g']*100:.1f}",
            "retorno_faixa1_%":      f"{rm[0]*100:.1f}",
            "retorno_faixa2_%":      f"{rm[1]*100:.1f}",
            "retorno_faixa3_%":      f"{rm[2]*100:.1f}",
            "retorno_faixa4_%":      f"{rm[3]*100:.1f}",
            "dp_retorno_faixa1_%":   f"{rd[0]*100:.1f}",
            "dp_retorno_faixa2_%":   f"{rd[1]*100:.1f}",
            "dp_retorno_faixa3_%":   f"{rd[2]*100:.1f}",
            "dp_retorno_faixa4_%":   f"{rd[3]*100:.1f}",
            "transferencia_R$_mes":  str(d["transferencia_base"]),
            "limiar_R$_mes":         limiar_str,
            "usa_renda_total":       str(d["limiar_usa_renda_total"]),
            "alpha_seguro":          str(d["alpha_seguro"]),
            "max_choques_edu":       str(d["max_choques_edu"]),
            "p_sucessao_%":          f"{d['p_sucessao']*100:.1f}",
            "banda_histerese_%":     f"{d['banda_histerese']*100:.0f}",
        }

    params = list(next(iter(colunas.values())).keys())

    # larguras de cada coluna para alinhamento fixo
    w_param = max(len(p) for p in params)
    w_cols  = {cid: max(len(cid), max(len(colunas[cid][p]) for p in params))
               for cid in ids}

    sep   = "+-" + "-" * w_param + "-+-" + "-+-".join("-" * w_cols[c] for c in ids) + "-+"
    linha = lambda param, vals: (
        "| " + param.ljust(w_param) + " | " +
        " | ".join(vals[c].ljust(w_cols[c]) for c in ids) + " |"
    )
    header = "| " + "parametro".ljust(w_param) + " | " + \
             " | ".join(c.ljust(w_cols[c]) for c in ids) + " |"

    linhas_txt = [
        f"rodada: {ts}",
        "",
        sep,
        header,
        sep,
    ]
    for p in params:
        linhas_txt.append(linha(p, {cid: colunas[cid][p] for cid in ids}))
    linhas_txt += [sep, ""]

    caminho = os.path.join(OUTPUT, f"cenarios_params_{ts}.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas_txt))
    print(f"[params] {caminho}")


def rodar(cenarios: list[str], n_familias: int, n_runs: int,
          com_figuras: bool, com_microdados: bool) -> None:
    os.makedirs(OUTPUT, exist_ok=True)
    todos = P.cenarios_base(n_familias=n_familias)
    resultados = {}

    _gravar_params_raiz(cenarios, todos, n_familias, n_runs)

    for cid in cenarios:
        cen = todos[cid]
        cen.n_familias = n_familias
        t0 = time.time()
        res = S.simular_cenario(cen, n_runs=n_runs,
                                coletar_painel_run0=com_microdados)
        dt = time.time() - t0
        g2126 = res["media"]["gini_patrimonio"].iloc[-1]
        print(f"[{cid}] {cen.nome:28s} {dt:6.1f}s  Gini patr. 2126 = {g2126:.3f}")

        _gravar_outputs(cid, cen, res, P.SEED_BASE, com_microdados)
        if com_figuras:
            n = len(G.figuras_cenario(res, cen, os.path.join(OUTPUT, cid)))
            print(f"        {n} figuras geradas")
        resultados[cid] = res

    if com_figuras and len(resultados) > 1:
        comp_dir = os.path.join(OUTPUT, "comparativos")
        n = len(G.figuras_comparativas(resultados, comp_dir))
        print(f"[comparativos] {n} figuras geradas em {comp_dir}")


def main():
    ap = argparse.ArgumentParser(description="ABM de famílias brasileiras")
    ap.add_argument("--cenarios", nargs="+", default=list(P.cenarios_base()),
                    help="ids dos cenários (default: todos S0..S7)")
    ap.add_argument("--n-familias", type=int, default=1000)
    ap.add_argument("--n-runs", type=int, default=P.N_RUNS)
    ap.add_argument("--sem-figuras", action="store_true")
    ap.add_argument("--sem-microdados", action="store_true")
    ap.add_argument("--rapido", action="store_true",
                    help="atalho de teste: n=500, 5 runs, sem microdados")
    a = ap.parse_args()

    if a.rapido:
        a.n_familias, a.n_runs, a.sem_microdados = 500, 5, True

    print(f"Cenários: {a.cenarios} | n_familias={a.n_familias} | n_runs={a.n_runs}")
    rodar(a.cenarios, a.n_familias, a.n_runs,
          com_figuras=not a.sem_figuras, com_microdados=not a.sem_microdados)
    print(f"\nConcluído. Saídas em {OUTPUT}")


if __name__ == "__main__":
    main()
