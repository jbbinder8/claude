/**
 * Bolão da Copa — Web App em Google Apps Script
 *
 * INSTALAÇÃO:
 *   1. Abra a planilha no Google Sheets.
 *   2. Menu Extensões > Apps Script.
 *   3. Cole este arquivo como Code.gs e o Index.html como arquivo HTML "Index".
 *   4. Em "Configurações do projeto" defina o fuso para "(GMT-03:00) São Paulo"
 *      (afeta Utilities.formatDate quando TZ_PADRAO === 'script').
 *   5. Implantar > Nova implantação > Aplicativo da Web.
 *        • Executar como: "Usuário que acessa o app" (assim Session.getActiveUser()
 *          devolve o email do logado).
 *        • Acesso: "Qualquer pessoa com Conta do Google" (ou restrito ao domínio).
 *      Cada usuário precisará ter pelo menos permissão de leitura na planilha,
 *      OU você pode mudar para "Executar como: eu" + compartilhar planilha
 *      apenas comigo — mas aí o email do usuário pode vir vazio fora do mesmo
 *      Workspace. Para um bolão fechado entre amigos, o ideal é deixar
 *      "Qualquer pessoa com Conta do Google" e compartilhar a planilha como
 *      somente-leitura com todos.
 */

const SHEET_TABELA      = 'tabela';
const SHEET_PALPITES    = 'palpites';
const TZ                = 'America/Sao_Paulo';
const GOLS_MIN          = 0;
const GOLS_MAX          = 20;

// Colunas da aba "tabela" (1-based)
const COL_JOGO          = 1;   // A
const COL_DATA_BR       = 4;   // D
const COL_HORA_BR       = 5;   // E
const COL_SELECAO1      = 7;   // G
const COL_SELECAO2      = 8;   // H
const COL_CONSIDERAR    = 9;   // I
const COL_TITULO        = 10;  // J
const COL_RESULTADO1    = 11;  // K — gols reais selecao1
const COL_RESULTADO2    = 12;  // L — gols reais selecao2
const COL_EDIT_RESULTADO = 13; // M — 1 = permite editar resultado após início
const COL_FIM           = 13;  // até onde lemos

// Colunas da aba "palpites"
const PCOL_JOGO         = 1;
const PCOL_USUARIO      = 2;
const PCOL_TIMESTAMP    = 3;
const PCOL_GOLS1        = 4;
const PCOL_GOLS2        = 5;


// =========================================================================
// Entrada do Web App
// =========================================================================
function doGet(e) {
  const page = (e && e.parameter && e.parameter.page === 'stats') ? 'Estatisticas' : 'Index';
  return HtmlService.createTemplateFromFile(page)
    .evaluate()
    .setTitle('Bolão da Copa')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}


// =========================================================================
// Helpers de tempo
// -------------------------------------------------------------------------
// Por que parseamos do TÍTULO (coluna J) e não direto da célula E?
//
// O Google Sheets armazena células "só hora" sobre a data de epoch dele,
// 30/12/1899. Naquela data, o fuso America/Sao_Paulo usava LMT-03:06:28
// (Local Mean Time, baseado na longitude). Outros fusos têm offsets LMT
// próprios igualmente fracionários. Se o timezone da SUA planilha não for
// América/São_Paulo, formatDate(célula_hora, 'America/Sao_Paulo', 'HH:mm')
// faz aritmética entre LMTs de 1899 e devolve um horário deslocado em
// minutos esquisitos. Como a coluna J tem "DD/MM HH:MM - ..." no início
// (texto puro, sem fuso), ela é a fonte canônica do horário do jogo.
// =========================================================================
function _agoraIso() {
  return Utilities.formatDate(new Date(), TZ, "yyyy-MM-dd'T'HH:mm:ss");
}

function _extrairInicioIso(tituloVal, dataDisplay) {
  const t = String(tituloVal || '');
  // Formato esperado: "DD/MM/YYYY HH:MM - ..." (ano opcional para retrocompatibilidade)
  const m = t.match(/^\s*(\d{1,2})\/(\d{1,2})(?:\/(\d{4}))?\s+(\d{1,2}):(\d{2})/);
  if (!m) return null;
  const dia  = parseInt(m[1], 10);
  const mes  = parseInt(m[2], 10);
  const hora = parseInt(m[4], 10);
  const min  = parseInt(m[5], 10);

  // Ano: da coluna J se presente; fallback coluna D; fallback 2026 (Copa).
  let ano;
  if (m[3]) {
    ano = parseInt(m[3], 10);
  } else {
    const y = String(dataDisplay || '').match(/(\d{4})/);
    ano = y ? parseInt(y[1], 10) : 2026;
  }

  const pad = n => (n < 10 ? '0' + n : '' + n);
  return ano + '-' + pad(mes) + '-' + pad(dia) + 'T' +
         pad(hora) + ':' + pad(min) + ':00';
}

