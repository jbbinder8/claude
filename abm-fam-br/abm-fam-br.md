especificação para código python que usa ABM para simular microeconomia das famílias brasileiras

# 1. Objetivo

Quantificar como a desigualdade patrimonial brasileira evolui no longuíssimo prazo (~100 anos) sob diferentes cenários de:
- juros reais (heterogeneidade entre famílias, calibrada pela faixa de patrimônio vigente a cada momento)
- crescimento da renda agregada
- choques de desemprego
- política de transferências (ex.: renda básica)

O modelo deve responder perguntas como:
- "Se a Selic real estrutural cair 2 p.p., o Gini patrimonial diminui ou aumenta em 50 anos?"
- "Quanto da desigualdade vem de retornos desiguais sobre o patrimônio vs. propensão a poupar desigual?"
- "Uma renda básica de R$ 600/mês reverte quanto da concentração projetada?"

# 2. Escopo

- Período: 2026 a 2126 (100 anos, passo anual)
- Famílias: 1.000 unidades iniciais (parametrizável; alvo final 10.000)
- Preços constantes (todos os valores em R$ de 2026)
- Sem ciclo de vida, sem herança, sem variação populacional (ver seção 9)

# 3. Granularidade

Cada família é uma unidade fixa que existe em todos os anos. Não modelamos indivíduos dentro da família.

Atributos persistentes de cada família `i`:
- `renda_trabalho_base_i(t)` — renda anual **recorrente não-patrimonial** em R$ (apesar do nome "trabalho", inclui também aposentadorias, pensões e outras rendas estruturais que não vêm do estoque de patrimônio, em linha com o agregado da PNAD usado para calibração). Inicializada de uma log-normal (4.1); aumenta apenas com choques de educação (5.4); cresce com `g` agregado. **Não cai com desemprego** — representa o capital humano e direitos previdenciários (estruturais).
- `c_faixa_decil_i` — **vetor** de 5 propensões a consumir pré-sorteadas na inicialização, uma para cada faixa de decil de renda total (1: decil 1–3; 2: decil 4–7; 3: decil 8–9; 4: decil 10; 5: top 1%). A propensão efetiva em cada ano é `c_faixa_decil_i[faixa_decil_renda_total_i(t)]`. Ver seção 4.3.
- `retorno_real_i(t)` — taxa real anual de retorno sobre o patrimônio. Sorteada na inicialização em função da faixa de patrimônio inicial e mantida fixa enquanto a família permanecer na mesma faixa (com histerese, ver seção 5.2).
- `faixa_patrimonio_i(t)` — derivada do patrimônio corrente (1 = baixo … 4 = alto) com histerese e limites indexados por `g` (ver seção 5.2)
- `patrimonio_i(t)` — variável de estado evoluída pela simulação
- `status_emprego_i(t)` — empregado / desempregado (cadeia de Markov)
- `n_choques_edu_i(t)` — contador de choques de educação acumulados (limitado, ver seção 5.4)

## 3.1 Ordem dos eventos dentro do ano `t`

A ordem do pipeline anual é fixa e determinística (cada etapa usa o estado consolidado da etapa anterior):

1. Atualiza `status_emprego_i(t)` (cadeia de Markov, seção 5.3) — probabilidades baseadas no **decil de `renda_trabalho_base_i(t-1)`**
2. Aplica eventual choque de educação → atualiza `renda_trabalho_base_i(t)` (seção 5.4) — probabilidade baseada no **decil de `renda_trabalho_base_i(t-1)`**
3. Calcula `renda_trabalho_i(t)` (com `g` e choque de emprego, seção 5.1)
4. Calcula `retorno_patrimonio_i(t) = retorno_real_i(t) × patrimonio_i(t)` (seção 5.2)
5. Calcula `transferencia_i(t)` (seção 5.1) — pode depender da renda do patrimônio se `LIMIAR_USA_RENDA_TOTAL = True`, por isso vem **depois** da etapa 4
6. Calcula `renda_total_i(t) = renda_trabalho + retorno_patrimonio + transferencia`
7. Determina o **decil de `renda_total_i(t)`** entre todas as famílias e a faixa de decil correspondente (1–5); seleciona `propensao_consumir_i(t) = c_faixa_decil_i[faixa_decil_atual]`
8. Calcula consumo e poupança (seção 5.5); atualiza `patrimonio_i(t+1)` (com piso em zero)
9. Aplica eventual **choque de sucessão** (seção 5.6) — dilui patrimônio
10. Recalcula `faixa_patrimonio_i(t+1)` com histerese e limites indexados por `g` — se houve transição de faixa (já considerando histerese), re-sorteia `retorno_real_i` da nova distribuição

Resumo das ancoragens de decis:
- **Decil para desemprego e educação:** `renda_trabalho_base_i` (capital humano estrutural). Não pode cair com desemprego do próprio ano — senão um médico desempregado entraria no perfil de risco de um trabalhador informal, o que é circular.
- **Faixa de decil para propensão a consumir:** `renda_total_i(t)` (comportamento adaptativo). Família que enriquece via patrimônio adapta-se à nova classe de consumo; mas o ajuste é estável porque cada família tem sua própria propensão pré-sorteada por faixa (sem flicker).
- **Faixa de patrimônio para retorno real:** `patrimonio_i(t)` com histerese (ver 5.2).

# 4. Inicialização (calibração híbrida com dados reais do Brasil)

Distribuições paramétricas calibradas para reproduzir os momentos observados da PNAD Contínua 2024 (renda), POF 2017–2018 (consumo, patrimônio), IRPF 2023 / Relatório SPE-Fazenda (concentração no topo), Censo 2022 (demografia) e séries históricas do Banco Central (retornos reais). Todas as fontes estão listadas na seção 10.

Todos os valores monetários estão em R$ correntes de 2024 (que serão tratados como R$ de 2026 sob hipótese de preços constantes).

## 4.0 Demografia e referência agregada

