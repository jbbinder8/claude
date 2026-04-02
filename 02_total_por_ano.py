import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

df = pd.read_excel('Nomes2.xlsx')
df_valido = df[(df['Ano'] >= 1880) & (df['Ano'] <= 2024)]
total_por_ano = df_valido.groupby('Ano')['Q'].sum().reset_index()
total_por_ano.columns = ['Ano', 'Total']

# Exportar TXT
with open('total_nomes_por_ano.txt', 'w', encoding='utf-8') as f:
    f.write(f'{"Ano":<8}{"Total":>15}\n')
    f.write('-' * 23 + '\n')
    for _, row in total_por_ano.iterrows():
        f.write(f'{int(row["Ano"]):<8}{int(row["Total"]):>15,}\n')
    f.write('-' * 23 + '\n')
    f.write(f'{"TOTAL":<8}{int(total_por_ano["Total"].sum()):>15,}\n')

# Gráfico
fig, ax = plt.subplots(figsize=(16, 7))
ax.plot(total_por_ano['Ano'], total_por_ano['Total'], color='steelblue', linewidth=2)
ax.fill_between(total_por_ano['Ano'], total_por_ano['Total'], alpha=0.2, color='steelblue')
ax.set_title('Total de Registros de Nomes por Ano de Nascimento', fontsize=16, fontweight='bold', pad=15)
ax.set_xlabel('Ano', fontsize=12)
ax.set_ylabel('Total de Registros', fontsize=12)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x/1e6:.1f}M'))
ax.set_xticks(range(1880, 2025, 10))
ax.tick_params(axis='x', rotation=45)
ax.grid(axis='y', linestyle='--', alpha=0.5)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig('total_nomes_por_ano.png', dpi=150)
print('Arquivos salvos: total_nomes_por_ano.txt e total_nomes_por_ano.png')
