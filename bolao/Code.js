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

const SHEET_TABELA        = 'tabela';
const SHEET_PALPITES      = 'palpites';
const SHEET_PLACAR_TIPO   = 'placar_tipo';
const SHEET_PLACAR_FASE   = 'placar_fase';
const SHEET_PLACAR_RODADA = 'placar_rodada';
const SHEET_RESULT        = 'result';
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
const COL_FIM           = 13;  // até onde lemos (lógica de palpites/resultados)
const COL_RODADA        = 14;  // N — rodada (usada só na aba Estatística)

// Colunas da aba "palpites"
const PCOL_JOGO         = 1;
const PCOL_USUARIO      = 2;
const PCOL_TIMESTAMP    = 3;
const PCOL_GOLS1        = 4;
const PCOL_GOLS2        = 5;

// Colunas da aba "result" (uma linha por palpite, enriquecida com pontuação)
const RCOL_JOGO         = 1;   // A
const RCOL_USUARIO      = 2;   // B
const RCOL_GOLS1        = 4;   // D
const RCOL_GOLS2        = 5;   // E
const RCOL_RODADA       = 14;  // N — rodada (Gr1, Gr2, ...)


// =========================================================================
// Entrada do Web App
// =========================================================================
function doGet() {
  return HtmlService.createTemplateFromFile('Index')
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
    const map = {}, countMap = {}, palpitesMap = {};
    pdata.forEach(function (r) {
      const u  = String(r[PCOL_USUARIO - 1] || '').toLowerCase();
      const g1 = r[PCOL_GOLS1 - 1];
      const g2 = r[PCOL_GOLS2 - 1];
      const jid = String(r[PCOL_JOGO - 1]);
      if (u && g1 !== '' && g1 !== null && g2 !== '' && g2 !== null) {
        countMap[jid] = (countMap[jid] || 0) + 1;
        if (!palpitesMap[jid]) palpitesMap[jid] = [];
        palpitesMap[jid].push({ usuario: u, gols1: Number(g1), gols2: Number(g2) });
      }
      if (u === email) {
        map[jid] = { gols1: g1, gols2: g2 };
      }
    });
    jogos.forEach(function (j) {
      const p = map[String(j.numero)];
      if (p) {
        j.gols1 = (p.gols1 === '' || p.gols1 === null) ? null : Number(p.gols1);
        j.gols2 = (p.gols2 === '' || p.gols2 === null) ? null : Number(p.gols2);
      }
      j.totalPalpites = countMap[String(j.numero)] || 0;
      const raw = (palpitesMap[String(j.numero)] || [])
        .slice().sort(function(a, b) { return a.usuario.localeCompare(b.usuario); });
      j.palpites = raw.map(function(q) {
        return j.iniciado
          ? { usuario: q.usuario, gols1: q.gols1, gols2: q.gols2 }
          : { usuario: q.usuario };
      });
    });
  }

  return { email: email, jogos: jogos, agoraIso: _agoraIso() };
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

  const iniciado = _jogoIniciado(jogoRow[COL_TITULO - 1], dataDisplay);

  const sp = _abaPalpites();
  const lastRowP = sp.getLastRow();
  if (lastRowP < 2) return { ok: true, iniciado: iniciado, palpites: [] };

  const pdata    = sp.getRange(2, 1, lastRowP - 1, 5).getValues();
  const palpites = [];
  pdata.forEach(function(r) {
    if (r[PCOL_JOGO - 1] != jogoId) return;
    const email = String(r[PCOL_USUARIO - 1] || '').toLowerCase();
    const g1    = r[PCOL_GOLS1 - 1];
    const g2    = r[PCOL_GOLS2 - 1];
    if (!email || g1 === '' || g1 === null || g2 === '' || g2 === null) return;
    // Antes do início só expõe o nome, não os palpites
    if (iniciado) {
      palpites.push({ usuario: email, gols1: Number(g1), gols2: Number(g2) });
    } else {
      palpites.push({ usuario: email });
    }
  });

  palpites.sort(function(a, b) {
    return a.usuario.localeCompare(b.usuario);
  });

  return { ok: true, iniciado: iniciado, palpites: palpites };
}


