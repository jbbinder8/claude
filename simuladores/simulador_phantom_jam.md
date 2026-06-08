
# Documento de Especificação Técnica: Simulador de Tráfego Caótico (Phantom Jams)

## 0. Convenções Globais e Sistema de Unidades

* **Unidades físicas:** SI em toda a simulação (metros, segundos, m/s, m/s²). Velocidades exibidas ao usuário em km/h.
* **Escala visual:** $1 \text{ m} = 2 \text{ px}$ no canvas (constante `M_TO_PX = 2`), usada apenas para o **comprimento dos veículos** e para a **largura das faixas** (a curva da pista é definida em coordenadas de canvas — ver 2.3).
* **Dimensão dos veículos:** as dimensões físicas (em metros) são as usadas pelo IDM; a representação visual usa retângulos de tamanho fixo em pixels (independente da escala física da pista), conforme a tabela da Seção 3.
* **Idioma da UI:** Português (PT-BR).
* **Tudo num único arquivo HTML** (CSS + JS inline). Sem dependências externas.
* **Estado inicial:** pista vazia; nenhum veículo pré-populado.
* **Persistência:** sem persistência, a cada nova execução do html, considera-se os valores padrão.
* **Performance:** não há limite duro de $N_{max}$ veículos simultâneos.
* **Convenção de faixas (importante):**
   * **Faixa 0 = faixa da DIREITA** — faixa padrão / mais lenta.
   * **Faixa 1 = faixa da ESQUERDA** — faixa de ultrapassagem.
   * Toda a regra de troca de faixa (Seção 5) parte desta convenção: veículos lentos e pesados ocupam por padrão a Faixa 0; a Faixa 1 só é usada para ultrapassar veículos mais lentos à frente ou para desviar de obstáculos.

## 1. Arquitetura do Sistema (O Padrão Model-View)

O sistema é estritamente dividido em duas camadas, tudo implementado em um arquivo HTML:

* **Motor Físico (1D — Lógica):** Para a física, a via é uma **reta finita** com duas faixas. A única coordenada de posição de um veículo é $s$ (distância percorrida em metros), com $s \in [0, L_{track}]$. Não existem curvas na matemática. **A pista NÃO é um loop.**
* **Motor de Renderização (2D — Visual):** O HTML5 Canvas projeta a coordenada $s$ em um caminho visual sinuoso (serpentina horizontal) pré-calculado. As curvas são um artefato puramente estético.
* **Comprimento total** $L_{track} = 3000 \text{ m}$ (constante, ajustada para aproveitar o layout serpentina-horizontal da Seção 2). Veículos com $s > L_{track}$ são removidos (Seção 9).

## 2. A Geometria da Pista (Lookup Table)

### 2.1 Canvas e Layout de Tela

* **Aproveitamento total da largura da janela.** O simulador é projetado para ocupar toda a largura disponível (incluindo telas 1920 px).
* **Painel de UI (Seção 8):** faixa lateral fixa de **280 px** à direita.
* **Canvas:** largura = `window.innerWidth - 280 px`; altura = `window.innerHeight - 40 px` (sem teto rígido — usa toda a altura disponível).
* Em `window.resize`, o canvas é redimensionado e os waypoints são **regenerados** mantendo $L_{track}$ constante (a amplitude/altura da serpentina escala com a nova janela).

### 2.2 Gerador da Serpentina Horizontal

A pista é desenhada como uma **serpentina horizontal de múltiplas linhas** (boustrophedon), para maximizar o aproveitamento da largura da tela e tornar a pista muito mais comprida do que caberia em uma única reta:

* A pista é dividida em $n_{rows}$ linhas horizontais paralelas (típico: $n_{rows} = 4$, ajustável pela altura disponível).
* A **linha 0** (mais ao topo) percorre da **esquerda para a direita**.
* A **linha 1** percorre da **direita para a esquerda**.
* A **linha 2** percorre da **esquerda para a direita** novamente.
* … e assim sucessivamente (alternância).
* Entre uma linha e a seguinte há uma **curva em U** (meia-volta semicircular) na borda do canvas.
* Cada linha horizontal pode receber uma pequena modulação senoidal de baixa amplitude para preservar a estética de "serpente" do projeto original — opcional e puramente visual.

#### Parâmetros da serpentina horizontal

| Parâmetro | Valor / Regra |
|---|---|
| $n_{rows}$ | 4 linhas horizontais |
| Margem horizontal | 40 px nas duas bordas (para acomodar as curvas em U) |
| Altura útil por linha | $(H_{canvas} - 2 \cdot \text{margem}_y) / n_{rows}$ |
| Raio das curvas em U | $\approx$ altura útil de linha $/ 2$ |
| Amplitude da modulação senoidal (opcional) | $\le 15\%$ da altura útil de linha |

