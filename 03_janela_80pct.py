"""
Para cada nome, encontra a menor janela de anos consecutivos que concentra
80% da frequência relativa acumulada (normalizada pelo total de nascimentos
do ano, eliminando viés demográfico entre décadas).

Saídas:
  janela_80pct_todos_norm.txt  — todos os nomes
  janela_80pct_curtos_norm.txt — apenas nomes com janela < 20 anos
  nomes_pico_popularidade_norm.png — gráfico top 3 por década
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

df = pd.read_excel('data/Nomes2.xlsx')
df = df[(df['Ano'] >= 1900) & (df['Ano'] <= 2019)]

total_ano = df.groupby('Ano')['Q'].sum().rename('Total_Ano')
df = df.join(total_ano, on='Ano')
df['Freq'] = df['Q'] / df['Total_Ano']

pivot = df.pivot_table(index='Ano', columns='Nome', values='Freq', aggfunc='sum', fill_value=0)
all_years = pivot.index.to_numpy()
total_bruto = df.groupby('Nome')['Q'].sum()

results = []
for nome in pivot.columns:
    serie = pivot[nome].to_numpy()
    total_freq = serie.sum()
    if total_freq == 0:
        continue
    alvo = 0.80 * total_freq
    best_len = len(all_years) + 1
    best_start, best_end = 0, len(all_years) - 1
    left = 0
    window_sum = 0.0
    for right in range(len(all_years)):
        window_sum += serie[right]
        while window_sum >= alvo:
            span = right - left + 1
            if span < best_len:
                best_len = span
                best_start = left
                best_end = right
            window_sum -= serie[left]
            left += 1
    results.append({
        'Nome': nome,
        'Total_Bruto': int(total_bruto.get(nome, 0)),
        'Total_Norm': round(total_freq, 6),
        'Ano_Ini': int(all_years[best_start]),
        'Ano_Fim': int(all_years[best_end]),
        'Duracao': int(all_years[best_end] - all_years[best_start] + 1)
    })

results_df = pd.DataFrame(results).sort_values('Total_Norm', ascending=False)

# Arquivo 1: todos
with open('output/janela_80pct_todos_norm.txt', 'w', encoding='utf-8') as f:
    f.write(f'{"Nome":<25}{"Total_Bruto":>12}  {"Total_Norm":>12}  {"Ano_Ini":>8}  {"Ano_Fim":>8}  {"Duracao":>8}\n')
    f.write('-' * 80 + '\n')
    for _, r in results_df.iterrows():
        f.write(f'{r["Nome"]:<25}{r["Total_Bruto"]:>12,}  {r["Total_Norm"]:>12.4f}  {r["Ano_Ini"]:>8}  {r["Ano_Fim"]:>8}  {r["Duracao"]:>8}\n')
print(f'Arquivo 1: {len(results_df)} nomes')

# Arquivo 2: janela < 20 anos
curtos = results_df[results_df['Duracao'] < 20].copy()
with open('output/janela_80pct_curtos_norm.txt', 'w', encoding='utf-8') as f:
    f.write(f'{"Nome":<25}{"Total_Bruto":>12}  {"Total_Norm":>12}  {"Ano_Ini":>8}  {"Ano_Fim":>8}  {"Duracao":>8}\n')
    f.write('-' * 80 + '\n')
    for _, r in curtos.iterrows():
        f.write(f'{r["Nome"]:<25}{r["Total_Bruto"]:>12,}  {r["Total_Norm"]:>12.4f}  {r["Ano_Ini"]:>8}  {r["Ano_Fim"]:>8}  {r["Duracao"]:>8}\n')
print(f'Arquivo 2: {len(curtos)} nomes com janela < 20 anos')

# Gráfico: top 3 por década
curtos['Decada_Ini'] = (curtos['Ano_Ini'] // 10) * 10
top_decada = (curtos.sort_values('Total_Norm', ascending=False)
              .groupby('Decada_Ini').head(3)
              .sort_values(['Ano_Ini', 'Total_Norm'], ascending=[True, False]))

fig, ax = plt.subplots(figsize=(15, 12))
decadas = sorted(top_decada['Decada_Ini'].unique())
cmap = plt.cm.tab20
decade_colors = {d: cmap(i % 20) for i, d in enumerate(decadas)}

for i, (_, r) in enumerate(top_decada.iterrows()):
    color = decade_colors[r['Decada_Ini']]
    ax.barh(i, r['Duracao'], left=r['Ano_Ini'], height=0.65,
            color=color, edgecolor='white', linewidth=0.5)
    ax.text(r['Ano_Ini'] - 0.5, i, str(r['Ano_Ini']), va='center', ha='right', fontsize=7, color='gray')
    ax.text(r['Ano_Fim'] + 0.5, i, str(r['Ano_Fim']), va='center', ha='left', fontsize=7, color='gray')

ax.set_yticks(range(len(top_decada)))
ax.set_yticklabels([f"{r['Nome'].title()} ({r['Decada_Ini']}s)" for _, r in top_decada.iterrows()], fontsize=8.5)
ax.set_xlabel('Ano', fontsize=11)
ax.set_title('Nomes com popularidade pontual (janela < 20 anos) — Top 3 por década\n(Ordenados por frequência relativa acumulada, 1900–2019)', fontsize=12, fontweight='bold', pad=12)
ax.set_xlim(1895, 2025)
ax.xaxis.set_major_locator(plt.MultipleLocator(10))
ax.grid(axis='x', linestyle='--', alpha=0.4)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

legend_patches = [mpatches.Patch(color=decade_colors[d], label=f'{d}s') for d in decadas]
ax.legend(handles=legend_patches, title='Década', loc='lower right', fontsize=8, title_fontsize=8)

metodologia = (
    'Metodologia: nomes normalizados pela frequência relativa anual (participação no total de nascimentos do ano),\n'
    'eliminando o viés demográfico entre décadas. Exibidos os 3 nomes de maior freq. relativa acumulada por década\n'
    'cuja menor janela de 80% da popularidade é inferior a 20 anos. A escassez de nomes pontuais antes de 1970\n'
    'é um achado real: nomes eram mais estáveis e perenes nas gerações anteriores.'
)
fig.text(0.5, 0.005, metodologia, ha='center', va='bottom', fontsize=8, style='italic', color='#555555',
         bbox=dict(boxstyle='round,pad=0.4', facecolor='#f5f5f5', edgecolor='#cccccc'))

plt.tight_layout(rect=[0, 0.09, 1, 1])
plt.savefig('output/nomes_pico_popularidade_norm.png', dpi=150)
print('Gráfico salvo: nomes_pico_popularidade_norm.png')