function _jogoIniciado(tituloVal, dataDisplay) {
  const ini = _extrairInicioIso(tituloVal, dataDisplay);
  if (!ini) return true; // sem horário válido = trava por segurança
  return _agoraIso() >= ini;
}


// =========================================================================
// Identificação do usuário
// =========================================================================

// Cache da execução atual — cada request do web app é uma execução nova,
// então isso só evita chamar a API do Session várias vezes no mesmo request.
let _emailCache = null;

function _emailUsuario() {
  if (_emailCache) return _emailCache;

  const candidatos = [];
  // Effective primeiro: em "executar como usuário que acessa" é o mais
  // confiável. Active pode vir vazio para contas Gmail comuns.
  try { candidatos.push(Session.getEffectiveUser().getEmail()); } catch (e) {}
  try { candidatos.push(Session.getActiveUser().getEmail()); }    catch (e) {}

  for (const bruto of candidatos) {
    const email = _normalizaEmail(bruto);
    if (email) {
      _emailCache = email;
      return email;
    }
  }

  throw new Error('Não foi possível identificar seu e-mail Google. ' +
    'Verifique se você está logado e se o app está configurado para ' +
    '"Executar como: usuário que acessa".');
}

function _normalizaEmail(valor) {
  if (!valor || typeof valor !== 'string') return '';
  const email = valor.trim().toLowerCase();
  // Validação mínima: precisa ter @ com conteúdo dos dois lados e um ponto.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return '';
  return email;
}

// =========================================================================
// Aba de palpites — cria sob demanda
// =========================================================================
function _abaPalpites() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET_PALPITES);
  if (!sh) {
    sh = ss.insertSheet(SHEET_PALPITES);
    sh.getRange(1, 1, 1, 5).setValues([[
      'jogo', 'usuario', 'timestamp', 'gols_selecao1', 'gols_selecao2'
    ]]);
    sh.getRange(1, 1, 1, 5).setFontWeight('bold');
    sh.setFrozenRows(1);
    sh.setColumnWidth(1, 60);
    sh.setColumnWidth(2, 240);
    sh.setColumnWidth(3, 170);
    sh.setColumnWidth(4, 110);
    sh.setColumnWidth(5, 110);
  }
  return sh;
}