| Parâmetro | Valor | Fonte |
|-----------|-------|-------|
| Tamanho médio do domicílio | 2,79 pessoas | Censo 2022 |
| Renda média real per capita (2024) | R$ 2.020/mês | PNAD Contínua 2024 |
| Renda média real per capita do bottom 50% (2024) | R$ 713/mês | PNAD Contínua 2024 |
| Renda média do bottom 40% | R$ 601/mês | PNAD Contínua 2024 |
| Renda média do top 10% | R$ 8.034/mês | PNAD Contínua 2024 |
| Razão top 10% / bottom 40% | 13,4× | PNAD Contínua 2024 |
| Gini da renda domiciliar per capita | 0,506 (2024) | PNAD Contínua 2024 |
| Top 1% da renda nacional | 27,4% | WID/IRPF Brasil |
| Top 0,1% (≈ 150 mil indivíduos) | Renda média R$ 4,6M/ano | WID/IRPF Brasil |
| Top 0,01% (≈ 15 mil indivíduos) | Renda média R$ 23M/ano | WID/IRPF Brasil |

Como a unidade do modelo é a **família** (domicílio), todos os valores per capita são multiplicados por 2,79 para obter os agregados familiares:

| Métrica per capita | × 2,79 | Métrica domiciliar (família) |
|--------------------|--------|------------------------------|
| R$ 2.020/mês       |        | R$ 5.636/mês ≈ R$ 67.630/ano (média) |
| R$ 713/mês         |        | R$ 1.989/mês ≈ R$ 23.870/ano (média bottom 50%) |
| R$ 8.034/mês       |        | R$ 22.415/mês ≈ R$ 269.000/ano (média top 10%) |

## 4.1 Renda do trabalho inicial (distribuição log-normal com cauda Pareto)

A renda do trabalho anual da família `i` é amostrada de uma distribuição mista: log-normal para o corpo (percentis 0–99) e Pareto para a cauda (top 1%). Essa estrutura é necessária porque uma log-normal pura subestima sistematicamente a concentração no topo brasileiro.

### Corpo da distribuição (percentis 0–99)

```
ln(renda_trabalho_base_i) ~ Normal(μ_r, σ_r²)
```

Parâmetros calibrados para reproduzir o Gini e a média de 2024:

| Parâmetro | Valor | Derivação |
|-----------|-------|-----------|
| `μ_r` | **10,65** | calibrado para média = R$ 67.630/ano (renda domiciliar média 2024 × 2,79) |
| `σ_r` | **0,97**  | derivado de Gini = 0,506 via `Gini = 2·Φ(σ/√2) − 1` |

Verificação:
- Mediana = exp(10,65) ≈ **R$ 42.300/ano** (≈ R$ 3.525/mês para a família, R$ 1.264/mês per capita)
- Média = exp(10,65 + 0,97²/2) ≈ **R$ 67.630/ano** (≈ R$ 5.636/mês)
- Razão top 10% / bottom 40% esperada ≈ 12–14× (faixa observada em 2024: 13,4×)

### Cauda Pareto (top 1%)

Para reproduzir a participação observada do top 1% na renda total (27,4%), substituir as observações do top 1% (acima do percentil 99) por amostras de uma Pareto:

```
renda ~ Pareto(x_min_r, α_r), com:
x_min_r = exp(μ_r + 2,326·σ_r) ≈ R$ 405.000/ano  (percentil 99 do corpo log-normal)
α_r     = 1,5   (calibrado para top 0,01% / top 0,1% ≈ 5, observado nos dados WID)
```

Importante: **a substituição não é independente da do patrimônio**. A renda e o patrimônio são amostrados conjuntamente (Normal bivariada na 4.2), e a substituição Pareto da renda usa o **mesmo procedimento de ordenação** descrito na 4.2 (passo 3) para preservar a correlação ρ no topo. Ou seja, a família com o maior `ln_renda_aux` recebe o maior valor Pareto de renda; a família com o maior `ln_patrimonio_aux` recebe o maior valor Pareto de patrimônio; e como `ln_renda_aux` e `ln_patrimonio_aux` são correlacionados, há sobreposição parcial natural entre top 1% renda e top 1% patrimônio (consistente com a observação brasileira: alta mas imperfeita).

Verificação: com α_r = 1,5, a renda média do top 1% fica em ≈ 3× o limiar x_min_r ≈ R$ 1,2M/ano, e o top 0,1% médio fica em ≈ R$ 4–5M/ano, consistente com a observação WID.

### Calibração-alvo (validação após implementação)

| Indicador | Alvo brasileiro | Tolerância |
|-----------|-----------------|------------|
| Mediana renda família | R$ 42.000–48.000/ano | ±10% |
| Gini renda do trabalho | 0,52 | ±0,02 |
| Razão top 10% / bottom 40% | 13,4× | ±2 |
| Share top 1% na renda | 27% | ±3 p.p. |

## 4.2 Patrimônio inicial (log-normal correlacionada + cauda Pareto)

A distribuição patrimonial brasileira é muito mais concentrada que a de renda (Gini ≈ 0,82 vs. 0,51). Calibração combina log-normal correlacionada com a renda + cauda Pareto.

### Procedimento de amostragem conjunta renda–patrimônio

A amostragem é feita em **um único passo bivariado**, garantindo que a correlação observada renda–patrimônio seja preservada em todo o suporte (corpo e cauda). Procedimento:

**Passo 1 — Sortear log-renda auxiliar e log-patrimônio auxiliar conjuntamente (Normal bivariada):**

```
(ln_renda_aux_i, ln_patrimonio_aux_i) ~ Normal2(
    μ = [μ_r, μ_p],
    Σ = [[σ_r²,        ρ·σ_r·σ_p],
         [ρ·σ_r·σ_p,   σ_p²     ]]
)
```

| Parâmetro | Valor | Derivação |
|-----------|-------|-----------|
| `μ_p` | **11,00** | mediana de R$ 60.000 (≈ valor de imóvel próprio mediano + reserva mínima) |
| `σ_p` | **1,90**  | calibrado para Gini patrimonial ≈ 0,82 via fórmula log-normal |
| `ρ` (correlação log-renda × log-patrimônio) | **0,60** | ver justificativa empírica abaixo |

**Passo 2 — Aplicar a substituição Pareto na RENDA do top 1%, preservando o ranking:**

```
Para as famílias do top 1% por ln_renda_aux_i, ordenadas crescentemente:
    renda_trabalho_base_i = quantil_Pareto(rank_i / (n_top + 1); x_min_r, α_r)
Para as demais famílias:
    renda_trabalho_base_i = exp(ln_renda_aux_i)
```

Onde `x_min_r ≈ R$ 405.000/ano` e `α_r = 1,5` conforme seção 4.1.

