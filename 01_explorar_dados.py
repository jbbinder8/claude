import pandas as pd

df = pd.read_excel('data/Nomes2.xlsx')

print('=== RESUMO DO ARQUIVO ===')
print(f'Linhas: {len(df):,}')
print(f'Colunas: {list(df.columns)}')
print()
print('--- Primeiras linhas ---')
print(df.head(10).to_string(index=False))
print()
print('--- Anos disponíveis ---')
print(f'De {df["Ano"].min()} até {df["Ano"].max()}')
print()
print('--- Top 10 nomes mais frequentes (total geral) ---')
top = df.groupby('Nome')['Q'].sum().sort_values(ascending=False).head(10)
print(top.to_string())
print()
print('--- Total de nomes únicos ---')
print(f'{df["Nome"].nunique():,} nomes distintos')
print()
print('--- Total de registros por período (décadas) ---')
df['Decada'] = (df['Ano'] // 10) * 10
print(df.groupby('Decada')['Q'].sum().to_string())
