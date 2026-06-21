# ABM — Efeitos de Longuíssimo Prazo de Juros Reais Elevados

## Contexto

Simulador stand-alone (Agent-Based Model) para investigar, de forma exploratória, **o que acontece com a distribuição de patrimônio de uma população heterogênea quando a taxa real de juros se mantém estruturalmente alta por décadas**.

A pergunta motivadora: *se rodarmos uma economia por 100 anos com r = 7% a.a. real e renda crescendo a g = 2% a.a., o que emerge da interação entre classes que poupam diferente, vivem diferente e têm número diferente de filhos?*

O modelo não tenta reproduzir Piketty nem calibrar contra dados históricos do WID. O foco é deixar a dinâmica emergir e observar o que acontece.

### Parâmetros do experimento-base

| Parâmetro | Valor |
|---|---|
| Taxa real de juros (r) | 7% a.a. |
| Crescimento real da renda (g) | 2% a.a. |
| Agentes iniciais | 50 000 |
| Horizonte | 100 anos |
| Buffer pré-alocado | 600 000 slots |
| Semente aleatória | 42 |

---

## Estrutura de arquivos

```
abm/
├── parametros.py     # todas as constantes do modelo
├── populacao.py      # inicialização; criar_agente()
├── dinamica.py       # equação patrimonial anual; envelhecer()
├── ciclo_vida.py     # processar_nascimentos(); processar_herancas()
├── imoveis.py        # mercado imobiliário endógeno
├── metricas.py       # Gini, shares, snapshots
├── simulacao.py      # loop principal
├── graficos.py       # 11 gráficos PNG
├── main.py           # ponto de entrada
├── PLANO.md          # cópia deste arquivo
└── output/           # CSVs e PNGs gerados
```

---

## Representação dos agentes (arrays NumPy paralelos)

```
capital       : float64   capital financeiro acumulado
renda_base    : float64   renda do trabalho no ano 0 (log-normal por classe)
taxa_poupanca : float32   fração da renda poupada (sorteada por classe, fixa na vida)
retorno       : float32   retorno anual do capital financeiro (fixo por classe)
classe        : int8      0=consumidora, 1=poupadora, 2=rentista
idade         : int16     em anos completos
id_pai        : int32     -1 para geração fundadora
vivo          : bool
ano_nasc      : int16
n_imoveis     : int8      imóveis detidos (0=renter, 1=proprietário, 2+=investidor)
```

Buffer de 600 000 slots pré-alocado. Operações anuais são broadcasts NumPy sobre os ~50k slots marcados como `vivo=True`.

---

## Classes e calibração (Brasil 2024)

### Proporções e comportamento

| Classe | Proporção | Renda base (log-normal) | Poupança | Retorno financeiro |
|---|---|---|---|---|
| Consumidora (C0) | 75% | μ=R$30k, σ=0.60 | 50% poupam 0%; 50% poupam 0–10% | 0% |
| Poupadora (C1) | 20% | μ=R$120k, σ=0.50 | 10–38% (sorteado) | 6,5% |
| Rentista (C2) | 5% | μ=R$100k, σ=0.70 | 0% | 7,0% |

**Nota sobre poupança**: a taxa de poupança é sorteada uma vez no nascimento e permanece fixa na vida do agente. Para C0, há uma mistura: 50% sorteia exatamente 0% (não poupam nada) e 50% sorteia uniforme em (0%, 10%). Para C1, sorteia uniforme em (10%, 38%). Isso cria heterogeneidade contínua dentro de cada classe — consumidoras que guardam algo vs. as que gastam tudo; poupadores conservadores vs. agressivos. O parâmetro `FRAC_POUPANCA_ZERO = {0: 0.50}` em `parametros.py` controla a fração de não-poupadores por classe.

### Capital financeiro inicial

| Classe | Capital inicial |
|---|---|
| C0 | R$ 0 |
| C1 | log-normal: μ=R$200k, σ=0.90 |
| C2 | log-normal: μ=R$5M, σ=1.50 (fat-tail) |

### Imóveis iniciais (calibrado para taxa de propriedade ~73% — PNAD 2022)

| Classe | Proprietário (1+ imóvel) | Com 2º imóvel (investimento) |
|---|---|---|
| C0 | 68% | 0% |
| C1 | 88% | 22% |
| C2 | 100% | 55% + extras Poisson |

Máximo de imóveis: C0=1, C1=4, C2=10.

---

## Equação de evolução anual

$$K_{i,t} = \max\bigl(K_{i,t-1} \cdot (1 + r_i) + Y_{i,t} \cdot s_i,\ 0\bigr)$$

- $r_i$: retorno financeiro da classe (C0=0%, C1=6.5%, C2=7%)
- $Y_{i,t} = Y_{i,0} \cdot (1+g)^t$ se $18 \leq \text{idade} < 65$; zero fora da vida ativa
- $s_i$: taxa de poupança individual (sorteada no nascimento, fixa)
- Capital não pode ser negativo (sem modelagem de dívida)

---

## Mercado imobiliário endógeno

Preço de equilíbrio determinado pela capacidade de pagamento dos renters:

