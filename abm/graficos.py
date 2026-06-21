import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from pathlib import Path

NOMES_CLASSES = {0: 'Consumidora', 1: 'Poupadora', 2: 'Rentista'}
CORES_CLASSES  = {0: '#e06c75',    1: '#61afef',   2: '#98c379'}

plt.rcParams.update({'figure.dpi': 150, 'font.size': 10})


def _salvar(fig, path: Path, nome: str) -> None:
    fig.savefig(path / nome, bbox_inches='tight')
    plt.close(fig)
    print(f"  {path / nome}")


def plotar_gini(df: pd.DataFrame, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df['ano'], df['gini_total'],      color='#c678dd', linewidth=2, label='Gini (riqueza total)')
    ax.plot(df['ano'], df['gini_financeiro'], color='#e5c07b', linewidth=1.5, linestyle='--', label='Gini (só capital financeiro)')
    ax.set(xlabel='Ano', ylabel='Gini', title='Desigualdade ao longo do tempo')
    ax.set_ylim(0, 1)
    ax.legend()
    ax.grid(alpha=0.3)
    _salvar(fig, output, 'gini_temporal.png')


def plotar_shares(df: pd.DataFrame, output: Path) -> None:
    """Concentracao de riqueza — 2 subplots:
       1) Shares cumulativos (Top 1%, Top 10%, Top 50%)
       2) Shares por faixas exclusivas (Top 1% / 9% seguintes / 40% seguintes)
    """
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))

    # Subplot 1: cumulativos
    ax = axes[0]
    ax.plot(df['ano'], df['share_top1'],  label='Top 1%',  color='#e06c75', linewidth=2)
    ax.plot(df['ano'], df['share_top10'], label='Top 10%', color='#e5c07b', linewidth=2)
    ax.plot(df['ano'], df['share_top50'], label='Top 50%', color='#98c379', linewidth=2)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set(xlabel='Ano', ylabel='Fração da riqueza total',
           title='Concentração cumulativa (Top 1% / 10% / 50%)')
    ax.legend()
    ax.grid(alpha=0.3)

    # Subplot 2: exclusivos
    ax = axes[1]
    if 'share_top10_excl_top1' in df.columns:
        ax.plot(df['ano'], df['share_top1'],
                label='Top 1% (P99-100)', color='#e06c75', linewidth=2)
        ax.plot(df['ano'], df['share_top10_excl_top1'],
                label='9% seguintes (P90-99)', color='#e5c07b', linewidth=2)
        ax.plot(df['ano'], df['share_top50_excl_top10'],
                label='40% seguintes (P50-90)', color='#98c379', linewidth=2)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set(xlabel='Ano', ylabel='Fração da riqueza total',
           title='Concentração por faixas exclusivas')
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    _salvar(fig, output, 'shares_temporal.png')


def plotar_imoveis(df: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Preço do imóvel
    ax = axes[0]
    ax.plot(df['ano'], df['preco_imovel'] / 1_000, color='#56b6c2', linewidth=2)
    ax.set(xlabel='Ano', ylabel='Preço (R$ mil)',
           title='Preço de mercado do imóvel')
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'R${x:.0f}k'))
    ax.grid(alpha=0.3)

    # Taxa de propriedade
    ax = axes[1]
    ax.plot(df['ano'], df['taxa_propriedade'] * 100, color='#98c379', linewidth=2)
    ax.set(xlabel='Ano', ylabel='% proprietários',
           title='Taxa de propriedade imobiliária')
    ax.grid(alpha=0.3)

    plt.tight_layout()
    _salvar(fig, output, 'mercado_imoveis.png')