**Passo 3 — Aplicar a substituição Pareto no PATRIMÔNIO do top 1%, preservando o ranking:**

```
Para as famílias do top 1% por ln_patrimonio_aux_i, ordenadas crescentemente:
    patrimonio_i = quantil_Pareto(rank_i / (n_top + 1); x_min_p, α_p)
Para as demais famílias:
    patrimonio_i = exp(ln_patrimonio_aux_i)
```

```
Pareto(x_min_p, α_p):
x_min_p ≈ R$ 2.300.000  (limiar do top 1% patrimonial, Monsieur-Lifestyle 2024)
α_p     = 1,25         (calibrado para top 1% deter 40–45% do patrimônio agregado)
```

Esse procedimento garante:
- Correlação renda–patrimônio preservada no corpo (via Σ da Normal bivariada).
- Correlação renda–patrimônio preservada **também na cauda** (via ordenação dentro de cada variável: como `ln_renda_aux` e `ln_patrimonio_aux` são correlacionados, as famílias do top 1% de renda **tendem a ser** as do top 1% de patrimônio — mas não com sobreposição perfeita, exatamente como no Brasil real).
- Não há saltos artificiais entre corpo e cauda em nenhuma das duas variáveis.

Verificação:
- Mediana patrimonial (todas as famílias) ≈ R$ 60.000
- Média do corpo ≈ R$ 365.000
- Média do top 1% (Pareto com α_p = 1,25) ≈ 5× x_min ≈ R$ 11,5M
- Top 0,1% chega a R$ 60–80M — consistente com Global Wealth Report

### Justificativa empírica do `ρ = 0,60`

Não há estimativa direta publicada da correlação log(renda) × log(patrimônio) para o Brasil, mas há evidências indiretas convergentes:

| Evidência | Implicação |
|-----------|-----------|
| EUA 2022–23: correlação Pearson renda × patrimônio líquido = **0,559** (dqydj.com) | Referência internacional para país com concentração patrimonial menor que a brasileira |
| Top 1% brasileiro: **>1/3 da renda vem do capital** (lucros + dividendos + ganhos financeiros), IRPF 2020 | Renda de capital depende do estoque patrimonial → correlação positiva forte no topo |
| Top 0,1% (2017–2023): **90% do aumento de concentração de renda** vem do capital, sendo 66% de dividendos (Observatório de Política Fiscal FGV-IBRE) | Renda e patrimônio crescem juntos no topo brasileiro, indicando correlação ainda mais alta que EUA |
| POF 2017–2018: famílias <2 SM com variação patrimonial 1,1% da renda; famílias >25 SM com 15,3% | Quem ganha mais acumula mais (consistente com ρ > 0,5) |

Conclusão: como o Brasil tem topo mais dominado por capital que os EUA, a correlação log–log esperada deve ser **levemente superior** a 0,56 — por isso adotamos **ρ = 0,60**, valor conservador (não exagerado) e dentro da faixa razoável de 0,55–0,70.

### Composição implícita do patrimônio

Não modelamos imóvel vs. financeiro separadamente, mas a calibração reflete a composição observada (IRPF 2023):

| Faixa | Composição típica (referência IRPF) |
|-------|-------------------------------------|
| Bottom 50%  | ~85% imóvel próprio + bens duráveis, ~15% poupança |
| Decil 6–9   | ~60% imóvel + ~25% financeiro conservador + ~15% outros |
| Top 10%     | ~40% imóvel + ~50% financeiro (CDB/Tesouro/multimercado) + ~10% outros |
| Top 1%      | ~25% imóvel + ~65% financeiro (renda variável/private equity) + ~10% outros |

Essa composição justifica os retornos diferenciados por faixa (seção 4.4). Agregado nacional declarado (IRPF 2023): 50,2% financeiro, 36,7% imóveis, 6,7% outros, 6,4% bens móveis.

### Calibração-alvo (validação após implementação)

| Indicador | Alvo brasileiro | Tolerância |
|-----------|-----------------|------------|
| Mediana patrimônio | R$ 55.000–70.000 | ±15% |
| Gini patrimonial | 0,82 | ±0,02 |
| Share top 1% no patrimônio | 40–50% (IRPF: 37%, Credit Suisse: 49,6%) | ±5 p.p. |
| Share top 10% no patrimônio | 64% (IRPF) | ±5 p.p. |
| % famílias com patrimônio > R$ 5M (faixa 4) | ≈ 0,4–0,6% | — |
| % famílias com patrimônio < R$ 50k (faixa 1) | ≈ 45–55% | — |

## 4.3 Propensão a consumir (calibrada à POF — vetor pré-sorteado, lookup dinâmico)

A propensão a consumir efetiva de cada família muda quando ela transita entre faixas de decil de renda total. Para evitar oscilação artificial e preservar heterogeneidade individual, **cada família sorteia, na inicialização, um vetor `c_faixa_decil_i` de 5 propensões — uma para cada faixa de decil** — e usa, em cada ano `t`, a propensão correspondente à sua faixa vigente.

```
c_faixa_decil_i = [c1, c2, c3, c4, c5]   (sorteado uma vez na inicialização)
propensao_consumir_i(t) = c_faixa_decil_i[ faixa_decil_renda_total_i(t) ]
```

Distribuições por faixa, calibradas à POF 2017–2018:

| Faixa de decil | Faixas | `c_k ~ ...` | Variação patrimonial observada (POF) |
|----------------|--------|-------------|--------------------------------------|
| 1 | Decil 1–3   | `Uniform(0,97; 1,00)` | 1,1% da renda (famílias < 2 SM) |
| 2 | Decil 4–7   | `Uniform(0,88; 0,97)` | 3–6% da renda |
| 3 | Decil 8–9   | `Uniform(0,75; 0,88)` | 8–12% da renda |
| 4 | Decil 10 (excl. top 1%) | `Uniform(0,55; 0,75)` | 13–18% da renda |
| 5 | Top 1%      | `Uniform(0,30; 0,55)` | 15,3% da renda (famílias > 25 SM, POF) |

Justificativa do desenho dinâmico: uma família do decil 2 que sobe via choques de educação para o decil 9 não continuaria consumindo 99% da renda como na pobreza — ela adapta o estilo de vida à nova classe. Por outro lado, **dentro de uma faixa, a propensão é constante** (sem oscilação artificial), porque os 5 valores são pré-sorteados e fixos para a família. Família "frugal de natureza" e família "esbanjadora de natureza" mantêm posições relativas dentro de cada classe ao longo da vida.