$$P_{\text{eq},t} = \frac{\bar{Y}_{C0,t} \cdot 0.35}{0.035}$$

onde 0.35 = fração da renda gasta com moradia, 0.035 = yield bruto de aluguel (3.5%).

Como $\bar{Y}_{C0}$ cresce a 2%/ano real, o preço de equilíbrio cresce junto. O preço observado converge para $P_{\text{eq}}$ com ajuste parcial (8% por ano).

**Construção**: +1.5%/ano de estoque base; dispara +4% quando preço > 1.30× equilíbrio.

**Herança de imóveis**: residência principal (1º imóvel) é transferida diretamente ao primeiro filho registrado sem imóvel. Imóveis de investimento (2º+) são liquidados ao preço de mercado e divididos como capital financeiro entre os filhos.

**Geração fundadora** (sem filhos registrados): residência vai ao primeiro renter disponível da mesma classe.

---

## Loop anual (em `simulacao.py`)

```
para t em 0..100:
    1. coletar_metricas         → registrar estado atual
    2. envelhecer               → idade += 1
    3. evoluir_capital          → equação patrimonial (NumPy broadcast)
    4. passo_mercado            → ajuste de preço + construção + compras/vendas
    5. processar_nascimentos    → fecundidade estocástica (IBGE calibrado)
    6. processar_herancas       → mortalidade estocástica + transferência de ativos
```

---

## Demografía — calibração IBGE 2022

### Mortalidade
Tábua quinquenal × 0.85 (ajuste prospectivo para e(0)≈82 em 2050). CDR implícito ≈0.72%/ano para pirâmide brasileira 2026.

### Fecundidade
Taxas IBGE × 1.20. TFR ≈1.77/mulher (Brasil 2026 ≈1.7). Multiplicadores por classe:
- C0: ×1.15 (TFR ≈2.04)
- C1: ×0.95 (TFR ≈1.68)
- C2: ×0.75 (TFR ≈1.33)

### Pirâmide inicial
Distribuição de idade na inicialização segue pirâmide etária IBGE 2024 (18 grupos quinquenais).

### Trajetória demográfica resultante
Pico populacional em torno do ano 15-16 (+6%), população ainda +5% no ano 24 (2050), −18% no ano 74. Compatível com projeções IBGE.

---

## Saídas

### CSVs (`output/`)

| Arquivo | Conteúdo |
|---|---|
| `serie_temporal.csv` | Uma linha por ano: Gini, shares, preço, taxa de propriedade, riqueza média por classe, população |
| `snapshot_geracoes.csv` | Distribuição de riqueza (percentis P10–P99) por classe nos anos 0, 25, 50, 75, 100 |
| `trajetorias_exemplo.csv` | Capital anual de 9 agentes representativos (3 por classe) |

### Gráficos PNG (11 arquivos)

| Arquivo | Conteúdo |
|---|---|
| `gini_temporal.png` | Gini total e Gini financeiro ao longo do tempo |
| `shares_temporal.png` | Share de riqueza do top 1%, 10%, 50% |
| `mercado_imoveis.png` | Preço do imóvel e taxa de propriedade |
| `populacao.png` | Evolução da população simulada |
| `trajetorias.png` | Trajetórias individuais de capital (escala log) |
| `distribuicao_geracoes.png` | Percentis de riqueza por classe nos anos de snapshot |
| `rent_flow.png` | Aluguel como % da renda + renters vs. proprietários |
| `riqueza_decomposicao.png` | Riqueza média: financeira vs. imobiliária vs. total |
| `riqueza_por_classe.png` | Riqueza média por classe ao longo do tempo (escala log) |
| `piramide_etaria.png` | Pirâmide etária nos anos de snapshot |
| `distribuicao_poupadores.png` | Distribuição de riqueza dos poupadores (fan P25–P99) |

---

## Resultados observados (semente 42)

| Ano | Vivos | Gini | Top 1% | Prop. | Preço |
|---|---|---|---|---|---|
| 0 | 50 000 | 0.759 | 52.5% | 73.6% | R$300k |
| 10 | 52 819 | 0.842 | 58.7% | 70.1% | R$270k |
| 30 | 51 813 | 0.897 | 66.8% | 69.1% | R$425k |
| 50 | 46 753 | 0.937 | 75.4% | 72.7% | R$513k |
| 70 | 41 581 | 0.958 | 80.7% | 77.4% | R$741k |
| 90 | 37 119 | 0.968 | 81.9% | 80.1% | R$1.10M |

Tempo de execução: ~8–10s.

---

## Fora de escopo (intencionalmente)

- Casamento e formação de domicílios (heranças bilaterais)
- Mobilidade social entre classes (testado e revertido — adiciona complexidade sem ganho analítico claro)
- Choques econômicos (crises, hiperinflação)
- Tributação progressiva sobre herança ou patrimônio
- Dashboard interativo com sliders
- Calibração contra dados reais (WID, IBGE, Receita Federal)

---

## Execução

```
C:\Users\DELL-PC\AppData\Local\Python\pythoncore-3.14-64\python.exe abm/main.py
```
