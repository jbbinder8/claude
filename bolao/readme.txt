================================================================================
BOLÃO DA COPA — Google Apps Script
================================================================================

## O QUE É

Web app hospedado no Google Apps Script, vinculado a uma planilha Google Sheets.
Permite que participantes façam palpites nos jogos da Copa do Mundo 2026.
Cada usuário se identifica pelo e-mail Google e os palpites ficam salvos na
planilha, aba "palpites".


## ARQUIVOS NESTA PASTA

  Code.js              — código do servidor (Google Apps Script / .gs)
  Index.html           — frontend (HTML + CSS + JS inline, servido pelo doGet)
  appsscript.json      — manifesto do projeto (scopes OAuth, timezone, webapp)
  tabela_jogos_v10.xlsx — download da planilha do Google Drive (referência)
                          NÃO é o arquivo canônico; a fonte verdadeira é o Drive.


## PLANILHA NO GOOGLE DRIVE

  - Compartilhamento: "Qualquer pessoa com o link" (somente leitura)
  - Aba "tabela" : lista de jogos (estrutura abaixo)
  - Aba "palpites": criada automaticamente pelo script na primeira execução


### Estrutura da aba "tabela" (colunas 1-based)

  Col A (1) — número do jogo
  Col D (4) — data (exibição BR, ex: "11/06/2026")
  Col E (5) — hora (exibição BR — NÃO usada para parse; ver nota abaixo)
  Col G (7) — seleção 1
  Col H (8) — seleção 2
  Col I (9) — considerar (1 = inclui no bolão, outro valor = ignora)
  Col J (10)— título completo, formato: "DD/MM HH:MM - fase - time1 x time2"
              *** FONTE CANÔNICA DO HORÁRIO — veja nota de timezone abaixo ***

  Nota timezone: células "só hora" no Sheets usam epoch 30/12/1899 com LMT local,
  gerando offsets fracionários ao converter fuso. Por isso o horário é lido da
  coluna J (texto puro), não da coluna E.

### Estrutura da aba "palpites"

  Col A — número do jogo
  Col B — e-mail do usuário (lowercase)
  Col C — timestamp do último save
  Col D — gols seleção 1
  Col E — gols seleção 2


## DEPLOY ATUAL

  Execute as : USER_ACCESSING (usuário que acessa o web app)
  Who has access : ANYONE (qualquer pessoa com Conta Google)

  Isso significa que cada usuário executa o script com suas próprias credenciais
  e precisa autorizar o app na primeira visita.


## BUG CORRIGIDO — e-mail retornando vazio

### Sintoma
  "Erro ao carregar: Error: Não foi possível identificar seu e-mail Google.
   Verifique se você está logado e se o app está configurado para
   'Executar como: usuário que acessa'."

### Causa
  Sem declarar explicitamente o scope "userinfo.email" no appsscript.json,
  o Apps Script não solicitava permissão de e-mail no flow OAuth. O token era
  gerado sem a claim de e-mail, fazendo Session.getEffectiveUser().getEmail()
  e Session.getActiveUser().getEmail() retornarem string vazia.

### Correção aplicada
  O arquivo appsscript.json desta pasta já contém o scope correto:

    "oauthScopes": [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/userinfo.email"
    ]

### O QUE AINDA PRECISA SER FEITO NO APPS SCRIPT EDITOR

  1. Abrir o projeto no editor: Extensions > Apps Script na planilha.
  2. Ir em Configurações do projeto (engrenagem) >
     marcar "Mostrar arquivo de manifesto appsscript.json no editor".
  3. Substituir o conteúdo do appsscript.json pelo arquivo desta pasta.
  4. Salvar.
  5. Implantar > Gerenciar implantações > criar NOVA versão
     (não editar a existente — mudança de scope exige novo token OAuth).
  6. Distribuir o novo URL para os participantes.
     Na primeira visita, cada um verá a tela de consentimento pedindo
     acesso ao e-mail — é esperado e correto.

  Quem já havia autorizado a versão anterior precisará re-autorizar
  (o novo URL de implantação dispara isso automaticamente).


## LÓGICA DE NEGÓCIO

  - Apenas jogos com coluna I = 1 aparecem no bolão.
  - Palpites ficam abertos até o horário de início do jogo (fuso America/Sao_Paulo).
  - A trava é feita tanto no frontend (campo disabled) quanto no servidor
    (salvarPalpite rejeita silenciosamente alterações de jogos já iniciados).
  - Upsert: se o usuário já tem palpite para o jogo, o save atualiza a linha;
    caso contrário, appendRow.
  - LockService.getDocumentLock() evita race condition em saves simultâneos.

  Pontuação (definida nas regras exibidas na tela, NÃO calculada pelo script):
    +1 resultado correto na fase de grupos / +2 nas demais fases
    +1 placar exato ou total de gols correto / +2 nas demais fases


## FUNÇÃO DE DIAGNÓSTICO

  No editor do Apps Script, selecione a função "diagnostico" e clique em Run.
  Ela loga no console:
    - Timezone da planilha e do script
    - Hora atual no fuso SP
    - As 5 primeiras linhas da aba tabela com os valores brutos e o horário
      extraído, para confirmar que o parse do título está correto.


## CONSTANTES IMPORTANTES (Code.js)

  GOLS_MIN = 0, GOLS_MAX = 20
  TZ = 'America/Sao_Paulo'
  SHEET_TABELA = 'tabela'
  SHEET_PALPITES = 'palpites'


## TECNOLOGIAS

  - Google Apps Script (runtime V8)
  - Google Sheets como banco de dados
  - HtmlService para servir o frontend
  - google.script.run para chamadas assíncronas frontend → servidor
  - Fontes: Archivo Black, IBM Plex Sans, IBM Plex Mono (Google Fonts)
================================================================================