// =========================================================================
// API chamada pelo front-end ao carregar a página.
// Devolve: { email, jogos: [ { numero, titulo, selecao1, selecao2,
//                              inicio, iniciado, gols1, gols2 } ] }
// =========================================================================
function getJogosEPalpites() {
  const email = _emailUsuario();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const tabela = ss.getSheetByName(SHEET_TABELA);
  if (!tabela) throw new Error('Aba "tabela" não encontrada.');

  const lastRow = tabela.getLastRow();
  const jogos = [];
  if (lastRow >= 2) {
    const range = tabela.getRange(2, 1, lastRow - 1, COL_FIM);
    const values   = range.getValues();
    const displays = range.getDisplayValues();
    const agoraIso = _agoraIso();

    for (let i = 0; i < values.length; i++) {
      const row = values[i];
      const considerar = row[COL_CONSIDERAR - 1];
      if (considerar != 1) continue;

      const numero = row[COL_JOGO - 1];
      const sel1   = row[COL_SELECAO1 - 1];
      const sel2   = row[COL_SELECAO2 - 1];
      const titulo = row[COL_TITULO - 1];
      if (!numero || !titulo) continue;

      const inicioIso = _extrairInicioIso(titulo, displays[i][COL_DATA_BR - 1]);
      if (!inicioIso) continue;

      const r1 = row[COL_RESULTADO1 - 1];
      const r2 = row[COL_RESULTADO2 - 1];
      jogos.push({
        numero:          numero,
        titulo:          titulo || '',
        selecao1:        sel1 || '',
        selecao2:        sel2 || '',
        inicio:          inicioIso.replace('T', ' '),
        inicioIso:       inicioIso,
        iniciado:        agoraIso >= inicioIso,
        gols1:           null,
        gols2:           null,
        resultado1:      (r1 !== '' && r1 !== null && r1 !== undefined && !isNaN(Number(r1))) ? Number(r1) : null,
        resultado2:      (r2 !== '' && r2 !== null && r2 !== undefined && !isNaN(Number(r2))) ? Number(r2) : null,
        editarResultado: row[COL_EDIT_RESULTADO - 1] == 1,
        totalPalpites:   0,
      });
    }
  }

  // Carrega palpites do usuário
  const sp = _abaPalpites();
  const lastRowP = sp.getLastRow();
  if (lastRowP >= 2) {
    const pdata = sp.getRange(2, 1, lastRowP - 1, 5).getValues();
    const map = {}, countMap = {};
    pdata.forEach(function (r) {
      const u  = String(r[PCOL_USUARIO - 1] || '').toLowerCase();
      const g1 = r[PCOL_GOLS1 - 1];
      const g2 = r[PCOL_GOLS2 - 1];
      if (g1 !== '' && g1 !== null && g2 !== '' && g2 !== null) {
        const jid = String(r[PCOL_JOGO - 1]);
        countMap[jid] = (countMap[jid] || 0) + 1;
      }
      if (u === email) {
        map[String(r[PCOL_JOGO - 1])] = { gols1: g1, gols2: g2 };
      }
    });
    jogos.forEach(function (j) {
      const p = map[String(j.numero)];
      if (p) {
        j.gols1 = (p.gols1 === '' || p.gols1 === null) ? null : Number(p.gols1);
        j.gols2 = (p.gols2 === '' || p.gols2 === null) ? null : Number(p.gols2);
      }
      j.totalPalpites = countMap[String(j.numero)] || 0;
    });
  }

  return { email: email, jogos: jogos };
}


// =========================================================================
// API: salva (ou atualiza) o palpite. Revalida no servidor que o jogo ainda
// não começou. Se já começou, descarta silenciosamente e devolve o palpite
// original (se existir).
// =========================================================================
function salvarPalpite(jogoId, gols1, gols2) {
  const lock = LockService.getDocumentLock();
  lock.waitLock(15000);
  try {
    const email = _emailUsuario();

    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const tabela = ss.getSheetByName(SHEET_TABELA);
    const lastRow = tabela.getLastRow();
    if (lastRow < 2) return { ok: false, motivo: 'Tabela vazia.' };

    // Localiza o jogo pelo número na coluna A (com I=1)
    const range = tabela.getRange(2, 1, lastRow - 1, COL_FIM);
    const values   = range.getValues();
    const displays = range.getDisplayValues();
    let jogo = null;
    let dataDisplay = null;
    for (let i = 0; i < values.length; i++) {
      if (values[i][COL_JOGO - 1] == jogoId &&
          values[i][COL_CONSIDERAR - 1] == 1) {
        jogo = values[i];
        dataDisplay = displays[i][COL_DATA_BR - 1];
        break;
      }
    }
    if (!jogo) {
      return { ok: false, motivo: 'Jogo não encontrado ou indisponível.' };
    }

    // ============== TRAVA DE SERVIDOR =================
    // Mesmo que o usuário tente burlar o front (DevTools, requests manuais),
    // qualquer alteração em jogo já iniciado é silenciosamente descartada.
    if (_jogoIniciado(jogo[COL_TITULO - 1], dataDisplay)) {
      const atual = _palpiteAtual(jogoId, email);
      return {
        ok: false,
        iniciado: true,
        motivo: 'Jogo já iniciado. Palpite não foi alterado.',
        gols1: atual ? atual.gols1 : null,
        gols2: atual ? atual.gols2 : null
      };
    }

    // Validação dos números
    const g1 = _parseGols(gols1);
    const g2 = _parseGols(gols2);
    if (g1 === null || g2 === null) {
      return {
        ok: false,
        motivo: 'Informe inteiros entre ' + GOLS_MIN + ' e ' + GOLS_MAX + '.'
      };
    }

    // Upsert na aba palpites
    const sp = _abaPalpites();
    const lastRowP = sp.getLastRow();
    let rowIdx = -1;
    if (lastRowP >= 2) {
      const pdata = sp.getRange(2, 1, lastRowP - 1, 2).getValues();
      for (let i = 0; i < pdata.length; i++) {
        if (pdata[i][0] == jogoId &&
            String(pdata[i][1] || '').toLowerCase() === email) {
          rowIdx = i + 2;
          break;
        }
      }
    }

    const ts = new Date();
    if (rowIdx > 0) {
      sp.getRange(rowIdx, PCOL_TIMESTAMP, 1, 3).setValues([[ts, g1, g2]]);
    } else {
      sp.appendRow([jogoId, email, ts, g1, g2]);
    }

    return { ok: true, gols1: g1, gols2: g2 };

  } finally {
    lock.releaseLock();
  }
}