Justificativa empírica dos valores: a POF 2017–2018 mostra que famílias até 2 SM têm variação patrimonial líquida de apenas 1,1% da renda (consomem ~99% da renda monetária + não-monetária), enquanto famílias acima de 25 SM acumulam 15,3% da renda em variação patrimonial.

Calibração-alvo agregada: taxa de poupança das famílias ≈ 7–10% da renda disponível (compatível com a média histórica brasileira recente segundo o Banco Central).

## 4.4 Retorno real do patrimônio (sorteio por faixa vigente)

Para cada família `i`, sortear `retorno_real_i` na inicialização com base na faixa de patrimônio em 2026. Esse retorno permanece fixo enquanto a família estiver na mesma faixa. Se a família mudar de faixa em algum ano, sorteia-se um **novo retorno** da distribuição da nova faixa (ver seção 5.2).

### Calibração com retornos reais históricos brasileiros

O retorno por faixa abaixo reflete (a) a composição típica observada na seção 4.2 e (b) a hipótese estrutural de que a Selic real brasileira convergirá para níveis mais baixos no longo prazo (~3% real ao invés de 8%).

| Faixa | Patrimônio | Composição implícita | Distribuição de `retorno_real_i` |
|-------|------------|----------------------|-----------------------------------|
| 1 | < R$ 50k         | Poupança + bens duráveis (não-investimento)         | `Normal(1,0%; 1,0%)` truncada em [−2%; 3%]  |
| 2 | R$ 50k – 500k    | Imóvel próprio + Tesouro Selic / CDB                | `Normal(3,0%; 1,5%)` truncada em [−1%; 5%]  |
| 3 | R$ 500k – 5M     | Diversificado moderado (RF longa + multimercado)    | `Normal(5,0%; 2,5%)` truncada em [−1%; 11%] |
| 4 | > R$ 5M          | Renda variável + private equity + imóveis comerciais | `Normal(5,0%; 2,5%)` truncada em [−1%; 11%] |

Observações:
- Famílias dentro da mesma faixa têm retornos diferentes, o que gera dispersão dos resultados de longo prazo entre famílias semelhantes.
- A truncagem evita valores extremos que destruiriam a coerência numérica em 100 anos.
- Não há ruído anual: o retorno é fixo enquanto a faixa não muda. A reamostragem só ocorre em transição de faixa.
- Calibração-alvo agregada: retorno real médio do patrimônio total ≈ 3,5–4% a.a. (consistente com Selic real estrutural projetada + prêmio de risco médio do mix da carteira agregada).

Nota técnica: com a cauda Pareto patrimonial (4.2) e retorno médio 5% nas faixas 3–4, o agregado bruto antes da diluição sucessória tende a 4,5–5% a.a. Após aplicar o choque de sucessão (5.6) — que dilui ~1,8% a.a. em média — o **retorno real líquido agregado realizado** fica em torno de 2,7–3,2% a.a., compatível com a Selic real estrutural brasileira projetada.

## 4.5 Validação da inicialização (passo zero)

Antes de simular qualquer ano, executar uma rotina de validação que verifica se as amostras iniciais batem com os alvos da seção 4. Se o desvio exceder a tolerância, recalibrar μ, σ, α e re-amostrar. A simulação só inicia após validação aprovada.

Indicadores a verificar em 2026:
- Gini renda do trabalho ≈ 0,52 (tol. ±0,02)
- Gini patrimonial ≈ 0,82 (tol. ±0,02)
- Mediana renda família R$ 42–48 mil/ano (tol. ±10%)
- Mediana patrimônio R$ 55–70 mil (tol. ±15%)
- Share top 1% na renda 25–30%
- Share top 1% no patrimônio 40–50%
- Razão top 10% / bottom 40% (renda) entre 11× e 16×
- % famílias na faixa 1 (patrimônio < R$ 50k): 45–55%
- % famílias na faixa 4 (patrimônio > R$ 5M): 0,4–0,6%
- Taxa de desemprego inicial ≈ 7,9% (calibrada à PNAD 2024)
- **Correlação renda × patrimônio realizada:**
  - Pearson(ln_renda, ln_patrimônio) entre **0,55 e 0,65** (alvo: 0,60)
  - Spearman(rank_renda, rank_patrimônio) entre **0,55 e 0,68**
  - % famílias do top 10% de renda que também estão no top 10% de patrimônio: **≥ 50%** (Brasil real: ~55–65%)
  - % famílias do top 1% de renda que também estão no top 1% de patrimônio: **≥ 25%** (a sobreposição não é perfeita: rentistas vs. assalariados de alta renda)

Inicialização do `status_emprego_i(0)`: amostrar aleatoriamente para que a proporção de desempregados em cada **decil de `renda_trabalho_base_i`** (mesma ancoragem usada na dinâmica, seção 5.3) bata com a heterogeneidade da PNAD 2024 (decil 1–3: ~11%, decil 4–9: ~6%, decil 10: ~2,5%).

# 5. Dinâmica anual

A cada ano `t`, para cada família `i`:

## 5.1 Renda disponível do ano

```
renda_trabalho_i(t) = renda_trabalho_base_i × (1 + g)^(t - 2026) × choque_emprego_i(t)
elegivel_i(t)       = (LIMIAR_USA_RENDA_TOTAL? renda_total_provisoria_i(t)/2,79 : renda_trabalho_i(t)/2,79) < LIMIAR
transferencia_i(t)  = TRANSFERENCIA_BASE × 2,79 × 12 se elegivel_i(t) else 0   (anual; per capita × moradores × meses)
renda_total_i(t)    = renda_trabalho_i(t) + transferencia_i(t) + retorno_patrimonio_i(t)
```

- `g` — crescimento real agregado anual da renda (parâmetro; default 0% a.a.)
- `choque_emprego_i(t)` — 1 se empregado, (1 - α_seguro) se desempregado (α_seguro = 0,7 → família perde 70% da renda do trabalho)
- `TRANSFERENCIA_BASE` (R$/mês per capita) e `LIMIAR` (R$/mês per capita) — parâmetros de política (default 0)
- `LIMIAR_USA_RENDA_TOTAL` — boolean. `False` (default): elegibilidade pela renda do trabalho per capita (mais simples). `True`: elegibilidade pela renda total per capita (mais próximo de Bolsa Família / BPC); nesse caso, calcula-se `renda_total_provisoria` antes da transferência usando trabalho + retorno do patrimônio.