### 2.3 Procedimento de Pré-Cálculo dos Waypoints

1. Construir a curva total como concatenação de segmentos:
   * **Reta horizontal** (linha $k$, direção alternada).
   * **Semicírculo** (curva em U conectando linha $k$ → linha $k+1$).
2. Discretizar a curva total em amostras finas (densidade suficiente para precisão sub-pixel — ex.: passo paramétrico de $0{,}5$ px).
3. Acumular o comprimento de arco $s(u)$ por soma de segmentos euclidianos.
4. Reamostrar para gerar waypoints **espaçados uniformemente em $s$**, com $\Delta s = 2 \text{ m}$ entre cada waypoint consecutivo.
5. Resultado: array de $L_{track}/\Delta s + 1 = 1501$ waypoints `{ x, y, s }`, garantindo que `waypoints[i].s = i * 2`.
6. **Importante:** a curva paramétrica é em coordenadas de canvas — **ignora-se a escala m→px no eixo da pista**. A escala `M_TO_PX` é usada apenas para o **comprimento dos veículos** e para a **largura das faixas**. Isso permite que os 3000 m de pista caibam visualmente independente da resolução da tela.

### 2.4 Projeção 1D → 2D

Para desenhar um carro na posição $s$:

1. Encontrar índice $i = \lfloor s / \Delta s \rfloor$, e $\alpha = (s - i \cdot \Delta s) / \Delta s$.
2. **Lerp** entre `waypoints[i]` e `waypoints[i+1]` para obter $(x_c, y_c)$.
3. Calcular ângulo $\theta = \text{atan2}(y_{i+1} - y_i, x_{i+1} - x_i)$.
4. Aplicar **Deslocamento Normal (Lane Offset):**
   * Vetor normal unitário: $(\hat{n}_x, \hat{n}_y) = (-\sin\theta, \cos\theta)$.
   * Largura visual de faixa: $W_{lane} = 14 \text{ px}$ (constante).
   * **Faixa 0 (direita):** offset = $+0.5 \cdot W_{lane}$ na direção normal.
   * **Faixa 1 (esquerda):** offset = $-0.5 \cdot W_{lane}$ na direção normal.
   * Durante transição: `laneOffset` interpolado linearmente entre os dois valores.

## 3. Entidades e Perfil dos Veículos

### 3.1 Tabela de Veículos

| Veículo | Dim. Visual (L x C) | Comprimento Físico | $a_{max}$ (default) | $b$ | $v_0$ base (default) | Cor base |
| --- | --- | --- | --- | --- | --- | --- |
| **Carro** | 8 x 16 px | 4 m | 1.5 m/s² (slider) | 2.0 m/s² | 33 m/s (≈120 km/h, slider) | — |
| **Caminhão** | 10 x 40 px | 12 m | 0.7 m/s² (slider) | 1.8 m/s² | 22 m/s (≈80 km/h, slider) | — |

* A **cor base** não é fixa: cada veículo é colorido a cada frame pelo Mapa de Calor (Seção 7).
* O formato (carro vs. caminhão) é distinguível pelo **comprimento visual**.
* Os valores de $a_{max}$ e $v_0$ base são **configuráveis em tempo real via sliders** (Seção 8). Veículos já existentes adotam o novo valor a partir do frame seguinte.

### 3.2 Fator de Personalidade (ruído por-instância, configurável)

Ao ser instanciado, cada veículo recebe um multiplicador $\mu$ aplicado **uma única vez** à velocidade-alvo:

$$v_{0,inst} = \mu \cdot v_{0,base}$$

O multiplicador $\mu$ é sorteado de uma distribuição **uniforme centrada em 1.0** cuja **semi-amplitude $\sigma$ é configurável pelo usuário**, com sliders independentes para carros e caminhões (Seção 8):

$$\mu \sim \mathcal{U}(1 - \sigma, \; 1 + \sigma)$$

Defaults:
* $\sigma_{carro} = 0{,}10$ (recupera o comportamento original $\mu \in [0{,}9; 1{,}1]$).
* $\sigma_{caminhao} = 0{,}10$.
* Faixa do slider: $\sigma \in [0; 0{,}30]$.

Esse valor de $\mu$ é fixo durante toda a vida do veículo. **Não confundir** com o ruído por-frame (Seção 8.2.1).

## 4. O Modelo Físico Principal: IDM (Intelligent Driver Model)

### 4.1 Distância Real

$$s_{real} = S_{lider} - S_{seguidor} - C_{lider}$$

onde $C_{lider}$ é o **comprimento físico** do líder (em metros, da tabela 3.1; veículos fantasmas têm $C=0$).

### 4.2 Equação de Aceleração