// =========================================================================
// Auxiliares
// =========================================================================
function _palpiteAtual(jogoId, email) {
  const sp = _abaPalpites();
  const lastRowP = sp.getLastRow();
  if (lastRowP < 2) return null;
  const pdata = sp.getRange(2, 1, lastRowP - 1, 5).getValues();
  for (let i = 0; i < pdata.length; i++) {
    if (pdata[i][0] == jogoId &&
        String(pdata[i][1] || '').toLowerCase() === email) {
      return {
        gols1: pdata[i][PCOL_GOLS1 - 1],
        gols2: pdata[i][PCOL_GOLS2 - 1]
      };
    }
  }
  return null;
}

function _parseGols(v) {
  if (v === '' || v === null || v === undefined) return null;
  const n = Number(v);
  if (!isFinite(n)) return null;
  if (Math.floor(n) !== n) return null;
  if (n < GOLS_MIN || n > GOLS_MAX) return null;
  return n;
}


// =========================================================================
// API: retorna palpites de TODOS para um jogo — só funciona após início.
// =========================================================================
function getPalpitesJogo(jogoId) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const tabela = ss.getSheetByName(SHEET_TABELA);
  if (!tabela) return { ok: false, motivo: 'Tabela não encontrada.' };

  const lastRow = tabela.getLastRow();
  if (lastRow < 2) return { ok: false, motivo: 'Tabela vazia.' };

  const range    = tabela.getRange(2, 1, lastRow - 1, COL_FIM);
  const values   = range.getValues();
  const displays = range.getDisplayValues();

  let jogoRow = null, dataDisplay = null;
  for (let i = 0; i < values.length; i++) {
    if (values[i][COL_JOGO - 1] == jogoId &&
        values[i][COL_CONSIDERAR - 1] == 1) {
      jogoRow     = values[i];
      dataDisplay = displays[i][COL_DATA_BR - 1];
      break;
    }
  }
  if (!jogoRow) return { ok: false, motivo: 'Jogo não encontrado.' };

  if (!_jogoIniciado(jogoRow[COL_TITULO - 1], dataDisplay)) {
    return { ok: false, motivo: 'Jogo ainda não iniciado.' };
  }

  const sp = _abaPalpites();
  const lastRowP = sp.getLastRow();
  if (lastRowP < 2) return { ok: true, palpites: [] };

  const pdata    = sp.getRange(2, 1, lastRowP - 1, 5).getValues();
  const palpites = [];
  pdata.forEach(function(r) {
    if (r[PCOL_JOGO - 1] != jogoId) return;
    const email = String(r[PCOL_USUARIO - 1] || '').toLowerCase();
    const g1    = r[PCOL_GOLS1 - 1];
    const g2    = r[PCOL_GOLS2 - 1];
    if (!email || g1 === '' || g1 === null || g2 === '' || g2 === null) return;
    palpites.push({ usuario: email, gols1: Number(g1), gols2: Number(g2) });
  });

  palpites.sort(function(a, b) {
    return a.usuario.localeCompare(b.usuario);
  });

  return { ok: true, palpites: palpites };
}