## 5.2 Retorno real sobre o patrimônio (com histerese e limites indexados a `g`)

```
retorno_patrimonio_i(t) = retorno_real_i(t) × patrimonio_i(t)
```

### Limites das faixas indexados ao crescimento agregado

Para evitar "bracket creep" sob crescimento positivo (`g > 0`), os limites de patrimônio das faixas crescem com a economia, mantendo o **poder de compra constante**:

```
limite_k(t) = limite_k_inicial × (1 + g)^(t − 2026)
```

Onde `limite_k_inicial` é o limite da faixa `k` em R$ de 2026, conforme seção 4.4: R$ 50k entre faixas 1↔2; R$ 500k entre 2↔3; R$ 5M entre 3↔4. Com o default `g = 0%`, os limites permanecem constantes.

### Histerese para evitar "flicker" nas fronteiras

Famílias com patrimônio próximo ao limite de faixa oscilariam artificialmente, re-sorteando retornos a cada pequeno movimento. Adotamos **bandas de ±10%** em torno de cada limite:

```
Para subir da faixa k para k+1, é necessário: patrimonio_i(t) > limite_k(t) × 1,10
Para descer da faixa k para k-1, é necessário: patrimonio_i(t) < limite_(k-1)(t) × 0,90
Caso contrário, a família permanece na faixa anterior.
```

Em valores de 2026 (com `g = 0`):

| Transição | Limite nominal | Para subir | Para descer |
|-----------|----------------|------------|-------------|
| Faixa 1 ↔ 2 | R$ 50.000  | > R$ 55.000  | < R$ 45.000  |
| Faixa 2 ↔ 3 | R$ 500.000 | > R$ 550.000 | < R$ 450.000 |
| Faixa 3 ↔ 4 | R$ 5.000.000 | > R$ 5.500.000 | < R$ 4.500.000 |

### Regra de re-sorteio

```
faixa_anterior = faixa_patrimonio_i(t-1)
faixa_atual    = faixa_com_histerese(patrimonio_i(t), faixa_anterior, t)

se faixa_atual != faixa_anterior:
    retorno_real_i(t) = sorteio da distribuição da faixa_atual (ver seção 4.4)
senão:
    retorno_real_i(t) = retorno_real_i(t-1)
```

Sem ruído anual: o retorno é fixo enquanto a faixa não muda. A reamostragem só ocorre em transição efetiva de faixa (já considerada a histerese).

A heterogeneidade dos retornos entre famílias é o **principal mecanismo de desigualdade** ativo no modelo (Piketty: r heterogêneo > g). A desigualdade emerge de três fontes: (i) famílias mais ricas operam em faixas com média de retorno mais alta; (ii) dispersão dentro de cada faixa cria trajetórias divergentes entre famílias semelhantes; (iii) famílias que sobem ou descem de faixa têm seu retorno re-sorteado, o que pode acelerar ou frear sua trajetória.

## 5.3 Choque de emprego (calibrado à PNAD Contínua)

Cadeia de Markov de 2 estados por família. A PNAD Contínua 2024 mostra desemprego médio nacional ≈ 7,9% (Q1/2024), com forte heterogeneidade por escolaridade (3,9% no superior completo, 5,6% sem instrução, com picos > 14% nos jovens 18–24).

Probabilidades dependem do **decil de `renda_trabalho_base_i`** (não da renda total vigente), evitando o loop circular onde um médico desempregado entraria no perfil de risco de um trabalhador informal apenas porque sua renda corrente caiu. O `renda_trabalho_base_i` representa o capital humano estrutural — sobe com choque de educação, mas não cai com desemprego.

| Decil de `renda_trabalho_base_i` | `P(desempregar | empregado)` (a.a.) | Justificativa |
|----------------------------------|-------------------------------------|---------------|
| Decil 1–3 | 8% a.a. | desemprego empírico nesta faixa ≈ 10–12% (baixa escolaridade) |
| Decil 4–9 | 4% a.a. | desemprego empírico ≈ 5–7% |
| Decil 10  | 1,5% a.a. | desemprego empírico ≈ 2–3% (superior completo) |

```
P(reempregar | desempregado) ≈ 50% a.a.  →  duração esperada do desemprego ≈ 2 anos
```

Justificativa da duração: PNAD 2024 reporta ≈ 1,4 milhão de pessoas há ≥ 24 meses buscando emprego (≈ 17% dos desempregados), com média de busca em torno de 18–24 meses.

Choques são a principal fonte de mobilidade descendente no modelo. Em estado estacionário com essas probabilidades, a taxa de desemprego média do modelo deve ficar em torno de 7–9%, batendo com a PNAD.

## 5.4 Choque de educação (mobilidade ascendente)

Simétrico ao choque de desemprego, mas em sentido oposto: representa eventos que elevam permanentemente a capacidade de geração de renda (conclusão de curso, qualificação técnica, salto de carreira).

- A cada ano, cada família com `n_choques_edu_i(t) < MAX_CHOQUES_EDU` tem probabilidade `p_edu` de receber um choque de educação.
- `p_edu` depende do **decil de `renda_trabalho_base_i`** (capital humano estrutural; mesmo critério usado em 5.3, para coerência):
  - Decil 1–3: 1,2% a.a.
  - Decil 4–6: 1,5% a.a.
  - Decil 7–9: 0,8% a.a.
  - Decil 10: 0,2% a.a.
- Quando o choque ocorre, `renda_trabalho_base_i` é multiplicada por um fator `f ~ Uniform(1,15; 1,35)` (ganho permanente de 15% a 35%) e `n_choques_edu_i` é incrementado.
- Teto: `MAX_CHOQUES_EDU = 3` por família ao longo dos 100 anos (representa trajetória de carreira realista: ensino médio → técnico/superior → especialização/promoção).

Esse é o principal mecanismo de mobilidade ascendente do modelo.

Calibração-alvo (literatura de mobilidade intergeracional brasileira):
- Elasticidade intergeracional de renda no Brasil: 0,42–0,53 (IPEA, dados 2014)
- Apenas ~50% dos brasileiros nascidos nos anos 1980 superaram a renda dos pais (IMDS)
- Brasil tem a menor mobilidade de renda entre países da OCDE