// =========================================================================
// API: retorna placar_tipo e placar_rodada (lidas diretamente das abas).
// =========================================================================
function getPlacar() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  function _ler(nome, ncols) {
    const sh = ss.getSheetByName(nome);
    if (!sh || sh.getLastRow() < 2) return [];
    return sh.getRange(2, 1, sh.getLastRow() - 1, ncols).getValues();
  }

  // placar_tipo: usuario | pt_venc | pt_placar | pt_gols | pt_total | jogos
  //              | pt_venc_apr (G) | pt_total_apr (H)
  // As colunas G e H são frações 0..1 (aproveitamento).
  const tipo = _ler(SHEET_PLACAR_TIPO, 8)
    .filter(function(r) { return r[0]; })
    .map(function(r) {
      return {
        nome:       String(r[0]).split('@')[0],
        pt_venc:    Number(r[1]) || 0,
        pt_placar:  Number(r[2]) || 0,
        pt_gols:    Number(r[3]) || 0,
        pt_total:   Number(r[4]) || 0,
        aprov_venc:  Number(r[6]) || 0,   // coluna G
        aprov_total: Number(r[7]) || 0    // coluna H
      };
    })
    .sort(function(a, b) { return b.pt_total - a.pt_total || a.nome.localeCompare(b.nome); });

  // placar_rodada: usuario (A) | rodadas (B..J) | total (K)
  // Cabeçalhos lidos da linha 1, colunas B a K (9 rodadas + total).
  let rodadaHeaders = [];
  const shRodada = ss.getSheetByName(SHEET_PLACAR_RODADA);
  if (shRodada && shRodada.getLastRow() >= 1) {
    rodadaHeaders = shRodada.getRange(1, 2, 1, 10).getValues()[0].map(function(h) {
      return String(h == null ? '' : h).trim();
    });
  }

  const rodada = _ler(SHEET_PLACAR_RODADA, 11)
    .filter(function(r) { return r[0]; })
    .map(function(r) {
      const valores = [];
      for (let c = 1; c <= 10; c++) valores.push(Number(r[c]) || 0);  // B..K
      return {
        nome:    String(r[0]).split('@')[0],
        valores: valores   // 9 rodadas + total (última posição)
      };
    })
    .sort(function(a, b) {
      const ta = a.valores[a.valores.length - 1];
      const tb = b.valores[b.valores.length - 1];
      return tb - ta || a.nome.localeCompare(b.nome);
    });

  return { tipo: tipo, rodada: rodada, rodadaHeaders: rodadaHeaders };
}


// =========================================================================
// API: retorna contagem de palpites por usuário, detalhada por rodada.
// A quantidade por rodada vem da aba "result" (coluna N), na mesma ordem
// das demais tabelas (cabeçalhos de placar_rodada: Gr1..F). O "total" por
// usuário é a soma — equivale ao número de palpites já registrados.
// =========================================================================
function getEstatisticas() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // Total de jogos ativos (considerar = 1)
  const tabela = ss.getSheetByName(SHEET_TABELA);
  let totalJogos = 0;
  if (tabela && tabela.getLastRow() >= 2) {
    const vals = tabela.getRange(2, 1, tabela.getLastRow() - 1, COL_CONSIDERAR).getValues();
    vals.forEach(function(r) { if (r[COL_CONSIDERAR - 1] == 1) totalJogos++; });
  }

  // Ordem das rodadas = cabeçalhos B..J da aba placar_rodada (Gr1..F).
  let rodadaLabels = [];
  const shRodada = ss.getSheetByName(SHEET_PLACAR_RODADA);
  if (shRodada && shRodada.getLastRow() >= 1) {
    rodadaLabels = shRodada.getRange(1, 2, 1, 9).getValues()[0]
      .map(function(h) { return String(h == null ? '' : h).trim(); })
      .filter(function(h) { return h; });
  }

  // Contagem por usuário e por rodada a partir da aba "result"
  // (col A=jogo, B=usuario, D/E=gols, N=rodada). Uma linha por palpite.
  const porUser = {};   // email -> { total, rodadas: { label: n } }
  const shResult = ss.getSheetByName(SHEET_RESULT);
  if (shResult && shResult.getLastRow() >= 2) {
    const rdata = shResult.getRange(2, 1, shResult.getLastRow() - 1, RCOL_RODADA).getValues();
    rdata.forEach(function(r) {
      const email = String(r[RCOL_USUARIO - 1] || '').toLowerCase().trim();
      const g1 = r[RCOL_GOLS1 - 1];
      const g2 = r[RCOL_GOLS2 - 1];
      if (!email) return;
      if (g1 === '' || g1 === null || g2 === '' || g2 === null) return;
      const rod = String(r[RCOL_RODADA - 1] == null ? '' : r[RCOL_RODADA - 1]).trim();
      if (!porUser[email]) porUser[email] = { total: 0, rodadas: {} };
      porUser[email].total++;
      if (rod) porUser[email].rodadas[rod] = (porUser[email].rodadas[rod] || 0) + 1;
    });
  }

  const usuarios = Object.keys(porUser).map(function(email) {
    const u = porUser[email];
    const porRodada = rodadaLabels.map(function(lbl) { return u.rodadas[lbl] || 0; });
    return { nome: email.split('@')[0], total: u.total, porRodada: porRodada };
  });
  usuarios.sort(function(a, b) {
    return b.total - a.total || a.nome.localeCompare(b.nome);
  });

  return { usuarios: usuarios, totalJogos: totalJogos, rodadaLabels: rodadaLabels };
}