def plotar_trajetorias(df: pd.DataFrame, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    for (classe, ag_id), grp in df.groupby(['classe', 'agente_id']):
        vivo = grp['vivo']
        anos = grp.loc[vivo, 'ano'].values
        caps = grp.loc[vivo, 'capital'].clip(lower=1).values
        if len(anos) == 0:
            continue
        ax.semilogy(anos, caps,
                    color=CORES_CLASSES[int(classe)], alpha=0.75, linewidth=1.5,
                    label=f"{NOMES_CLASSES[int(classe)]} #{ag_id}")
    ax.set(xlabel='Ano', ylabel='Capital financeiro (R$, escala log)',
           title='Trajetórias individuais de capital')
    ax.legend(fontsize=8, ncol=3)
    ax.grid(alpha=0.3, which='both')
    _salvar(fig, output, 'trajetorias.png')


def plotar_distribuicao_geracoes(df: pd.DataFrame, output: Path) -> None:
    anos = sorted(df['ano'].unique())
    n_anos = len(anos)
    fig, axes = plt.subplots(1, n_anos, figsize=(4 * n_anos, 5), sharey=False)
    if n_anos == 1:
        axes = [axes]

    percentis_plot = ['p25', 'p50', 'p75', 'p90', 'p99']
    largura = 0.25
    x = np.arange(len(percentis_plot))

    for ax, ano in zip(axes, anos):
        sub = df[df['ano'] == ano]
        for offset, c in zip([-largura, 0, largura], range(3)):
            row = sub[sub['classe'] == c]
            if row.empty:
                continue
            vals = [float(row[p].values[0]) for p in percentis_plot]
            ax.bar(x + offset, vals, width=largura,
                   color=CORES_CLASSES[c], alpha=0.8, label=NOMES_CLASSES[c])
        ax.set_yscale('log')
        ax.set_xticks(x)
        ax.set_xticklabels(['P25', 'P50', 'P75', 'P90', 'P99'], fontsize=8)
        ax.set_title(f'Ano {ano}')
        ax.set_ylabel('Riqueza total (R$)')
        if ano == anos[0]:
            ax.legend(fontsize=7)

    fig.suptitle('Distribuição de riqueza por classe (capital + imóveis)', y=1.01)
    plt.tight_layout()
    _salvar(fig, output, 'distribuicao_geracoes.png')


def plotar_rent_flow(df: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    ax.plot(df['ano'], df['frac_rent_renda'] * 100, color='#e06c75', linewidth=2)
    ax.set(xlabel='Ano', ylabel='Aluguel / Renda consumidores (%)',
           title='Fração da renda dos consumidores extraída como aluguel')
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(df['ano'], df['n_renters'], color='#e5c07b', linewidth=2, label='Renters')
    ax.plot(df['ano'], df['n_proprietarios'], color='#98c379', linewidth=2, label='Proprietários')
    ax.set(xlabel='Ano', ylabel='Número de agentes',
           title='Renters vs proprietários ao longo do tempo')
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    _salvar(fig, output, 'rent_flow.png')


def plotar_populacao(df: pd.DataFrame, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df['ano'], df['populacao'], color='#56b6c2', linewidth=2)
    ax.set(xlabel='Ano', ylabel='Agentes vivos',
           title='Evolução da população simulada')
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    ax.grid(alpha=0.3)
    _salvar(fig, output, 'populacao.png')


def plotar_piramide_etaria(df_pir: pd.DataFrame, output: Path) -> None:
    anos = sorted(df_pir['ano'].unique())
    n = len(anos)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 5), sharey=True, sharex=True)
    if n == 1:
        axes = [axes]
    faixas = [f"{g*5}-{g*5+4}" for g in range(18)]
    for ax, ano in zip(axes, anos):
        sub = df_pir[df_pir['ano'] == ano]
        vals = sub.set_index('faixa').reindex(faixas)['n'].fillna(0).values
        ax.barh(faixas, vals, color='#56b6c2', alpha=0.8)
        ax.set_title(f'Ano {ano}')
        ax.set_xlabel('Agentes')
        if ano == anos[0]:
            ax.set_ylabel('Faixa etária')
    fig.suptitle('Pirâmide etária simulada', y=1.01)
    plt.tight_layout()
    _salvar(fig, output, 'piramide_etaria.png')



def plotar_riqueza_por_classe(df: pd.DataFrame, output: Path) -> None:
    if 'riqueza_media_c0' not in df.columns:
        return
    fig, ax = plt.subplots(figsize=(12, 5))
    for c in range(3):
        col = f'riqueza_media_c{c}'
        if col in df.columns:
            ax.plot(df['ano'], df[col] / 1_000,
                    color=CORES_CLASSES[c], linewidth=2, label=NOMES_CLASSES[c])
    ax.set_yscale('log')
    ax.set(xlabel='Ano', ylabel='Riqueza média (R$ mil)',
           title='Riqueza média por classe: capital financeiro + imóveis (escala log)')
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'R${x:.0f}k'))
    ax.legend()
    ax.grid(alpha=0.3, which='both')
    _salvar(fig, output, 'riqueza_por_classe.png')