Meta operacional do modelo: 20–25% das famílias do decil 1 inicial devem subir pelo menos um decil de renda em 30 anos.

## 5.5 Consumo e evolução do patrimônio

```
propensao_consumir_i(t) = c_faixa_decil_i[ faixa_decil_renda_total_i(t) ]    (ver 4.3)
consumo_i(t)            = propensao_consumir_i(t) × renda_total_i(t)
poupanca_i(t)           = renda_total_i(t) − consumo_i(t)
patrimonio_pos_poupanca = max(0, patrimonio_i(t) + poupanca_i(t))
```

Restrição: patrimônio não pode ficar negativo. Se família desempregada não conseguir cobrir consumo, consome do patrimônio até zerar; a partir daí, consumo = renda disponível (corte forçado).

## 5.6 Choque de sucessão (mitigação do efeito "clã imortal")

Sem morte e herança no modelo, em 100 anos o efeito `r > g` operando sem interrupção produz uma assíntota de Gini patrimonial irreal: as fortunas nunca são particionadas entre herdeiros nem tributadas (ITCMD). Para corrigir esse artefato **sem precisar criar novos agentes**, introduzimos um *choque de sucessão estocástico*.

```
A cada ano t, para cada família i:
  com probabilidade p_sucessao:
    n_herdeiros ~ Uniform{1, 2, 3, 4}   (inteiro)
    fator_diluicao = 1 / n_herdeiros    (∈ {1; 0,5; 0,33; 0,25})
    patrimonio_i(t+1) = patrimonio_pos_poupanca × fator_diluicao
  caso contrário:
    patrimonio_i(t+1) = patrimonio_pos_poupanca
```

| Parâmetro | Default | Interpretação |
|-----------|---------|---------------|
| `p_sucessao` | **3% a.a.** | troca de geração esperada a cada ~33 anos (≈ 3 sucessões em 100 anos por família) |
| `n_herdeiros` ~ Uniform{1,…,4} | média 2,5 | reflete fertilidade brasileira recente (~1,6 filhos por mulher, mas tipicamente 2 filhos por casal); o caso `n=1` representa transmissão integral (sem dispersão) |

Modelagem conceitual: a "família" do modelo continua existindo após a sucessão, mas com patrimônio reduzido — interpretada como "a unidade observada" entre as N herdadas. O patrimônio que saiu não é redistribuído entre outras famílias do modelo (essa abstração permite manter a população fixa em N). O efeito líquido é equivalente a uma taxa de erosão sucessória implícita.

Calibração-alvo: o agregado patrimonial total dilui em média `p_sucessao × E[1 − 1/n_herdeiros] = 0,03 × 0,604 ≈ 1,8% a.a.` do estoque, o que aproximadamente cancela o efeito de retorno real médio de ~4% a.a. nas famílias sem nova poupança. Isso impede que as fortunas se acumulem indefinidamente.

Sensibilidade: na seção 6.3, `p_sucessao` deve ser variável (sweep: 0% a 5% a.a.) para diagnosticar a contribuição da sucessão à dinâmica de longo prazo.

# 6. Parâmetros de política (para análise contrafactual)

Cada simulação roda com um cenário definido por:

| Parâmetro | Default | Faixa de teste |
|-----------|---------|----------------|
| `g` — crescimento da renda | 0% a.a. | 0% a 3% |
| Médias de retorno por faixa (vetor) | [1,0; 3,0; 5,0; 5,0]% | manter conforme seção 4.4; em cenário "Selic baixa estrutural" reduzir top |
| Desvios-padrão dos retornos por faixa | [1,0; 1,5; 2,5; 2,5]% | conforme seção 4.4 |
| `TRANSFERENCIA_BASE` (R$/mês per capita) | R$ 0 | R$ 0 a R$ 600 |
| `LIMIAR` (R$/mês per capita) | — | linha de pobreza (~R$ 218) ou universal |
| `LIMIAR_USA_RENDA_TOTAL` | `False` | `True` para focalização tipo Bolsa Família |
| `α_seguro` desemprego | 0,7 | 0,5 a 0,9 |
| `MAX_CHOQUES_EDU` | 3 | 1 a 5 |
| `p_sucessao` (choque sucessório) | 3% a.a. | 0% a 5% |
| Banda de histerese de faixa de patrimônio | ±10% | ±5% a ±20% |

## 6.1 Conjunto mínimo de cenários a executar

| ID | Nome | Descrição |
|----|------|-----------|
| `S0` | **baseline** | Parâmetros default da seção 4.4. Sem transferência. |
| `S1` | **selic_baixa** | Retornos `[1,0; 3,0; 3,5; 3,5]%` (compressão estrutural do prêmio de risco para o top). |
| `S2` | **renda_basica_universal** | `TRANSFERENCIA_BASE = R$ 600/mês`, `LIMIAR = ∞` (todos recebem). |
| `S3` | **renda_basica_focalizada** | `TRANSFERENCIA_BASE = R$ 600/mês`, `LIMIAR = R$ 218/mês per capita`, `LIMIAR_USA_RENDA_TOTAL = True`. |
| `S4` | **selic_baixa + renda_basica** | Combinação de S1 e S3. |
| `S5` | **crescimento_alto** | `g = 2% a.a.`, demais como baseline. Limites de faixa indexados automaticamente. |
| `S6` | **sem_sucessao** | `p_sucessao = 0`, demais como baseline. Diagnóstico do efeito "clã imortal" no Gini de longo prazo. |
| `S7` | **sucessao_forte** | `p_sucessao = 5%` (geração ~20 anos). Aproxima cenário de tributação efetiva sobre transmissão. |

## 6.2 Monte Carlo e reprodutibilidade

- Cada cenário roda `N_RUNS = 30` repetições com sementes distintas (`seed = 1000 + i`).
- Todos os sorteios usam uma única instância `rng = numpy.random.default_rng(seed)` propagada explicitamente — nenhuma chamada a `numpy.random.*` global.
- Indicadores anuais (Gini, top shares, percentis) são reportados como média entre runs ± IC95% (banda nas visualizações).
- A implementação deve ser **vetorizada** (operações numpy sobre arrays de tamanho `N_FAMILIAS`), sem loop por família. Loops permitidos apenas sobre anos e sobre runs.

## 6.3 Análise de sensibilidade