$$a = a_{max} \left[ 1 - \left(\frac{v}{v_0}\right)^4 - \left(\frac{s^*}{s_{real}}\right)^2 \right]$$

$$s^* = s_0 + v T + \frac{v \Delta v}{2 \sqrt{a_{max} b}}$$

* $s_0 = 2 \text{ m}$ (constante global).
* $T$: tempo de reação (slider da Seção 8).
* $\Delta v = v_{seguidor} - v_{lider}$.
* $v_0$: velocidade desejada do veículo (instância) **modulada** pelo ruído por-frame (Seção 8.2.1).

### 4.3 Caso "Sem Líder à Frente"

Quando não há líder real, semáforo nem obra à frente na faixa do veículo:

* $s_{real} = +\infty$ (na prática: número grande, ex: `1e9`).
* $\Delta v = 0$.
* O termo de interação $(s^* / s_{real})^2 \approx 0$, restando apenas a aceleração livre.

### 4.4 Proteções Numéricas e Anti-Colisão de Emergência

* Se $s_{real} \le 0.1 \text{ m}$ (colisão lógica), forçar $s_{real} = 0.1$ para evitar singularidade.
* Saturar a aceleração final: $a \in [-b_{max}, a_{max}]$, com $b_{max} = 9.0 \text{ m/s²}$ (frenagem normal saturada).
* Garantir $v \ge 0$ após integração (Seção 9.4).

#### 4.4.1 Freada de Emergência Anti-Penetração (regra obrigatória)

**Regra absoluta:** veículos não podem se sobrepor / "entrar dentro" do veículo da frente. A frenagem normal do IDM saturada em $b_{max}$ pode, em casos extremos (alto $\Delta v$, gap inicial muito pequeno após troca de faixa, etc.), não ser suficiente para evitar colisão. Para garantir invariância de não-colisão:

1. Após calcular $a$ pelo IDM, computar a **distância mínima de parada** necessária dado $v$ atual e a desaceleração disponível:
   $$d_{min} = \frac{v^2}{2 \cdot b_{max}}$$
2. Se houver líder e $s_{real} - d_{min} < s_0$ (não há margem de segurança $s_0$ após parar com $b_{max}$ pleno), **sobrescrever** a aceleração calculada por **freada total**:
   $$a = -\frac{v^2}{2 \cdot \max(s_{real} - s_0, \; 0{,}1)}$$
   limitada inferiormente por um "freio físico absoluto" $b_{emerg} = 20{,}0 \text{ m/s²}$ (desaceleração de emergência irrealista, mas garante anti-colisão).
3. Como salvaguarda final na integração (Seção 9.4), após atualizar $v$ e $s$, **clamp** da posição: se $s_{novo} + C_{seguidor}/2 \ge S_{lider} - C_{lider}/2 - s_0$, posicionar o seguidor exatamente em $S_{lider} - C_{lider} - s_0$ e **zerar** sua velocidade.

Esta cadeia (predição → freada de emergência → clamp posicional) é mandatória e tem precedência sobre qualquer outra regra dinâmica.

## 5. Lógica de Troca de Faixa: MOBIL Assimétrico Estendido

### 5.1 Constantes

| Símbolo | Valor | Significado |
| --- | --- | --- |
| $p$ | 0.2 | Fator de cortesia (peso do impacto sobre o veículo de trás na nova faixa). |
| $\Delta a_{th}$ | 0.2 m/s² | Threshold de incentivo: trocar só se ganho superar isso. |
| $\Delta a_{bias,dir}$ | 0.3 m/s² | Bônus assimétrico para **voltar à direita** (Faixa 0). |
| $b_{seguro}$ | 4.0 m/s² | Limite de frenagem aceitável para o novo seguidor. |
| $D_{livre}$ | 150 m | Distância de "direita livre à frente" para forçar retorno à direita (5.6). |
| $D_{congest}$ | 100 m | Distância para detectar congestionamento na esquerda (5.7). |
| $v_{congest}$ | 5 m/s (≈18 km/h) | Velocidade abaixo da qual o líder à frente é considerado "congestionado". |
| $D_{obra,prox}$ | 200 m | Distância à obra que suprime bônus de retorno à direita (5.5/5.8). |

### 5.2 Critério de Segurança

Calcular a aceleração IDM hipotética do **novo seguidor** na faixa de destino, considerando que o veículo-alvo passa a estar à sua frente (com o comprimento do veículo-alvo incluído em $s_{real}$). Se $a'_{novo\_seguidor} < -b_{seguro}$, **proibir** a troca.

### 5.3 Critério de Incentivo (MOBIL Completo)

