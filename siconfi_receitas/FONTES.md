# Fontes de Informação — Extrator de Receitas Fiscais

Este documento descreve as quatro fontes de dados consultadas pelo sistema, os relatórios
acessados em cada uma, os parâmetros utilizados nas consultas e as variáveis extraídas.

---

## Visão geral

O sistema coleta três indicadores fiscais para todos os estados e municípios brasileiros,
no período de 2019 a 2025:

| Indicador | Ente |
|---|---|
| ICMS | Estados (incluindo o Distrito Federal) |
| ISS | Municípios |
| Cota-Parte do ICMS | Municípios |

Cada indicador é obtido de até duas fontes independentes, permitindo cruzamento e validação.
Os arquivos de saída são:

- **`receitas_consolidadas.csv`** — formato longo: uma linha por (ente, indicador, ano, fonte)
- **`receitas_pivot.csv`** — formato pivotado: uma linha por (ente, indicador, ano), com uma coluna por fonte

---

## Fonte 1 — DCA / SICONFI (Tesouro Nacional)

### Sistema
**SICONFI** — Sistema de Informações Contábeis e Fiscais do Setor Público Brasileiro,
mantido pela Secretaria do Tesouro Nacional (STN).

### Relatório consultado
**DCA — Declaração de Contas Anuais, Anexo I-C (Balanço Orçamentário de Receitas)**

O DCA é a prestação de contas anual que estados e municípios enviam ao Tesouro.
O Anexo I-C especificamente contém o Balanço Orçamentário de Receitas — o resultado
definitivo da arrecadação no exercício.

### Coluna utilizada
**"Receitas Brutas Realizadas"** — representa o valor total arrecadado no exercício,
antes de qualquer dedução.

### Acesso
API REST pública do Tesouro Nacional:
```
GET https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca
```

### Parâmetros da consulta

| Parâmetro | Valor | Descrição |
|---|---|---|
| `an_exercicio` | 2019 a 2025 | Exercício fiscal |
| `no_anexo` | `DCA-Anexo I-C` | Identificador do anexo |
| `id_ente` | código IBGE do ente | Identificador do estado ou município |

### Códigos de conta consultados

O plano de contas (PCASP) foi alterado em 2022. O sistema aplica os códigos corretos
conforme o exercício:

**Estados**

| Período | Código | Indicador |
|---|---|---|
| 2019–2021 | `RO1.1.1.8.02.1.0` | ICMS |
| 2022–2025 | `RO1.1.1.4.50.1.0` | ICMS |

**Municípios**

| Período | Código | Indicador |
|---|---|---|
| 2019–2021 | `RO1.1.1.8.02.3.0` | ISS |
| 2022–2025 | `RO1.1.1.4.51.1.0` | ISS |
| 2019–2021 | `RO1.7.2.8.01.1.0` | Cota-Parte ICMS |
| 2022–2025 | `RO1.7.2.1.50.0.0` | Cota-Parte ICMS |

### Cobertura
- Todos os 26 estados + Distrito Federal (como ente estadual)
- Todos os ~5.570 municípios, incluindo Brasília (DF como ente municipal)

### Tratamento especial — Distrito Federal
No SICONFI, o Distrito Federal aparece apenas como município (Brasília, código IBGE 5300108).
O sistema inclui o DF também como estado (código IBGE 53) para capturar o ICMS estadual,
traduzindo internamente o código antes de consultar a API.

---

## Fonte 2 — RREO / SICONFI (Tesouro Nacional)

### Sistema
Também o **SICONFI** (mesma API do DCA, endpoint diferente).

### Relatório consultado
**RREO — Relatório Resumido de Execução Orçamentária, Demonstrativo 3
(Receitas Correntes por Fonte/Destinação de Recursos)**

O RREO é publicado bimestralmente. O sistema consulta exclusivamente o **6.º bimestre**
(novembro/dezembro), cujos valores acumulados representam o total do exercício (janeiro a dezembro).

### Coluna utilizada
**"TOTAL (ÚLTIMOS 12 MESES)"** — acumulado do exercício completo.

### Acesso
```
GET https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo
```

### Parâmetros da consulta

| Parâmetro | Valor | Descrição |
|---|---|---|
| `id_ente` | código IBGE do ente | Identificador do estado ou município |
| `an_exercicio` | 2019 a 2025 | Exercício fiscal |
| `nr_periodo` | `6` | 6.º bimestre (acumulado jan–dez) |
| `co_tipo_demonstrativo` | `RREO` | Tipo do demonstrativo |

