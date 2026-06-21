import numpy as np
import pandas as pd
from parametros import *
from populacao import inicializar
from dinamica import envelhecer, evoluir_capital
from ciclo_vida import processar_nascimentos, processar_herancas
from imoveis import criar_mercado, inicializar_propriedades, passo_mercado
from metricas import coletar_metricas, snapshot_distribuicao, snapshot_piramide

ANOS_SNAPSHOT = [0, 25, 50, 75, 100]
N_EXEMPLOS_POR_CLASSE = 3


def _selecionar_exemplos(pop: dict) -> dict:
    exemplos: dict[int, list[int]] = {}
    for c in range(3):
        candidatos = np.where(
            (pop['classe'][:N_AGENTES_INICIAL] == c) &
            (pop['idade'][:N_AGENTES_INICIAL] < 20) &
            pop['vivo'][:N_AGENTES_INICIAL]
        )[0]
        exemplos[c] = candidatos[:N_EXEMPLOS_POR_CLASSE].tolist()
    return exemplos


def run(seed: int = SEMENTE, verbose: bool = True) -> tuple:
    rng = np.random.default_rng(seed)
    pop, proximo_id, filhos_por_pai = inicializar(rng)

    mercado = criar_mercado()
    inicializar_propriedades(pop, proximo_id, mercado, rng)

    exemplos = _selecionar_exemplos(pop)
    todos_exemplos = [idx for ids in exemplos.values() for idx in ids]
    traj_buffer: dict[int, list] = {idx: [] for idx in todos_exemplos}

    serie: list[dict] = []
    snapshots: list[pd.DataFrame] = []
    piramides: list[pd.DataFrame] = []

    for t in range(N_ANOS + 1):
        metricas = coletar_metricas(pop, mercado, t)
        serie.append(metricas)

        for idx in todos_exemplos:
            traj_buffer[idx].append({
                'ano':     t,
                'capital': float(pop['capital'][idx]),
                'n_im':    int(pop['n_imoveis'][idx]),
                'vivo':    bool(pop['vivo'][idx]),
            })

        if t in ANOS_SNAPSHOT:
            snapshots.append(snapshot_distribuicao(pop, mercado, t))
            piramides.append(snapshot_piramide(pop, t))

        if t == N_ANOS:
            break

        if verbose and t % 10 == 0:
            print(f"Ano {t:>4d} | Vivos: {metricas['populacao']:>7,} | "
                  f"Gini: {metricas['gini_total']:.3f} | "
                  f"Top 1%: {metricas['share_top1']:.1%} | "
                  f"Prop: {metricas['taxa_propriedade']:.1%} | "
                  f"Preco R${metricas['preco_imovel']:>8,.0f} | "
                  f"Rent/Renda: {metricas['frac_rent_renda']:.1%}")

        envelhecer(pop)
        evoluir_capital(pop, t)
        passo_mercado(pop, mercado, t, rng)
        proximo_id = processar_nascimentos(pop, proximo_id, filhos_por_pai, t, rng)
        processar_herancas(pop, filhos_por_pai, mercado, rng)

    df_serie = pd.DataFrame(serie)

    traj_rows = []
    for c, ids in exemplos.items():
        for idx in ids:
            for entry in traj_buffer[idx]:
                traj_rows.append({'classe': c, 'agente_id': idx, **entry})
    df_traj = pd.DataFrame(traj_rows)

    df_snap = pd.concat(snapshots, ignore_index=True) if snapshots else pd.DataFrame()
    df_pir  = pd.concat(piramides, ignore_index=True) if piramides else pd.DataFrame()

    return df_serie, df_traj, df_snap, df_pir, mercado