Definir:
* $a_c$, $a'_c$: aceleração atual e hipotética do veículo que pondera trocar.
* $a_n$, $a'_n$: aceleração atual e hipotética do **novo seguidor** na faixa de destino.
* $a_o$, $a'_o$: aceleração atual e hipotética do **antigo seguidor** que fica para trás.
* $\Delta a_{bias}$: $+\Delta a_{bias,dir}$ se a troca for **para a direita** (Faixa 1 → Faixa 0); $-\Delta a_{bias,dir}$ se for **para a esquerda** (Faixa 0 → Faixa 1). Ou seja, voltar à direita ganha bônus, ir à esquerda paga pedágio. Isso codifica a regra "ultrapassagem é sempre pela esquerda" e "direita é faixa padrão".

A troca acontece se, e somente se:

$$(a'_c - a_c) + p \cdot \left[ (a'_n - a_n) + (a'_o - a_o) \right] + \Delta a_{bias} > \Delta a_{th}$$

### 5.4 Estado `TROCANDO_FAIXA`

* Iniciada uma troca, o veículo entra em status `TROCANDO_FAIXA` por **1.0 s**, durante o qual o `laneOffset` visual faz Lerp suave (linear) entre faixas.
* Durante a transição, o veículo é considerado **pertencente já à faixa de destino** para fins de busca de líder/seguidor (atualização imediata da topologia lógica). Isso evita duplicação de presença em ambas as faixas.
* **Nenhuma nova decisão MOBIL** é avaliada enquanto $estado = $ `TROCANDO_FAIXA`.

### 5.5 Supressão do Bônus na Zona de Obras

Se a obra está ativa e o veículo está na Faixa 0 a menos de $D_{obra,prox} = 200 \text{ m}$ de $S_{cone,início}$, **suprimir** $\Delta a_{bias,dir}$ ao avaliar volta à direita. Equivalente: $\Delta a_{bias} = 0$ na decisão de retorno enquanto a obra estiver à frente próxima.

### 5.6 Regra "Retornar à Direita Quando Livre"

Se um veículo está na Faixa 1 (esquerda) e a Faixa 0 (direita) está **livre nos próximos $D_{livre} = 150 \text{ m}$** (sem líder, ou líder com $v \ge v$ do próprio veículo), o veículo deve **tentar retornar à Faixa 0**:

* A decisão MOBIL para a direita é avaliada normalmente.
* O bônus $\Delta a_{bias,dir}$ atua naturalmente a favor.
* Se segurança for satisfeita, a troca ocorre mesmo que o ganho de aceleração seja marginal.

**Exceção:** a regra é desativada quando há obra à frente próxima na Faixa 0 (subseção 5.5/5.8 prevalece).

### 5.7 Regra "Esquerda Congestionada e Direita Livre"

Se o veículo está na Faixa 1 (esquerda) e:
* Existe líder na Faixa 1 com $v_{lider} < v_{congest}$ a menos de $D_{congest}$ à frente, **e**
* A Faixa 0 (direita) está livre nos próximos $D_{livre}$ metros,

então o veículo é fortemente incentivado a mudar para a direita. Implementação: ao detectar essa condição, somar um bônus adicional $+0{,}5 \text{ m/s²}$ ao termo de incentivo MOBIL (em adição ao $\Delta a_{bias,dir}$). Continua sujeito ao critério de segurança (5.2).

### 5.8 Regra "Não Voltar à Direita Antes de Obra"

Quando há obra ativa à frente do veículo (na faixa de destino que seria a Faixa 0), proibir a mudança Faixa 1 → Faixa 0 enquanto o veículo estiver dentro de $D_{obra,prox} = 200 \text{ m}$ de $S_{cone,início}$. Isso evita oscilações e movimentos contraproducentes às vésperas da zona bloqueada.

### 5.9 Regra "Caminhões Preferem a Direita"

Veículos do tipo **Caminhão** têm comportamento mais conservador quanto à Faixa 1:

* Só consideram trocar para a Faixa 1 (esquerda) em dois casos:
   1. Para **ultrapassar** um líder real na Faixa 0 cuja velocidade seja claramente inferior à do caminhão (diferença $> 5 \text{ km/h}$ sustentada).
   2. Para **desviar de obstáculo** na Faixa 0 (cone/obra ou fantasma).
* Em qualquer outro cenário, a decisão MOBIL para a esquerda é **bloqueada** para caminhões.
* O bônus de retorno à direita (5.6) atua normalmente: caminhão que tenha ido à esquerda volta para a direita assim que possível.

### 5.10 Zona de Obras — Zipper Merge (Comboio Alternado)

Veículos na Faixa 0 com a obra ativa à frente entram em **Modo de Fuga da Obra** (já descrito em 6.4). Adicionalmente, para garantir convergência fluida e justa quando há fila:

* **Cortesia obrigatória do veículo de trás na esquerda:** veículo da Faixa 0 que precisa migrar para a Faixa 1 por causa da obra é tratado como **prioritário** pelo MOBIL do veículo que vem atrás na Faixa 1. Implementação: o critério de segurança (5.2) usa um $b_{seguro,zipper} = 6{,}0 \text{ m/s²}$ mais permissivo, e o novo seguidor na Faixa 1 deve **antecipadamente reduzir velocidade** (aplicar desaceleração extra de até $-2{,}0 \text{ m/s²}$) para criar o gap necessário, quando detecta um veículo da direita em modo de fuga aproximando-se lateralmente em $s$ semelhante (janela $\pm 20 \text{ m}$).
* **Padrão zipper (1-para-1):** dentro da zona de aproximação da obra ($S_{cone,início} - 200 \text{ m} \le s \le S_{cone,início}$), quando ambas as faixas estão congestionadas (líderes com $v < v_{congest}$), o avanço deve ser alternado:
   * Manter um contador discreto `last_advanced ∈ {direita, esquerda}` por zona.
   * Quando a frente da fila avança, alternar a permissão: o próximo a entrar no "ponto de fusão" (último waypoint da Faixa 0 antes da obra) é o veículo da faixa **oposta** ao último que avançou.
   * Operacionalmente: o líder da Faixa 1 imediatamente após o ponto de merge "segura" $\approx 0{,}5 \text{ s}$ adicional após sua passagem para que o líder da Faixa 0 (em modo de fuga) consiga entrar à frente, alternadamente.
* A regra **só se aplica em regime congestionado**; em regime livre, prevalece o MOBIL padrão.

## 6. Obstáculos Dinâmicos (Semáforo e Obras)

### 6.1 Modelo de Veículos Fantasmas

Obstáculos são representados como objetos injetados no array de busca de líderes, com $v = 0$ e $C_{lider} = 0$.

### 6.2 Semáforo

* **Posição fixa: $S_{semaforo} = L_{track} / 2$** (meio da pista — para $L_{track} = 3000 \text{ m}$, fica em $1500 \text{ m}$).
* Estados: **VERDE** (sem fantasma) e **VERMELHO** (fantasma em ambas as faixas).
* **Sem ciclo automático**: o toggle da UI alterna manualmente entre verde e vermelho.
* Transição VERMELHO → VERDE: remoção imediata do fantasma; sem fase amarela.

### 6.3 Obras (Lane Drop)

* **Posição inicial:** $S_{cone,início} = (23/33) \cdot L_{track}$ na **Faixa 0**. Para $L_{track} = 3000 \text{ m}$, fica em $\approx 2090{,}9 \text{ m}$.
* Comprimento da zona bloqueada: $L_{obra} = 30 \text{ m}$.
* O fantasma da obra é injetado em $S_{cone,início}$ na Faixa 0 enquanto o toggle estiver ativo.
* Visualmente, renderizar cones laranja entre $S_{cone,início}$ e $S_{cone,início} + L_{obra}$ na Faixa 0.

### 6.4 Modo de Emergência (Fuga da Obra)

* **Gatilho:** veículo na Faixa 0, obra ativa, e distância até $S_{cone,início}$ menor que **150 m**.
* **Comportamento:**
   * Suprime $\Delta a_{bias,dir}$ (já coberto em 5.5).
   * Força avaliação MOBIL para a esquerda **apenas com critério de segurança** (ignora incentivo de aceleração) e usa $b_{seguro,zipper}$ (5.10).
   * Sinaliza-se como "veículo em fuga" para que o veículo de trás na Faixa 1 aplique a cortesia obrigatória (5.10).
   * Se a troca for segura, executa; senão, segue freando contra o fantasma na Faixa 0 (pode parar em zero) e aguarda nova janela.
* O modo se mantém até o veículo trocar para Faixa 1 ou ultrapassar $S_{cone,início}$.

## 7. Pipeline de Renderização

A função `draw()` executada no `requestAnimationFrame`:

1. **Limpar Canvas** com cor de fundo `#1a1a1a`.
2. **Desenhar Asfalto:**
   * Polilinha grossa (largura $2 \cdot W_{lane} = 28 \text{ px}$) ao longo dos waypoints, cor `#333`.
   * Linha tracejada central separando as duas faixas, cor `#888`, dash `[10, 10]`.
3. **Desenhar Obstáculos** (se ativos):
   * Semáforo vermelho: círculo `#ff3333` raio 8 px na posição $S_{semaforo}$ projetada, centralizado entre as faixas.
   * Cones: triângulos `#ff8c00` distribuídos a cada 5 m de $S_{cone,início}$ a $S_{cone,início} + L_{obra}$ na Faixa 0.
4. **Iterar sobre veículos** (ordem: $s$ crescente, para que veículos à frente fiquem por cima):
   * Calcular $(x, y, \theta)$ via Seção 2.4.
   * Determinar cor pelo Mapa de Calor (7.1).
   * `ctx.save(); ctx.translate(x, y); ctx.rotate(θ); ctx.fillRect(-L/2, -W/2, L, W); ctx.restore();`
   * onde $L, W$ são as dimensões visuais em px da tabela 3.1.

### 7.1 Mapa de Calor

Razão $r = v / v_{0,inst}$ (sem aplicar ruído por-frame na referência). Cor por interpolação contínua HSL:

* $r \le 0.1$ → vermelho puro `hsl(0, 90%, 50%)`.
* $0.1 < r \le 0.5$ → interpolar de vermelho (hue 0) para amarelo (hue 60).
* $0.5 < r \le 0.8$ → interpolar de amarelo (hue 60) para verde-claro (hue 100).
* $r > 0.8$ → verde puro `hsl(120, 80%, 45%)`.

## 8. Entradas do Usuário (Painel de UI)

### 8.1 Layout

Painel lateral fixo à direita, 280 px de largura, fundo `#222`, texto `#eee`, sliders nativos do HTML estilizados.

Contém também:
* **Botão Reset:** remove todos os veículos e zera o spawner.
* **Botão Pausar/Continuar:** congela o `update()` mantendo `draw()`.
* **Botão Restaurar Defaults:** restaura todos os sliders aos valores default e limpa `localStorage`.
* **Painel de Métricas (somente leitura):**
   * Veículos ativos.
   * Vazão (veículos despawned nos últimos 30 s, extrapolado para por minuto).
   * Velocidade média (m/s e km/h).

### 8.2 Tabela de Controles

| Controle | Min | Max | Step | Default | Variável |
| --- | --- | --- | --- | --- | --- |
| **Taxa de Entrada** | 0.1 | **20.0** | 0.1 | 1.0 carros/s | Spawn rate em $s=0$. |
| **% de Caminhões** | 0 | 100 | 1 | 15 % | Probabilidade do spawner gerar caminhão. |
| **Tempo de Reação ($T$)** | 0.5 | 3.0 | 0.1 | 1.5 s | IDM de todos os veículos. |
| **Nível de Ruído (por-frame)** | 0.0 | 0.5 | 0.01 | 0.05 | Veja 8.2.1. |
| **VMax Carros** | 60 | 160 | 5 | 120 km/h | Limite $v_{0,base}$ para carros. |
| **VMax Caminhões** | 40 | 110 | 5 | 80 km/h | Limite $v_{0,base}$ para caminhões. |
| **Desvio VMax Carros ($\sigma_{carro}$)** | 0.00 | 0.30 | 0.01 | 0.10 | Semi-amplitude do $\mu$ uniforme para carros (3.2). |
| **Desvio VMax Caminhões ($\sigma_{caminhao}$)** | 0.00 | 0.30 | 0.01 | 0.10 | Idem para caminhões (3.2). |
| **Aceleração Carros ($a_{max,carro}$)** | 0.3 | 4.0 | 0.1 | 1.5 m/s² | Override do $a_{max}$ da tabela 3.1 para carros. |
| **Aceleração Caminhões ($a_{max,cam}$)** | 0.2 | 2.5 | 0.1 | 0.7 m/s² | Override do $a_{max}$ da tabela 3.1 para caminhões. |
| **Multiplicador de Tempo ($k_t$)** | 1 | 10 | 1 | 1 | Acelera toda a simulação (Seção 9.1). |
| **Semáforo** | — | — | — | Verde | Toggle. |
| **Obras na Direita** | — | — | — | Off | Toggle. |

#### 8.2.1 Ruído por-frame (distinto do fator de personalidade)

A cada frame, **antes** de aplicar o IDM, o $v_0$ efetivo de cada veículo é:

$$v_{0,eff}(t) = v_{0,inst} \cdot (1 + \eta \cdot \xi_t), \quad \xi_t \sim \mathcal{U}(-1, +1)$$

onde $\eta$ é o "Nível de Ruído" do slider. Em $\eta = 0$, recupera-se exatamente $v_{0,inst}$ (apenas a personalidade fixa atua).

**Resumo:**
* **Personalidade ($\mu$):** sorteada **uma vez** ao spawn, distribuição $\mathcal{U}(1-\sigma, 1+\sigma)$ com $\sigma$ configurável por classe (carro/caminhão). Constante para sempre.
* **Ruído por-frame ($\eta \xi_t$):** sorteado **a cada frame**, simula jitter térmico do motorista.

#### 8.2.2 Multiplicador de Tempo $k_t$

O slider $k_t \in \{1, 2, \ldots, 10\}$ acelera a passagem do tempo da simulação **sem alterar o passo de integração**. Implementação: para cada frame, o número de chamadas a `update(dt)` no acumulador é **multiplicado por $k_t$**. Assim, $k_t = 10$ avança 10 passos físicos por frame visual (simulação 10× mais rápida em tempo real). $k_t = 1$ é o comportamento default. Não afeta o spawn por frame (a taxa em carros/s permanece equivalente em tempo de simulação, então mais carros spawnam por segundo de tempo real).

## 9. Ciclo de Vida (Game Loop)

### 9.1 Passo de Tempo

* Integração com **passo fixo** $dt = 1/60 \text{ s}$, dirigida por acumulador.
* `requestAnimationFrame` mede $\Delta t_{frame}$ real; acumulador soma e dispara `update(dt)` repetidamente enquanto $\ge dt$.
* **Multiplicador de tempo $k_t$:** a cada frame, a quantidade de passos `update(dt)` executados é **multiplicada por $k_t$** (Seção 8.2.2).
* **Clamp de segurança:** se $\Delta t_{frame} > 0.25 \text{ s}$ (aba inativa), descartar o excedente (não tentar recuperar).

### 9.2 Ordem dentro de `update(dt)`

1. **Spawner:** tenta gerar novos veículos em $s = 0$.
   * Probabilidade por chamada: $taxa \cdot dt$.
   * Classe sorteada conforme % de caminhões.
   * **Atribuição de faixa no spawn:**
      * **Caminhões: sempre na Faixa 0 (direita).**
      * **Carros: na faixa que estiver mais livre.** Comparar a distância até o líder em cada faixa numa janela inicial de $d_{check} = 50 \text{ m}$; escolher a faixa cujo líder esteja mais distante (empate → Faixa 0). Se ambas livres, sortear uniformemente.
   * **Distância segura:** spawn é cancelado se existir veículo na faixa escolhida com $s < d_{safe}$, onde $d_{safe} = s_0 + L_{máx} = 2 + 12 = 14 \text{ m}$. (Para carros, se a faixa preferida estiver bloqueada mas a outra estiver livre, tentar a outra; se ambas bloqueadas, descartar conforme Seção 10.)
   * **Velocidade inicial:** $v_{spawn} = 0.8 \cdot v_{0,inst}$ (entrada na pista já em movimento).
2. **Aplicação do Ruído por-frame:** atualizar $v_{0,eff}$ de cada veículo.
3. **Varredura MOBIL:** veículos no estado `NORMAL` decidem trocas conforme regras 5.3, 5.6, 5.7, 5.8, 5.9, 5.10. Veículos em `TROCANDO_FAIXA` apenas avançam o cronômetro de transição.
4. **Varredura IDM:** cada veículo calcula $a$ usando o líder na faixa atual (incluindo fantasmas), aplica regra anti-colisão de emergência (Seção 4.4.1).
5. **Integração Euler:**
   * $v_{t+dt} = \max(0, v_t + a \cdot dt)$.
   * $s_{t+dt} = s_t + v_{t+dt} \cdot dt$.
   * Aplicar **clamp posicional anti-penetração** (4.4.1 passo 3): se a nova posição invadiria o veículo da frente, colar atrás dele a $s_0$ de distância e zerar $v$.
6. **Atualização da transição visual:** veículos em `TROCANDO_FAIXA` avançam $laneProgress$; se $\ge 1.0$, finalizam e voltam a `NORMAL`.
7. **Despawn:** remover veículos com $s > L_{track}$ (incrementar contador de vazão).

### 9.3 Estrutura de Decisão (Topologia Lógica)

Para evitar dependências circulares dentro do mesmo frame:

* Decisões MOBIL (passo 3) **usam as acelerações IDM do frame anterior** como base para $a_c, a_n, a_o$, e calculam $a'_c, a'_n, a'_o$ hipotéticas a partir do estado atual de posição/velocidade.
* O IDM real (passo 4) usa o **estado de faixa já atualizado** pelas decisões MOBIL deste mesmo frame.

### 9.4 Garantia de Não-Colisão (resumo operacional)

Em todo passo de integração, a cadeia anti-colisão da Seção 4.4.1 é aplicada:
1. IDM produz $a$ no intervalo $[-b_{max}, a_{max}]$.
2. Verificação de distância de parada; se insuficiente, sobrescrita por freada emergencial (até $-b_{emerg}$).
3. Integração de $v$ e $s$.
4. Clamp posicional final: nenhum veículo termina o passo invadindo o anterior.

## 10. Casos Extremos e Decisões de Borda

| Cenário | Comportamento esperado |
| --- | --- |
| Spawn bloqueado em ambas as faixas | Veículos não-spawned são **descartados** (não enfileiram). |
| $s_{real}$ tendendo a zero (colisão lógica) | Clamp em 0.1 m (Seção 4.4); IDM aplica frenagem máxima; cadeia anti-colisão da 4.4.1 garante não-penetração. |
| Veículo termina transição de faixa e descobre líder muito próximo | A regra anti-colisão de emergência (4.4.1) garante parada total antes de penetrar. |
| Semáforo abre (vermelho → verde) com fila parada atrás | Fantasma some; veículos retomam IDM com líder real (próximo veículo parado) e arrancam naturalmente. |
| Veículo atinge $s = L_{track}$ exatamente no spawn | Não pode ocorrer (spawn é em $s = 0$); despawn ocorre no passo 7. |
| Janela redimensionada durante simulação | Canvas e waypoints regenerados; $s$ de cada veículo preservado, posição visual recalculada. |
| Aba inativa por longo período | Acumulador descartado (clamp 0.25 s); simulação continua do estado congelado. |
| Veículo solitário no início (sem líder) | Caso "Sem Líder" da Seção 4.3: acelera até $v_{0,eff}$. |
| $\eta = 0$, $\sigma_{carro} = \sigma_{caminhao} = 0$ em todos os veículos | Phantom jams ainda podem emergir por instabilidade do IDM puro (validação do modelo). |
| $k_t = 10$ com taxa de entrada alta | Simulação avança 10× mais rápido; spawn por segundo de tempo real aumenta proporcionalmente. Performance pode degradar; sem tratamento especial. |
| Caminhão preso na Faixa 0 atrás de outro caminhão lento | Avalia MOBIL para esquerda (caso 5.9.1); se seguro e ganho > threshold, ultrapassa. Volta à direita por 5.6 assim que possível. |
| Veículo em fuga da obra sem espaço imediato na esquerda | Cortesia do seguidor na esquerda (5.10) cria gap; se ainda insuficiente, veículo para na Faixa 0 e tenta de novo no próximo frame. |

## 11. Resumo de Constantes (Tabela Única)

### 11.1 Físicas

| Constante | Valor |
| --- | --- |
| $L_{track}$ | 3000 m |
| $\Delta s$ (waypoints) | 2 m |
| $s_0$ | 2 m |
| $b_{max}$ (saturação IDM) | 9.0 m/s² |
| $b_{emerg}$ (freada absoluta anti-colisão) | 20.0 m/s² |
| $b_{seguro}$ | 4.0 m/s² |
| $b_{seguro,zipper}$ | 6.0 m/s² |
| $p$ (cortesia MOBIL) | 0.2 |
| $\Delta a_{th}$ | 0.2 m/s² |
| $\Delta a_{bias,dir}$ | 0.3 m/s² |
| $D_{livre}$ | 150 m |
| $D_{congest}$ | 100 m |
| $v_{congest}$ | 5 m/s |
| $D_{obra,prox}$ | 200 m |
| $dt$ (passo fixo) | 1/60 s |
| Carro: $L_{fis}, a_{max}\;\text{default}, b, v_{0,base}\;\text{default}$ | 4 m, 1.5, 2.0, 33 m/s |
| Caminhão: $L_{fis}, a_{max}\;\text{default}, b, v_{0,base}\;\text{default}$ | 12 m, 0.7, 1.8, 22 m/s |
| $\sigma$ default (carro e caminhão) | 0.10 |
| $S_{semaforo}$ | $L_{track}/2$ (= 1500 m) |
| $S_{cone,início}$ | $(23/33) \cdot L_{track}$ (≈ 2090.9 m) |
| $L_{obra}$ | 30 m |
| Gatilho Modo Emergência | 150 m |
| Duração `TROCANDO_FAIXA` | 1.0 s |
| $d_{safe}$ (spawn) | 14 m |
| $d_{check}$ (janela de escolha de faixa no spawn de carros) | 50 m |
| $v_{spawn}$ | $0.8 \cdot v_{0,inst}$ |
| Taxa máxima de spawn | 20 carros/s |
| $k_t$ (multiplicador de tempo) | 1..10 (default 1) |

### 11.2 Visuais

| Constante | Valor |
| --- | --- |
| `M_TO_PX` | 2 px/m (escala dos veículos e da largura de faixa) |
| $W_{lane}$ | 14 px |
| Carro visual | 8 × 16 px |
| Caminhão visual | 10 × 40 px |
| Serpentina horizontal — $n_{rows}$ | 4 linhas |
| Margem horizontal do canvas | 40 px |
| Amplitude da modulação senoidal opcional por linha | ≤ 15 % da altura útil de linha |
| Cor fundo | `#1a1a1a` |
| Cor asfalto | `#333` |
| Cor linha central | `#888` (dash 10/10) |
| Cor semáforo vermelho | `#ff3333` |
| Cor cones | `#ff8c00` |
| Painel UI: largura, bg, fg | 280 px, `#222`, `#eee` |