// =========================================================================
// API: estatísticas agregadas POR RODADA (coluna N da aba "tabela").
// Para cada rodada devolve:
//   - inicioIso  : início do PRIMEIRO jogo da rodada (p/ contagem regressiva)
//   - totalGols  : soma de gols (colunas K + L) dos jogos JÁ realizados
//   - jogosComResultado : nº de jogos com K e L preenchidos
//   - golsPorPartida    : totalGols / jogosComResultado
//   - empates    : jogos em que K == L
//   - pctEmpates : empates / jogosComResultado * 100
//   - empates0a0 : empates em que K == L == 0
// Também devolve "agoraIso" (horário do servidor em Brasília) para que o
// front-end calcule a contagem regressiva sem depender do relógio local.
// =========================================================================
function getEstatisticasRodadas() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const tabela = ss.getSheetByName(SHEET_TABELA);
  if (!tabela) throw new Error('Aba "tabela" não encontrada.');

  const agoraIso = _agoraIso();
  const mapa = {};   // rodada -> agregados
  let proximo = null;   // próximo JOGO individual ainda não iniciado
  const lastRow = tabela.getLastRow();

  if (lastRow >= 2) {
    const range    = tabela.getRange(2, 1, lastRow - 1, COL_RODADA);
    const values   = range.getValues();
    const displays = range.getDisplayValues();

    for (let i = 0; i < values.length; i++) {
      const row = values[i];

      const rodadaRaw = row[COL_RODADA - 1];
      if (rodadaRaw === '' || rodadaRaw === null || rodadaRaw === undefined) continue;
      const rodada = String(rodadaRaw).trim();
      if (!rodada) continue;

      if (!mapa[rodada]) {
        mapa[rodada] = {
          rodada:            rodada,
          inicioIso:         null,
          totalJogos:        0,
          jogosComResultado: 0,
          totalGols:         0,
          empates:           0,
          empates0a0:        0
        };
      }
      const agg = mapa[rodada];
      agg.totalJogos++;

      // Início do primeiro jogo da rodada (menor data/hora)
      const inicioIso = _extrairInicioIso(row[COL_TITULO - 1], displays[i][COL_DATA_BR - 1]);
      if (inicioIso && (agg.inicioIso === null || inicioIso < agg.inicioIso)) {
        agg.inicioIso = inicioIso;
      }

      // Próximo JOGO individual ainda não iniciado (pode ser no meio de um grupo).
      // Considera apenas jogos ativos (considerar = 1) com início futuro.
      if (inicioIso && row[COL_CONSIDERAR - 1] == 1 && inicioIso > agoraIso) {
        if (!proximo || inicioIso < proximo.inicioIso) {
          proximo = {
            inicioIso: inicioIso,
            selecao1:  row[COL_SELECAO1 - 1] || '',
            selecao2:  row[COL_SELECAO2 - 1] || '',
            rodada:    rodada
          };
        }
      }

      // Resultado oficial (K e L). Só conta se AMBOS forem numéricos.
      const r1 = row[COL_RESULTADO1 - 1];
      const r2 = row[COL_RESULTADO2 - 1];
      const tem1 = (r1 !== '' && r1 !== null && r1 !== undefined && !isNaN(Number(r1)));
      const tem2 = (r2 !== '' && r2 !== null && r2 !== undefined && !isNaN(Number(r2)));
      if (tem1 && tem2) {
        const g1 = Number(r1), g2 = Number(r2);
        agg.jogosComResultado++;
        agg.totalGols += g1 + g2;
        if (g1 === g2) {
          agg.empates++;
          if (g1 === 0) agg.empates0a0++;
        }
      }
    }
  }

  const rodadas = Object.keys(mapa).map(function(k) {
    const a = mapa[k];
    return {
      rodada:            a.rodada,
      inicioIso:         a.inicioIso,
      iniciado:          a.inicioIso ? (agoraIso >= a.inicioIso) : false,
      totalJogos:        a.totalJogos,
      jogosComResultado: a.jogosComResultado,
      totalGols:         a.totalGols,
      golsPorPartida:    a.jogosComResultado > 0 ? a.totalGols / a.jogosComResultado : 0,
      empates:           a.empates,
      pctEmpates:        a.jogosComResultado > 0 ? a.empates / a.jogosComResultado * 100 : 0,
      empates0a0:        a.empates0a0
    };
  });

  // Ordena pela data do primeiro jogo; rodadas sem data vão para o fim.
  rodadas.sort(function(a, b) {
    if (a.inicioIso && b.inicioIso) {
      return a.inicioIso < b.inicioIso ? -1 : (a.inicioIso > b.inicioIso ? 1 : 0);
    }
    if (a.inicioIso) return -1;
    if (b.inicioIso) return 1;
    return 0;
  });

  return { agoraIso: agoraIso, rodadas: rodadas, proximoJogo: proximo };
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
