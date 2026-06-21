import sys
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE   = Path(__file__).resolve().parent
OUTPUT = BASE / 'output'
OUTPUT.mkdir(exist_ok=True)

sys.path.insert(0, str(BASE))

from parametros import R_JUROS, G_RENDA, N_AGENTES_INICIAL, N_ANOS, SEMENTE, N_RUNS_MC
from simulacao import run
from graficos import (
    plotar_gini,
    plotar_shares,
    plotar_percentis_riqueza_real,
    plotar_percentis_capfin_real,
    plotar_imoveis_por_classe,
    plotar_proprietarios_por_classe,
    plotar_estoque_total,
    plotar_trajetorias,
    plotar_distribuicao_geracoes,
    plotar_populacao,
    plotar_imoveis,
    plotar_rent_flow,
    plotar_riqueza_decomposicao,
    plotar_piramide_etaria,
    plotar_riqueza_por_classe,
    plotar_distribuicao_poupadores,
    plotar_big_macs,
    plotar_classes,
    plotar_mc_bandas,
)

# Metricas com bandas IC95% no Monte Carlo
COLS_MC = ['gini_total', 'gini_financeiro', 'share_top1', 'share_top10', 'share_top50',
           'taxa_propriedade', 'preco_imovel', 'populacao',
           'riqueza_media', 'riqueza_media_c0', 'riqueza_media_c1', 'riqueza_media_c2',
           'frac_rent_renda', 'divida_media']


def _agregar_mc(df_mc: pd.DataFrame) -> pd.DataFrame:
    """Agrega series temporais de N runs em mean/p2.5/p50/p97.5 por ano."""
    cols = [c for c in COLS_MC if c in df_mc.columns]
    out = pd.DataFrame({'ano': sorted(df_mc['ano'].unique())}).set_index('ano')
    for c in cols:
        s = df_mc.groupby('ano')[c]
        out[f'{c}_mean']  = s.mean()
        out[f'{c}_p025']  = s.quantile(0.025)
        out[f'{c}_p500']  = s.quantile(0.500)
        out[f'{c}_p975']  = s.quantile(0.975)
    return out.reset_index()


def main() -> None:
    print("=" * 65)
    print("ABM -- Efeitos de Longuissimo Prazo de Juros Reais Elevados")
    print(f"  r = {R_JUROS:.1%} a.a. real  |  g = {G_RENDA:.1%} a.a. real")
    print(f"  {N_AGENTES_INICIAL:,} agentes iniciais  |  {N_ANOS} anos")
    print(f"  Mercado imobiliario endogeno com hipoteca rastreada")
    print(f"  Monte Carlo: {N_RUNS_MC} sementes")
    print("=" * 65)

    # ----- Run 1: detalhada (seed=42) — para CSVs e graficos individuais -----
    inicio = time.time()
    df_serie, df_traj, df_snap, df_pir, mercado = run(seed=SEMENTE, verbose=True)
    elapsed_single = time.time() - inicio
    print(f"\nRun base (seed={SEMENTE}) concluida em {elapsed_single:.1f}s")

    df_serie.to_csv(OUTPUT / 'serie_temporal.csv', index=False)
    df_traj.to_csv(OUTPUT  / 'trajetorias_exemplo.csv', index=False)
    df_snap.to_csv(OUTPUT  / 'snapshot_geracoes.csv', index=False)
    print(f"CSVs base -> {OUTPUT}/")

    # ----- Monte Carlo -----
    print(f"\nMonte Carlo: rodando {N_RUNS_MC} sementes adicionais...")
    inicio_mc = time.time()
    series_mc = [df_serie.assign(run_id=0)]
    for k in range(1, N_RUNS_MC):
        seed_k = SEMENTE + k
        df_k, _, _, _, _ = run(seed=seed_k, verbose=False)
        df_k['run_id'] = k
        series_mc.append(df_k)
        if k % 5 == 0 or k == N_RUNS_MC - 1:
            print(f"  seed {seed_k}  ({k+1}/{N_RUNS_MC})  "
                  f"Gini final={df_k['gini_total'].iloc[-1]:.3f}")

    df_mc_long = pd.concat(series_mc, ignore_index=True)
    df_mc_long.to_csv(OUTPUT / 'serie_temporal_mc_runs.csv', index=False)
    df_mc_agg = _agregar_mc(df_mc_long)
    df_mc_agg.to_csv(OUTPUT / 'serie_temporal_mc_agg.csv', index=False)
    elapsed_mc = time.time() - inicio_mc
    print(f"Monte Carlo concluido em {elapsed_mc:.1f}s "
          f"({elapsed_mc/N_RUNS_MC:.1f}s/run)")

    # ----- Graficos -----
    print("\nGerando graficos:")
    plotar_gini(df_serie, OUTPUT)
    plotar_shares(df_serie, OUTPUT)
    plotar_percentis_riqueza_real(df_serie, OUTPUT)
    plotar_percentis_capfin_real(df_serie, OUTPUT)
    plotar_imoveis_por_classe(df_serie, OUTPUT)
    plotar_proprietarios_por_classe(df_serie, OUTPUT)
    plotar_estoque_total(df_serie, OUTPUT)
    plotar_imoveis(df_serie, OUTPUT)
    plotar_populacao(df_serie, OUTPUT)
    if not df_traj.empty:
        plotar_trajetorias(df_traj, OUTPUT)
    if not df_snap.empty:
        plotar_distribuicao_geracoes(df_snap, OUTPUT)
    plotar_rent_flow(df_serie, OUTPUT)
    plotar_riqueza_decomposicao(df_serie, OUTPUT)
    plotar_riqueza_por_classe(df_serie, OUTPUT)
    plotar_classes(df_serie, OUTPUT)
    plotar_big_macs(df_serie, OUTPUT)
    if not df_pir.empty:
        plotar_piramide_etaria(df_pir, OUTPUT)
    if not df_snap.empty:
        plotar_distribuicao_poupadores(df_snap, OUTPUT)

    # Graficos Monte Carlo (mediana + IC95)
    plotar_mc_bandas(df_mc_agg, OUTPUT)

    plano_src = Path(
        r"C:\Users\DELL-PC\.claude\plans\arquitetura-do-modelo-baseado-logical-crane.md"
    )
    if plano_src.exists():
        shutil.copy2(plano_src, BASE / 'PLANO.md')

    print(f"\nConcluido. Tempo total: {time.time() - inicio:.1f}s")


if __name__ == '__main__':
    main()