Após validar os cenários, fazer sweep univariado nos seguintes parâmetros (variar ±25% mantendo demais fixos) para identificar os mais influentes no Gini patrimonial em 2126:
- `α_p` (expoente Pareto patrimonial)
- `σ_p` (dispersão patrimônio)
- `ρ` (correlação renda–patrimônio)
- Vetor de médias de retorno
- Propensão a consumir do top 1%
- `p_sucessao` (probabilidade do choque sucessório)
- Banda de histerese das faixas de patrimônio

# 7. Outputs

## 7.1 Estrutura de arquivos

Cada cenário grava em `abm-fam-br/output/<cenario_id>/`:

| Arquivo | Conteúdo |
|---------|----------|
| `microdados_<run>.parquet` | painel completo família × ano (compactado; um por run) |
| `series_agregadas.csv` | séries anuais (média entre runs + IC95%) de Gini, top shares, percentis, médias |
| `mobilidade_<run>.parquet` | matriz de transição entre decis a cada 10 anos |
| `decomposicao_variancia.csv` | decomposição anual da variância do crescimento patrimonial |
| `calibracao_inicial.json` | resultado da validação 4.5 |
| `params.json` | dump de todos os parâmetros do cenário |
| `figs/*.png` | todas as visualizações (lista abaixo) |

E em `abm-fam-br/output/comparativos/` ficam visualizações cross-cenário.

## 7.2 Métricas registradas anualmente

- Distribuição patrimonial: percentis 5, 10, 25, 50, 75, 90, 95, 99, 99,9
- Distribuição de renda total: mesmos cortes
- Gini patrimonial; Gini de renda total; Gini de renda do trabalho
- Top shares: share do top 0,1%, 1%, 5%, 10%; share do bottom 50%
- Razão Palma (top 10% / bottom 40%)
- Razão top 1% / bottom 50%
- % famílias em cada faixa de patrimônio (1–4)
- Patrimônio médio e mediano por faixa
- Taxa de desemprego média
- % famílias que receberam pelo menos um choque de educação
- Retorno real médio agregado realizado
- Renda agregada do trabalho vs. renda agregada do patrimônio (relação "r vs. g" agregada)

## 7.3 Visualizações (geradas por cenário)

Trajetórias temporais (linhas, eixo X = anos 2026–2126, bandas IC95%):
1. Gini patrimonial e Gini de renda total (mesmo gráfico)
2. Top shares (top 0,1%, 1%, 10%) e bottom 50%
3. Percentis patrimoniais (P10, P50, P90, P99) em escala log
4. Razão Palma e razão top 1% / bottom 50%
5. % de famílias em cada faixa de patrimônio (stacked area)
6. Taxa de desemprego agregada
7. Razão renda do patrimônio / renda do trabalho (decomposição "r vs. g")
8. Retorno real agregado realizado vs. retorno-alvo

Distribuições (instantâneo nos anos 2026, 2076, 2126):
9. Histograma + KDE de log(patrimônio) com 3 anos sobrepostos
10. Histograma + KDE de log(renda total) com 3 anos sobrepostos
11. Curva de Lorenz patrimonial com 3 anos sobrepostos
12. Curva de Lorenz de renda com 3 anos sobrepostos
13. Pareto plot (log-log da cauda) do patrimônio em 2126
14. Composição da distribuição patrimonial por faixa (stacked bar)

Heterogeneidade e mobilidade:
15. Heatmap da matriz de transição entre decis patrimoniais (2026 → 2076, 2076 → 2126, 2026 → 2126)
16. Sankey/alluvial da mobilidade entre faixas 1–4 ao longo de 100 anos
17. Boxplot do patrimônio em 2126 condicionado ao decil de renda inicial
18. **Scatter renda × patrimônio em 2026 e 2126** (eixos log–log, com linha de regressão, ρ de Pearson e Spearman exibidos no título; também marcar visualmente o top 1% e o top 0,1% para diagnóstico da cauda)
18b. **Heatmap conjunto de decis de renda × decis de patrimônio em 2026** (10×10; diagonal forte = correlação alta; permite ver onde estão rentistas e assalariados de alta renda separadamente)
19. Trajetórias individuais de 10 famílias representativas amostradas por percentil inicial

Mecanismos e diagnóstico:
20. Decomposição da variância do crescimento patrimonial (stacked area: retorno desigual / poupança desigual / desemprego / educação)
21. Contribuição marginal de cada mecanismo para o Gini ao longo do tempo
22. Histograma da propensão a consumir efetiva por faixa
23. Distribuição empírica do `retorno_real_i` realizado por faixa
24. Densidade de choques de educação acumulados por família ao final dos 100 anos
25. Gini intra-faixa (4 painéis, um por faixa)

## 7.4 Visualizações comparativas entre cenários (`output/comparativos/`)

26. Trajetória do Gini patrimonial nos 6 cenários, sobrepostas
27. Trajetória do share top 1% nos 6 cenários
28. Trajetória do share bottom 50% nos 6 cenários
29. Distribuição patrimonial em 2126 comparada entre cenários (KDE)
30. Razão Palma final por cenário (bar chart)
31. % de famílias na faixa 1 em 2126 por cenário
32. Curva de Lorenz patrimonial 2126 sobrepondo todos cenários
33. "Custo" da política em transferência total vs. ganho de Gini (scatter eficiência)
34. Resumo executivo (tabela renderizada como imagem): Gini, top 1%, bottom 50%, mobilidade — em 2076 e 2126 por cenário

## 7.5 Padrões técnicos das figuras

- Backend: `matplotlib` (estática) e `plotly` opcional para sankey/alluvial interativo
- Resolução 150 dpi, formato PNG
- Paleta com daltonismo-safe (`viridis` ou `tab10`)
- Eixos sempre com unidade e fonte
- IC95% como banda translúcida nas trajetórias entre runs

# 8. Variáveis exógenas

- `g` — crescimento real agregado da renda (parâmetro de cenário)
- Vetor de retornos reais por faixa (parâmetro de cenário)
- Parâmetros de política (transferência, seguro-desemprego)

# 9. O que NÃO é tratado (com justificativa)