// =========================================================================
// API: retorna contagem de palpites por usuário + total de jogos ativos.
// =========================================================================
function getEstatisticas() {
  // Total de jogos ativos (considerar = 1)
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const tabela = ss.getSheetByName(SHEET_TABELA);
  let totalJogos = 0;
  if (tabela && tabela.getLastRow() >= 2) {
    const vals = tabela.getRange(2, 1, tabela.getLastRow() - 1, COL_CONSIDERAR).getValues();
    vals.forEach(function(r) { if (r[COL_CONSIDERAR - 1] == 1) totalJogos++; });
  }

  // Contagem de palpites por usuário
  const sp = _abaPalpites();
  const lastRow = sp.getLastRow();
  const contagem = {};
  if (lastRow >= 2) {
    const pdata = sp.getRange(2, 1, lastRow - 1, 5).getValues();
    pdata.forEach(function(r) {
      const email = String(r[PCOL_USUARIO - 1] || '').toLowerCase().trim();
      const g1 = r[PCOL_GOLS1 - 1];
      const g2 = r[PCOL_GOLS2 - 1];
      if (!email) return;
      if (g1 === '' || g1 === null || g2 === '' || g2 === null) return;
      contagem[email] = (contagem[email] || 0) + 1;
    });
  }

  const usuarios = Object.keys(contagem).map(function(email) {
    return { nome: email.split('@')[0], total: contagem[email] };
  });
  usuarios.sort(function(a, b) {
    return b.total - a.total || a.nome.localeCompare(b.nome);
  });

  return { usuarios: usuarios, totalJogos: totalJogos };
}


// =========================================================================
// API: salva o resultado oficial (colunas K e L da aba tabela).
// Exige que coluna M = 1 E que o jogo já tenha iniciado.
// =========================================================================
function salvarResultado(jogoId, gols1, gols2) {
  const lock = LockService.getDocumentLock();
  lock.waitLock(15000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const tabela = ss.getSheetByName(SHEET_TABELA);
    if (!tabela) return { ok: false, motivo: 'Aba tabela não encontrada.' };

    const lastRow = tabela.getLastRow();
    if (lastRow < 2) return { ok: false, motivo: 'Tabela vazia.' };

    const range   = tabela.getRange(2, 1, lastRow - 1, COL_FIM);
    const values  = range.getValues();
    const displays = range.getDisplayValues();

    let rowIdx = -1;
    for (let i = 0; i < values.length; i++) {
      if (values[i][COL_JOGO - 1] == jogoId &&
          values[i][COL_CONSIDERAR - 1] == 1) {
        if (values[i][COL_EDIT_RESULTADO - 1] != 1) {
          return { ok: false, motivo: 'Edição de resultado não liberada para este jogo.' };
        }
        if (!_jogoIniciado(values[i][COL_TITULO - 1], displays[i][COL_DATA_BR - 1])) {
          return { ok: false, motivo: 'Jogo ainda não iniciou.' };
        }
        rowIdx = i + 2; // linha real na planilha (header na linha 1)
        break;
      }
    }
    if (rowIdx < 0) return { ok: false, motivo: 'Jogo não encontrado ou indisponível.' };

    const g1 = _parseGols(gols1);
    const g2 = _parseGols(gols2);
    if (g1 === null || g2 === null) {
      return { ok: false, motivo: 'Informe inteiros entre ' + GOLS_MIN + ' e ' + GOLS_MAX + '.' };
    }

    tabela.getRange(rowIdx, COL_RESULTADO1, 1, 2).setValues([[g1, g2]]);
    return { ok: true, gols1: g1, gols2: g2 };

  } finally {
    lock.releaseLock();
  }
}


// =========================================================================
// Diagnóstico — rode manualmente no editor (selecione "diagnostico" no
// menu de funções e clique em Run). Mostra no Logger o que está sendo lido
// das primeiras linhas, útil pra confirmar que o horário do jogo está sendo
// extraído corretamente do título.
// =========================================================================
function diagnostico() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(SHEET_TABELA);
  const n  = Math.min(5, sh.getLastRow() - 1);
  if (n <= 0) { Logger.log('Tabela vazia.'); return; }

  Logger.log('Spreadsheet TZ : %s', ss.getSpreadsheetTimeZone());
  Logger.log('Script TZ      : %s', Session.getScriptTimeZone());
  Logger.log('Agora (SP ISO) : %s', _agoraIso());
  Logger.log('');

  const rng = sh.getRange(2, 1, n, COL_FIM);
  const vs = rng.getValues();
  const ds = rng.getDisplayValues();
  for (let i = 0; i < n; i++) {
    Logger.log('--- linha %s (jogo %s) ---', i + 2, vs[i][COL_JOGO - 1]);
    Logger.log('  D display: "%s"',   ds[i][COL_DATA_BR - 1]);
    Logger.log('  E display: "%s"',   ds[i][COL_HORA_BR - 1]);
    Logger.log('  J value  : "%s"',   vs[i][COL_TITULO - 1]);
    Logger.log('  Início   : %s',
               _extrairInicioIso(vs[i][COL_TITULO - 1], ds[i][COL_DATA_BR - 1]));
  }
}