### Códigos descritivos consultados

O RREO usa identificadores textuais (não numéricos) e não altera conforme o ano.

**Estados**

| Código descritivo | Indicador |
|---|---|
| `ICMSLiquidoExcetoTransferenciasEFUNDEB` | ICMS |

**Municípios**

| Código descritivo | Indicador |
|---|---|
| `ISSLiquidoExcetoTransferenciasEFUNDEB` | ISS |
| `RREO3CotaParteDoICMS` | Cota-Parte ICMS |

### Diferenças em relação ao DCA

| Indicador | Diferença típica |
|---|---|
| ICMS (estados) | ~2,3% a menos no RREO (estrutural: RREO soma bimestres rolantes; DCA usa fechamento anual com ajustes) |
| ISS (municípios) | 0% — valores idênticos ao DCA |
| Cota-Parte ICMS | 0% — valores idênticos ao DCA |

A diferença no ICMS é estrutural, não erro. O DCA é considerado o valor de referência
por tratar-se do demonstrativo de fechamento do exercício.

### Cobertura
Mesma cobertura do DCA: todos os estados e municípios.

---

## Fonte 3 — SIOPS (DATASUS / Ministério da Saúde)

### Sistema
**SIOPS** — Sistema de Informações sobre Orçamentos Públicos em Saúde,
mantido pelo DATASUS (Ministério da Saúde).

### Relatório consultado
**Relatório LRF-Fiscal (Lei de Responsabilidade Fiscal)**

Este relatório apresenta as receitas municipais utilizadas como base de cálculo para
os gastos mínimos em saúde exigidos pela LRF. Contém ISS e Cota-Parte do ICMS.

### Acesso
O SIOPS não oferece API estruturada. O sistema acessa o servidor legado via requisição HTTP POST,
processando o HTML retornado (técnica de *web scraping*):
```
POST http://siops.datasus.gov.br/rel_LRF.php
```

### Parâmetros da consulta (campos do formulário)

| Campo | Valor | Descrição |
|---|---|---|
| `cmbAno` | 2019 a 2025 | Ano de competência |
| `cmbUF` | código numérico da UF (2 dígitos) | Estado (ex.: `41` para o Paraná) |
| `cmbPeriodo` | `2` | Período anual consolidado (janeiro a dezembro) |
| `cmbMunicipio[]` | código IBGE de 6 dígitos | Município (sem o dígito verificador) |
| `BtConsultar` | `Consultar` | Aciona a consulta |

### Extração dos valores
O sistema localiza as linhas da tabela HTML pelos seguintes rótulos:

| Rótulo buscado | Indicador |
|---|---|
| "Receita Resultante do Imposto sobre Serviços de Qualquer Natureza - ISS" | ISS |
| "Receita Resultante do Imposto sobre Serviços de Qualquer Natureza" | ISS (rótulo alternativo) |
| "Cota-Parte do ICMS" | Cota-Parte ICMS |

O valor extraído corresponde à **4.ª célula** da linha identificada pelo rótulo
(posição do valor anual consolidado no layout da tabela).

### Cobertura
Municípios apenas (o SIOPS/LRF não cobre estados).

### Restrições operacionais
Por ser um servidor legado e frágil, as consultas são feitas **sequencialmente**
(sem paralelismo), com intervalo de 0,5 segundo entre cada requisição,
e até 5 tentativas automáticas em caso de falha temporária.

---

## Fonte 4 — SIOPE (FNDE / Ministério da Educação)

### Sistema
**SIOPE** — Sistema de Informações sobre Orçamentos Públicos em Educação,
mantido pelo FNDE (Fundo Nacional de Desenvolvimento da Educação).

### Relatório consultado
**Receitas declaradas — base de cálculo para o gasto mínimo em educação**

Contém as receitas municipais (ISS e Cota-Parte do ICMS) que compõem a base de cálculo
dos percentuais mínimos de aplicação em educação exigidos pela Constituição Federal.

### Acesso
API OData pública do FNDE, com retorno em formato CSV:
```
GET https://www.fnde.gov.br/olinda-ide/servico/DADOS_ABERTOS_SIOPE/versao/v1/odata/
    Receita_Siope(Ano_Consulta=@Ano_Consulta,Num_Peri=@Num_Peri,Sig_UF=@Sig_UF)
```