| Não tratado | Por quê |
|-------------|---------|
| Inflação | Tudo em preços constantes; modelo é real |
| Empresas | Famílias só veem renda líquida |
| Governo (tributação) | Renda já é líquida; políticas entram via transferências |
| **Ciclo de vida (idade da família)** | **Decisão de escopo: simplifica o modelo. Limitação: não captura aposentadoria nem decumulação.** |
| **Herança / morte / nascimento de famílias** | **Não modelados explicitamente** (não há criação ou remoção de agentes). **O efeito sucessório agregado é capturado via `choque de sucessão` (seção 5.6)**, que dilui o patrimônio individual periodicamente representando a partilha entre herdeiros. Limitação remanescente: não é possível testar políticas específicas de tributação sobre transmissão (ITCMD) com discriminação por valor herdado, mas é possível testar variações na intensidade média da sucessão via `p_sucessao`. |
| Dívidas | Patrimônio mínimo é zero (não modela crédito) |
| Variação populacional | Quantidade de famílias constante |
| Imóvel separado de financeiro | Patrimônio é agregado; composição é tratada implicitamente via retorno por faixa |
| Conversão decil per capita ↔ decil domiciliar | Ignorada. O modelo trata a família como unidade homogênea (2,79 moradores). Famílias grandes com renda alta podem ter renda per capita baixa no Brasil real, mas isso não é modelado. |

# 10. Fontes para calibração

Fontes oficiais e estudos utilizados nos parâmetros da seção 4 e 5:

## Renda e desigualdade (PNAD Contínua)
- IBGE — *Rendimento de todas as fontes 2024* (Pnad Contínua). Renda domiciliar per capita média R$ 2.020/mês; Gini 0,506; bottom 50% com R$ 713/mês; razão top 10% / bottom 40% = 13,4×; top 10% com R$ 8.034/mês; bottom 40% com R$ 601/mês.
- IBGE — *Síntese de Indicadores Sociais* e *Pnad Contínua Trimestral 2024* (rendimento médio do trabalho R$ 3.208/mês, ocupados).

## Concentração no topo (renda e patrimônio)
- Ministério da Fazenda / SPE — *Relatório da Distribuição Pessoal da Renda e da Riqueza 2025* (com base no IRPF 2023). Top 1% concentra 37,3% do patrimônio declarado; top 5% concentra 54,7%; top 10% concentra 64,2%. Composição patrimônio agregado declarado: 50,2% financeiro, 36,7% imóveis, 6,7% outros, 6,4% bens móveis.
- WID/World Inequality Database e Tax Observatory — *Inequality in Brazil: Income, Wealth and Tax Distribution* (2024). Top 1% concentra 27,4% da renda nacional total; top 0,1% (≈150 mil pessoas): renda média R$ 4,6M/ano; top 0,01% (≈15 mil pessoas): R$ 23M/ano.
- IRPF 2020 (estudo SciELO / Observatório de Política Fiscal FGV-IBRE): top 1% concentra 51% do rendimento do capital.
- Credit Suisse / UBS — *Global Wealth Report 2022/2023*. Brasil com ≈ 413 mil milionários em USD; top 1% concentra 49,6% da riqueza (2021).

## Consumo e patrimônio das famílias (POF)
- IBGE — *Pesquisa de Orçamentos Familiares 2017–2018: Rendimentos, Despesas e Variação Patrimonial*. Famílias <2 SM: 1,1% da renda em variação patrimonial; famílias >25 SM: 15,3%. Famílias de baixa renda destinam 61,2% dos gastos a alimentação e habitação. Cerca de ¼ da renda disponível é não-monetária (aluguel imputado, autoconsumo).
- BCB — *Taxa de poupança das famílias: análise para Brasil e regiões* (Estudos Especiais nº 107).

## Demografia
- IBGE — *Censo Demográfico 2022, Características dos Domicílios*. 90 milhões de domicílios; 2,79 moradores por domicílio (queda em relação a 3,31 em 2010).

## Retornos reais históricos
- BCB / IBGE — *Selic real (ex-post) deflacionada pelo IPCA*. Médias: 2000–2007: 11,3%; 2008–2017: 5,2%; 2018–2019: 2,3%; ciclo 2021–2023 atinge 13,75% nominal.
- Ibovespa real médio (30 anos, deflacionado IPCA): ≈ 4,6% a.a.
- CDI real médio (30 anos): ≈ 5–8% a.a. (com viés de juros historicamente altos).
- FipeZap / IGMI-C / IVG-R: aluguel residencial bruto recente ≈ 5,96% a.a.; valorização real moderada em ciclos longos.

## Mercado de trabalho
- IBGE — *Pnad Contínua Trimestral 2024*. Taxa de desocupação 7,9% (Q1/2024) decrescente; superior completo: 3,9%; sem instrução: 5,6%; jovens 18–24: 14,9%. Desempregados há ≥24 meses: ≈1,4 milhão em 2025.

## Mobilidade social
- IPEA — *Mobilidade intergeracional de renda no Brasil* (Pero; Repositório IPEA). Elasticidade intergeracional 0,42–0,53 em 2014, em queda histórica.
- IMDS — *Mobilidade social no Brasil*. Brasil tem a menor mobilidade intergeracional entre países da OCDE. Apenas ~50% dos nascidos nos anos 1980 superaram a renda paterna.

## Outras referências para distribuições
- Pareto / log-normal: literatura de tributação ótima (SciELO Brasil, IPEA TD 2449) e estimação de cauda Pareto (Pareto models for top incomes and wealth, JEI 2021).
- Monsieur-Lifestyle Wealth Report 2024: limiar do top 1% patrimonial Brasil ≈ R$ 2,3 milhões.

## Correlação renda–patrimônio
- DQYDJ (2024) — *Correlation of Income and Net Worth in America*: correlação Pearson renda total × patrimônio líquido = 0,559 (Survey of Consumer Finances, EUA 2022–23). Referência internacional para país com concentração patrimonial menor que a brasileira.
- Observatório de Política Fiscal FGV-IBRE / Nota Técnica 2025 — *Concentração de renda no Brasil: o que os dados do IRPF revelam?*: 90% do aumento da concentração no top 0,1% (2017–2023) vem de renda de capital, sendo 66% de dividendos. Top 1% passou de 20,4% para 24,3% da renda nacional.
- Medeiros et al. — *A composição da renda no topo da distribuição: evolução no Brasil entre 2006 e 2012* (Unicamp Economia e Sociedade): no top 1%, menos da metade da renda vem do trabalho; mais de um terço vem do capital (lucros, dividendos, ganhos financeiros). Evidência indireta de correlação positiva forte entre renda e patrimônio no topo.
