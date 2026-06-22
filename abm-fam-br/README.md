# ABM — Microeconomia das famílias brasileiras

Implementação em Python da especificação [`abm-fam-br.md`](abm-fam-br.md): um modelo
baseado em agentes que simula a evolução da desigualdade patrimonial brasileira de
2026 a 2126 sob diferentes cenários de juros, crescimento, desemprego e transferências.

## Como rodar

Python 3.13 com `numpy`, `scipy`, `pandas`, `pyarrow`, `matplotlib`.

```bash
# nesta máquina o Python está em:
PY="C:/Program Files/Python313/python.exe"

# teste rápido (n=500, 5 runs, 3 cenários, sem microdados)
"$PY" main.py --cenarios S0 S2 S6 --rapido

# rodada completa da spec (S0..S7, n=1000, 30 runs, com figuras e microdados)
"$PY" main.py

# alvo final da spec (n=10000)
"$PY" main.py --n-familias 10000 --n-runs 30
```

Saídas em `output/<cenario>/` (séries, params, calibração, microdados, mobilidade,
decomposição de variância, `figs/*.png`) e `output/comparativos/` (figs 26–34).

## Módulos

| Arquivo | Seção da spec | Conteúdo |
|---------|---------------|----------|
| `parametros.py` | §4, §6 | constantes calibradas, cenários S0–S7, decisões [D1]–[D5] |
| `metricas.py` | §7.2 | Gini, top/bottom shares, Palma, decis, transição, decomposição |
| `inicializacao.py` | §4, §4.5 | amostragem bivariada + splice Pareto + validação do passo zero |
| `dinamica.py` | §5, §3.1 | pipeline anual de 10 etapas (vetorizado) |
| `simulacao.py` | §6 | run único + Monte Carlo (média + IC95%) |
| `graficos.py` | §7.3–7.5 | as 34 figuras |
| `main.py` | §7.1 | CLI e gravação dos outputs |

## Decisões de implementação (desvios documentados da spec)

A especificação tem algumas inconsistências numéricas e alvos de calibração
mutuamente incompatíveis. As resoluções estão no cabeçalho de `parametros.py`:

- **[D1]** Cauda Pareto do patrimônio: splice contínuo corpo→cauda em `x_min`
  (em vez de "substituir o top 1%" com descontinuidade). Para a renda recai
  exatamente no "top 1%" da spec.
- **[D2]** Diluição sucessória: `E[1−1/n] = 0,479` (a spec dizia 0,604);
  diluição efetiva ≈ 1,44%/ano com `p_sucessao = 3%`.
- **[D3]** Elegibilidade de transferência: comparação em R$/mês per capita
  (`renda_anual / 2,79 / 12`); a fórmula da spec omitia o `/12`.
- **[D4]** Alvos §4.5 incompatíveis (Gini de renda 0,52 × top 1% renda 27%;
  Gini patr. × top 1% patr. × faixa 4; Pearson × sobreposição de cauda).
  **Decisão do usuário:** priorizar os Ginis (dispersão). Calibração final:
  `μ_r=10,66`, `σ_r=0,97`, `α_r=1,5`, `μ_p=11,0`, `σ_p=1,9`, `α_p=1,35`,
  `x_min_p=2,3M`, `ρ=0,60`. Os shares de topo e a sobreposição ficam como
  indicadores **informativos** (não-gate) na validação.
- **[D5]** Decomposição da variância (fig.20): identidade aditiva
  `Δw = retorno + trabalho×poupança + sucessão` (soma 1). Desemprego e educação
  atuam via renda do trabalho e têm figuras próprias (6 e 24).

## Validação (§4.5)

`inicializacao.validar_inicializacao` classifica cada indicador como **gate**
(precisa passar) ou **info** (desvio documentado [D4]). A média do ensemble
(30 seeds, n=10000) passa todos os 9 gates.