### Parâmetros da consulta

| Parâmetro | Valor | Descrição |
|---|---|---|
| `@Ano_Consulta` | 2019 a 2025 | Exercício fiscal |
| `@Num_Peri` | `6` | 6.º bimestre (acumulado jan–dez) |
| `@Sig_UF` | sigla da UF (ex.: `PR`) | Unidade da Federação |

Diferentemente das demais fontes, o SIOPE é consultado por **UF × ano**, retornando
todos os municípios do estado de uma só vez.

### Campos selecionados na resposta

`TIPO, NUM_ANO, NUM_PERI, COD_UF, SIG_UF, COD_MUNI, NOM_MUNI,
COD_EXIB_FORMATADO, NOM_ITEM, IDN_CLAS, NOM_COLU, NUM_NIVE, NUM_ORDE, VAL_DECL`

Filtro aplicado no servidor: `IDN_CLAS eq 'RR'` (classificação "Receita Realizada").

### Códigos de conta consultados

O plano de contas do SIOPE passou por três gerações:

**2019–2020** — códigos com vírgulas (formato antigo); o ISS é composto por quatro
rubricas somadas por município:

| Código | Rubrica | Indicador |
|---|---|---|
| `4,11,13,05,00,00` | ISS principal | ISS |
| `4,19,11,40,00,00` | Multas e Juros de Mora sobre ISS | ISS |
| `4,19,13,13,00,00` | Multas e Juros de Mora da Dívida Ativa sobre ISS | ISS |
| `4,19,31,13,00,00` | Dívida Ativa de ISS | ISS |
| `4,17,22,01,01,00` | — | Cota-Parte ICMS |

Neste período, o filtro por código é feito localmente (os códigos com vírgulas
são rejeitados pelo servidor OData como separadores), e os quatro componentes
do ISS são somados por município antes de gravar.

**2021–2022**

| Código | Indicador |
|---|---|
| `11180230` | ISS |
| `17280110` | Cota-Parte ICMS |

**2023–2025**

| Código | Indicador |
|---|---|
| `11145110` | ISS |
| `17215000` | Cota-Parte ICMS |

### Código IBGE — diferença importante
O SIOPE retorna o código IBGE do município com **6 dígitos** (sem o dígito verificador).
As demais fontes (DCA, RREO, SIOPS) usam **7 dígitos**. Na geração do arquivo pivotado,
o sistema faz a correspondência pelos 6 primeiros dígitos, adotando o código de 7 dígitos
como chave final.

### Cobertura
Municípios apenas (o SIOPE não cobre estados).

### Tratamento especial — Distrito Federal
A API do FNDE não preenche o campo `COD_MUNI` para o Distrito Federal.
O sistema substitui por `530010` (código de Brasília sem o dígito verificador).

---

## Resumo comparativo das fontes

| Atributo | DCA | RREO | SIOPS | SIOPE |
|---|---|---|---|---|
| Órgão responsável | Tesouro Nacional | Tesouro Nacional | DATASUS/MS | FNDE/MEC |
| Tipo de acesso | API REST (JSON) | API REST (JSON) | Scraping HTML | API OData (CSV) |
| Periodicidade do relatório | Anual | Bimestral | Anual | Bimestral |
| Período consultado | Exercício completo | 6.º bimestre (jan–dez) | Consolidado anual | 6.º bimestre (jan–dez) |
| Cobertura — estados | Sim | Sim | Não | Não |
| Cobertura — municípios | Sim | Sim | Sim | Sim |
| Indicadores extraídos | ICMS, ISS, Cota-Parte ICMS | ICMS, ISS, Cota-Parte ICMS | ISS, Cota-Parte ICMS | ISS, Cota-Parte ICMS |
| Código IBGE do município | 7 dígitos | 7 dígitos | 7 dígitos (enviado 6) | 6 dígitos |
| Plano de contas muda por ano? | Sim (2022) | Não | Não | Sim (2021 e 2023) |
| Paralelismo na coleta | Sim (8 threads) | Sim (8 threads) | Não (sequencial) | Sim (4 threads) |

---

## Período de cobertura

Todos os módulos cobrem os exercícios de **2019 a 2025**, totalizando 7 anos.