def plotar_distribuicao_poupadores(df_snap: pd.DataFrame, output: Path) -> None:
    sub = df_snap[df_snap['classe'] == 1].sort_values('ano')
    if sub.empty or len(sub) < 2:
        return

    anos = sub['ano'].values
    fig, ax = plt.subplots(figsize=(10, 5))

    cores_perc = ['#aabbcc', '#61afef', '#56b6c2', '#e5c07b', '#e06c75']
    labels_perc = ['P25', 'P50 (mediana)', 'P75', 'P90', 'P99']
    cols_perc   = ['p25', 'p50', 'p75', 'p90', 'p99']
    lws         = [1.2,    2.0,           1.2,   1.5,   1.5]
    ls_list     = ['--',   '-',           '--',  ':',   ':']

    for col, label, cor, lw, ls in zip(cols_perc, labels_perc, cores_perc, lws, ls_list):
        vals = sub[col].values / 1_000
        ax.plot(anos, vals, marker='o', linewidth=lw, linestyle=ls,
                label=label, color=cor, markersize=5)

    ax.fill_between(anos, sub['p25'].values / 1_000, sub['p75'].values / 1_000,
                    alpha=0.15, color='#61afef', label='Intervalo P25–P75')

    ax.set_yscale('log')
    ax.set_xticks(anos)
    ax.set(xlabel='Ano', ylabel='Riqueza (R$ mil)',
           title='Distribuição de riqueza dos Poupadores ao longo do tempo')
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'R${x:.0f}k'))
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, which='both')
    _salvar(fig, output, 'distribuicao_poupadores.png')


def plotar_classes(df: pd.DataFrame, output: Path) -> None:
    if 'pop_c0' not in df.columns:
        return
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    for c in range(3):
        ax.plot(df['ano'], df[f'pop_c{c}'], color=CORES_CLASSES[c], linewidth=2, label=NOMES_CLASSES[c])
    ax.set(xlabel='Ano', ylabel='Agentes vivos', title='População por classe ao longo do tempo')
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[1]
    riq_total = sum(df[f'pop_c{c}'] * df[f'riqueza_media_c{c}'] for c in range(3))
    for c in range(3):
        share = df[f'pop_c{c}'] * df[f'riqueza_media_c{c}'] / riq_total * 100
        ax.plot(df['ano'], share, color=CORES_CLASSES[c], linewidth=2, label=NOMES_CLASSES[c])
    ax.set(xlabel='Ano', ylabel='% da riqueza total', title='Participação de cada classe na riqueza total')
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    _salvar(fig, output, 'classes_populacao_riqueza.png')


def plotar_big_macs(df: pd.DataFrame, output: Path) -> None:
    from parametros import PRECO_BIG_MAC
    cols = [f'renda_diaria_mediana_c{c}' for c in range(3)]
    if not all(c in df.columns for c in cols):
        return
    fig, ax = plt.subplots(figsize=(12, 5))
    for c in range(3):
        bms = df[f'renda_diaria_mediana_c{c}'] / PRECO_BIG_MAC
        ax.plot(df['ano'], bms, color=CORES_CLASSES[c], linewidth=2, label=NOMES_CLASSES[c])
    ax.set_yscale('log')
    ax.set(xlabel='Ano', ylabel='Big Macs / dia (mediana, escala log)',
           title=f'Poder de compra — Big Macs por dia por classe (R${PRECO_BIG_MAC} cada, R$ 2024)')
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{x:.1f}'))
    ax.legend()
    ax.grid(alpha=0.3, which='both')
    _salvar(fig, output, 'big_macs_por_dia.png')


