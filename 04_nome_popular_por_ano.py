"""
Para cada ano, identifica o nome mais popular dentre aqueles com
popularidade pontual (janela < 20 anos), usando frequência relativa.

Requer: janela_80pct_curtos_norm.txt (gerado por 03_janela_80pct.py)

Saída: nome_popular_por_ano.png
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

df = pd.read_excel('data/Nomes2.xlsx')
df = df[(df['Ano'] >= 1900) & (df['Ano'] <= 2019)]
total_ano = df.groupby('Ano')['Q'].sum().rename('Total_Ano')
df = df.join(total_ano, on='Ano')
df['Freq'] = df['Q'] / df['Total_Ano']

lines = open('output/janela_80pct_curtos_norm.txt', encoding='utf-8').readlines()[2:]
nomes_curtos = set()
for l in lines:
    parts = l.split()
    if parts:
        nomes_curtos.add(parts[0])

df_curtos = df[df['Nome'].isin(nomes_curtos)]
mais_popular = df_curtos.loc[df_curtos.groupby('Ano')['Freq'].idxmax(), ['Ano', 'Nome', 'Freq', 'Q']]
mais_popular = mais_popular.sort_values('Ano').reset_index(drop=True)

nomes_unicos = mais_popular['Nome'].unique()
cmap = plt.cm.tab20
color_map = {n: cmap(i % 20) for i, n in enumerate(nomes_unicos)}

fig, ax = plt.subplots(figsize=(18, 5))

for _, row in mais_popular.iterrows():
    ax.bar(row['Ano'], row['Freq'] * 100, width=1.0,
           color=color_map[row['Nome']], edgecolor='none')

prev = None
for _, row in mais_popular.iterrows():
    if row['Nome'] != prev:
        ax.axvline(row['Ano'], color='white', linewidth=0.8, alpha=0.6)
        ax.text(row['Ano'] + 0.3, row['Freq'] * 100 + 0.05,
                row['Nome'].title(), fontsize=7.5, rotation=45,
                va='bottom', ha='left', color=color_map[row['Nome']], fontweight='bold')
        prev = row['Nome']

ax.set_xlabel('Ano', fontsize=11)
ax.set_ylabel('Frequência relativa (%)', fontsize=11)
ax.set_title('Nome mais popular por ano — apenas nomes com popularidade pontual (janela < 20 anos)\nFrequência relativa = % do total de nascimentos naquele ano', fontsize=12, fontweight='bold', pad=12)
ax.set_xlim(1899, 2020)
ax.xaxis.set_major_locator(plt.MultipleLocator(10))
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.1f}%'))
ax.grid(axis='y', linestyle='--', alpha=0.3)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

legend_patches = [mpatches.Patch(color=color_map[n], label=n.title()) for n in nomes_unicos]
ax.legend(handles=legend_patches, loc='upper left', fontsize=7.5, ncol=2,
          framealpha=0.8, title='Nome dominante', title_fontsize=8)

plt.tight_layout()
plt.savefig('output/nome_popular_por_ano.png', dpi=150, bbox_inches='tight')
print('Gráfico salvo: nome_popular_por_ano.png')