def _plotar_grade_percentis(df: pd.DataFrame, output: Path,
                              col_template: str, titulo: str, fname: str,
                              ylabel: str) -> None:
    """Helper: plota percentis P50, P90-P99 deflacionados por g.

    col_template: ex. 'p{p}_riqueza' ou 'p{p}_capfin' — onde {p} vira o numero do percentil.
    """
    from parametros import G_RENDA
    fator = (1 + G_RENDA) ** df['ano'].values

    fig, ax = plt.subplots(figsize=(13, 6.5))

    # Gradiente para P91-P98 (laranja claro -> laranja escuro)
    cmap = plt.cm.YlOrRd
    for i, p in enumerate(range(91, 99)):
        col = col_template.format(p=p)
        if col not in df.columns:
            continue
        vals = (df[col].values / fator) / 1_000
        ax.plot(df['ano'], vals,
                color=cmap(0.30 + 0.07 * i), linewidth=1.0, alpha=0.85,
                label=f'P{p} (Top {100-p}% mais ricos)')

    # Destaques: P50 (mediana), P90 (limiar top 10%), P99 (limiar top 1%)
    col50, col90, col99 = (col_template.format(p=p) for p in (50, 90, 99))
    p50_v = (df[col50].values / fator) / 1_000
    p90_v = (df[col90].values / fator) / 1_000
    p99_v = (df[col99].values / fator) / 1_000

    ax.plot(df['ano'], p99_v, label='P99 (Top 1%)',
            color='#c92a2a', linewidth=2.8, marker='o', markersize=3, zorder=10)
    ax.plot(df['ano'], p90_v, label='P90 (Top 10%)',
            color='#e5c07b', linewidth=2.8, marker='o', markersize=3, zorder=9)
    ax.plot(df['ano'], p50_v, label='P50 (mediana)',
            color='#98c379', linewidth=2.8, marker='o', markersize=3, zorder=8)

    ax.set_yscale('symlog', linthresh=1.0)
    ax.set(xlabel='Ano', ylabel=ylabel, title=titulo)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'R${x:,.0f}k'))
    ax.axhline(y=0, color='gray', linewidth=0.5, alpha=0.5)
    ax.legend(loc='center left', bbox_to_anchor=(1.01, 0.5), fontsize=9)
    ax.grid(alpha=0.3, which='both')
    plt.tight_layout()
    _salvar(fig, output, fname)


def plotar_percentis_riqueza_real(df: pd.DataFrame, output: Path) -> None:
    """Percentis da RIQUEZA TOTAL (capital + imoveis - divida), deflacionada por g."""
    _plotar_grade_percentis(
        df, output,
        col_template='p{p}_riqueza',
        titulo='Riqueza TOTAL (capital + imoveis - divida) por percentil, '
               'deflacionada por g  (eq. R$ 2024)',
        fname='percentis_riqueza_real.png',
        ylabel='Riqueza total (R$ mil, em poder de compra de 2024)',
    )


def plotar_percentis_capfin_real(df: pd.DataFrame, output: Path) -> None:
    """Percentis do CAPITAL FINANCEIRO apenas (sem imoveis), deflacionado por g.

    Comparar com plotar_percentis_riqueza_real mostra quanto da riqueza vem
    de imoveis vs. acumulacao financeira.
    """
    _plotar_grade_percentis(
        df, output,
        col_template='p{p}_capfin',
        titulo='CAPITAL FINANCEIRO apenas (sem imoveis) por percentil, '
               'deflacionado por g  (eq. R$ 2024)',
        fname='percentis_capfin_real.png',
        ylabel='Capital financeiro (R$ mil, em poder de compra de 2024)',
    )


def plotar_estoque_total(df: pd.DataFrame, output: Path) -> None:
    """Balanco do estoque imobiliario: total (mercado) vs detidos vs vagos."""
    if 'n_total_mercado' not in df.columns:
        return
    n_total  = df['n_total_mercado']
    n_det    = df['n_detidos_total']
    n_vagos  = (n_total - n_det).clip(lower=0)

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(df['ano'], n_total / 1_000, color='#56b6c2', linewidth=2,
            label='Estoque total (construíd o + existente)')
    ax.plot(df['ano'], n_det / 1_000, color='#98c379', linewidth=2,
            label='Detidos (com dono vivo)')
    ax.plot(df['ano'], n_vagos / 1_000, color='#e06c75', linewidth=2,
            label='Vagos (sem dono)')
    ax.fill_between(df['ano'], 0, n_det / 1_000, color='#98c379', alpha=0.10)
    ax.fill_between(df['ano'], n_det / 1_000, n_total / 1_000, color='#e06c75', alpha=0.10)
    ax.set(xlabel='Ano', ylabel='Imoveis (milhares)',
           title='Balanco do estoque imobiliario: total vs detidos vs vagos')
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{x:,.0f}k'))
    ax.legend()
    ax.grid(alpha=0.3)
    _salvar(fig, output, 'estoque_total.png')


def plotar_imoveis_por_classe(df: pd.DataFrame, output: Path) -> None:
    """Numero total de imoveis detidos por cada classe ao longo do tempo."""
    cols = [f'n_imoveis_c{c}' for c in range(3)]
    if not all(c in df.columns for c in cols):
        return
    fig, ax = plt.subplots(figsize=(11, 5))
    for c in range(3):
        ax.plot(df['ano'], df[f'n_imoveis_c{c}'],
                color=CORES_CLASSES[c], linewidth=2, label=NOMES_CLASSES[c])
    ax.set(xlabel='Ano', ylabel='Imoveis detidos (total)',
           title='Estoque de imoveis por classe ao longo do tempo')
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    ax.legend()
    ax.grid(alpha=0.3)
    _salvar(fig, output, 'imoveis_por_classe.png')


def plotar_proprietarios_por_classe(df: pd.DataFrame, output: Path) -> None:
    """Subplot 1: numero absoluto de proprietarios por classe.
    Subplot 2: % de pessoas de cada classe que possuem pelo menos um imovel.
    """
    cols = [f'n_proprietarios_c{c}' for c in range(3)] + [f'pop_c{c}' for c in range(3)]
    if not all(c in df.columns for c in cols):
        return
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))

    # Subplot 1: absoluto
    ax = axes[0]
    for c in range(3):
        ax.plot(df['ano'], df[f'n_proprietarios_c{c}'],
                color=CORES_CLASSES[c], linewidth=2, label=NOMES_CLASSES[c])
    ax.set(xlabel='Ano', ylabel='Individuos com >=1 imovel',
           title='Numero de proprietarios por classe')
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    ax.legend()
    ax.grid(alpha=0.3)

    # Subplot 2: % da classe
    ax = axes[1]
    for c in range(3):
        pop_c = df[f'pop_c{c}'].clip(lower=1)
        frac = df[f'n_proprietarios_c{c}'] / pop_c
        ax.plot(df['ano'], frac * 100,
                color=CORES_CLASSES[c], linewidth=2, label=NOMES_CLASSES[c])
    ax.set(xlabel='Ano', ylabel='% da classe com >=1 imovel',
           title='Taxa de propriedade dentro de cada classe')
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.set_ylim(0, 105)
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    _salvar(fig, output, 'proprietarios_por_classe.png')


def plotar_mc_bandas(df_agg: pd.DataFrame, output: Path) -> None:
    """Plota mediana + banda IC95% para metricas-chave do Monte Carlo."""
    paineis = [
        ('gini_total',       'Gini (riqueza liquida)',     '#c678dd', None),
        ('share_top1',       'Share do Top 1%',            '#e06c75', 'pct'),
        ('share_top10',      'Share do Top 10%',           '#e5c07b', 'pct'),
        ('taxa_propriedade', 'Taxa de propriedade',        '#98c379', 'pct'),
        ('preco_imovel',     'Preco do imovel (R$ mil)',   '#56b6c2', 'k'),
        ('populacao',        'Populacao viva',             '#61afef', None),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    axes = axes.flatten()
    anos = df_agg['ano'].values

    for ax, (col, titulo, cor, escala) in zip(axes, paineis):
        c_p025 = f'{col}_p025'
        c_p500 = f'{col}_p500'
        c_p975 = f'{col}_p975'
        if c_p500 not in df_agg.columns:
            ax.set_visible(False)
            continue
        med = df_agg[c_p500].values
        lo  = df_agg[c_p025].values
        hi  = df_agg[c_p975].values

        if escala == 'k':
            med, lo, hi = med / 1_000, lo / 1_000, hi / 1_000

        ax.plot(anos, med, color=cor, linewidth=2, label='Mediana')
        ax.fill_between(anos, lo, hi, color=cor, alpha=0.20, label='IC 95%')
        ax.set_title(titulo, fontsize=11)
        ax.set_xlabel('Ano')
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        if escala == 'pct':
            ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
        elif escala == 'k':
            ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'R${x:.0f}k'))

    fig.suptitle(f'Monte Carlo: mediana e intervalo de confianca 95%', y=1.00, fontsize=13)
    plt.tight_layout()
    _salvar(fig, output, 'mc_bandas.png')


def plotar_riqueza_decomposicao(df: pd.DataFrame, output: Path) -> None:
    if 'riqueza_imob_media' not in df.columns:
        return
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df['ano'], df['riqueza_media']      / 1_000, color='#c678dd', linewidth=2, label='Riqueza total')
    ax.plot(df['ano'], df['capital_medio']      / 1_000, color='#61afef', linewidth=2, linestyle='--', label='Capital financeiro')
    ax.plot(df['ano'], df['riqueza_imob_media'] / 1_000, color='#e5c07b', linewidth=2, linestyle=':', label='Patrimônio imobiliário')
    ax.set(xlabel='Ano', ylabel='Riqueza média (R$ mil)',
           title='Decomposição da riqueza média: financeira vs imobiliária')
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f'R${x:.0f}k'))
    ax.legend()
    ax.grid(alpha=0.3)
    _salvar(fig, output, 'riqueza_decomposicao.png')
