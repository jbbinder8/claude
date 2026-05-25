#!/usr/bin/env node
// Headless runner for phantom_jam simulation logic.
// Usage: node capture_phantom.js [simSeconds] [outputFile]
// Defaults: 300 sim seconds, output to capture_output.json

const SIM_SECONDS  = parseInt(process.argv[2] || '300');
const OUTPUT_FILE  = process.argv[3] || 'capture_output.json';
const SNAPSHOT_INTERVAL = 5; // capture state every N sim seconds

// ─── CONSTANTES (espelho de phantom_jam.html) ────────────────────────────────
const DS      = 2;
const S0      = 2;
const B_MAX   = 9.0;
const B_SAFE  = 4.0;
const B_SAFE_ZIPPER = 6.0;
const P_MOBIL = 0.2;
const DA_TH   = 0.2;
const DA_BIAS = 0.3;
const DT      = 1 / 60;
const L_OBRA  = 30;
const LANE_DUR = 1.0;
const D_SAFE  = 14;
const LOOK_AHEAD_CLEAR = 150;
const D_OBRA_PROX = 200;

const L_TRACK = 3000;
const N_WP    = Math.round(L_TRACK / DS) + 1;
const S_LIGHT = Math.round(L_TRACK / 2);       // 1500 m
const S_CONE  = Math.round(L_TRACK * 23 / 33); // ~2091 m

const VEHICLE_DEF = {
  car:   { lenM: 4,  amax: 1.5, b: 2.0, v0base: 33 },
  truck: { lenM: 12, amax: 0.7, b: 1.8, v0base: 22 }
};

// ─── PARÂMETROS (defaults do simulador) ──────────────────────────────────────
const params = {
  spawnRate:  1.0,
  truckPct:   15,
  reaction:   1.5,
  noise:      0.05,
  vmaxCar:    120 / 3.6,
  vmaxTruck:  80 / 3.6,
  amaxCar:    1.5,
  amaxTruck:  0.7,
  vdevCar:    0.10,
  vdevTruck:  0.10,
};

// Pode ser sobrescrito por variáveis de ambiente
if (process.env.SPAWN_RATE)  params.spawnRate  = parseFloat(process.env.SPAWN_RATE);
if (process.env.TRUCK_PCT)   params.truckPct   = parseFloat(process.env.TRUCK_PCT);
if (process.env.REACTION)    params.reaction   = parseFloat(process.env.REACTION);
if (process.env.LIGHT_RED)   lightRed          = process.env.LIGHT_RED === '1';
if (process.env.CONSTRUCTION) constructionOn   = process.env.CONSTRUCTION === '1';

// ─── ESTADO ──────────────────────────────────────────────────────────────────
let vehicles   = [];
let nextId     = 0;
let spawnAccum = 0;
let lightRed        = false;
let constructionOn  = false;
let despawnCount    = 0;
let simTime         = 0;

// ─── VEÍCULO ─────────────────────────────────────────────────────────────────
class Vehicle {
  constructor(type) {
    this.id    = nextId++;
    this.type  = type;
    const def  = VEHICLE_DEF[type];
    this.lenM  = def.lenM;
    this.amax  = def.amax;
    this.b     = def.b;
    this.mu    = 1.0;
    this.v0base = def.v0base;
    this.v0inst = def.v0base;
    this.s     = 0;
    this.v     = 0;
    this.lane  = 0;
    this.state = 'NORMAL';
    this.laneTarget   = 0;
    this.laneSrc      = 0;
    this.laneProgress = 1.0;
    this.accel = 0;
    this._v0eff = def.v0base;
  }
}

// ─── IDM ─────────────────────────────────────────────────────────────────────
function idmWithLeader(v, amax, b, v0eff, T, s_real, dv) {
  if (s_real < 0.1) s_real = 0.1;
  const sStar = S0 + v * T + (v * dv) / (2 * Math.sqrt(amax * b));
  const a = amax * (1 - Math.pow(v / v0eff, 4) - Math.pow(sStar / s_real, 2));
  return Math.max(-B_MAX, Math.min(amax, a));
}

function idmFree(v, amax, b, v0eff) {
  if (v0eff <= 0) return 0;
  return Math.max(-B_MAX, Math.min(amax, amax * (1 - Math.pow(v / v0eff, 4))));
}

function idmAccel(veh, leader, T, v0eff) {
  if (!leader) return idmFree(veh.v, veh.amax, veh.b, v0eff);
  const s_real = leader.s - veh.s - leader.lenM;
  const dv     = veh.v - leader.v;
  return idmWithLeader(veh.v, veh.amax, veh.b, v0eff, T, s_real, dv);
}

function idmRaw(sEgo, vEgo, amax, b, v0, T, sLeader, vLeader, lenLeader) {
  const s_real = sLeader - sEgo - lenLeader;
  const dv     = vEgo - vLeader;
  return idmWithLeader(vEgo, amax, b, v0, T, s_real, dv);
}

// ─── FANTASMAS (obstáculos) ───────────────────────────────────────────────────
function ghostsForLane(lane) {
  const g = [];
  if (lightRed)                       g.push({ s: S_LIGHT, v: 0, lenM: 0 });
  if (constructionOn && lane === 0)   g.push({ s: S_CONE,  v: 0, lenM: 0 });
  return g;
}

// ─── BUSCA DE LÍDER / SEGUIDOR ────────────────────────────────────────────────
function findLeader(veh, laneOverride) {
  const lane = laneOverride !== undefined ? laneOverride : veh.lane;
  const cands = vehicles.filter(v => v !== veh && v.lane === lane && v.s > veh.s);
  const all   = [...cands, ...ghostsForLane(lane).filter(g => g.s > veh.s)];
  if (!all.length) return null;
  return all.reduce((a, b) => a.s < b.s ? a : b);
}

function findFollower(veh, laneOverride) {
  const lane = laneOverride !== undefined ? laneOverride : veh.lane;
  const cands = vehicles.filter(v => v !== veh && v.lane === lane && v.s < veh.s);
  if (!cands.length) return null;
  return cands.reduce((a, b) => a.s > b.s ? a : b);
}

function findRearFollower(veh, lane) {
  const rear = veh.s - veh.lenM;
  const cands = vehicles.filter(v => v !== veh && v.lane === lane && v.s <= rear);
  if (!cands.length) return null;
  return cands.reduce((a, b) => a.s > b.s ? a : b);
}

// ─── MOBIL ────────────────────────────────────────────────────────────────────
function evalMOBIL(veh, T) {
  if (veh.state !== 'NORMAL') return;

  const curLane = veh.lane;
  const altLane = 1 - curLane;
  const v0eff   = veh._v0eff;

  // Modo emergência: obra à frente na faixa 0 (< 150 m)
  if (constructionOn && curLane === 0 && S_CONE > veh.s && (S_CONE - veh.s) < 150) {
    const followerL = findFollower(veh, 1);
    // Critério de segurança com b_safe_zipper
    const safe = !followerL || idmRaw(
      followerL.s, followerL.v, followerL.amax, followerL.b,
      followerL._v0eff, T, veh.s, veh.v, veh.lenM
    ) >= -B_SAFE_ZIPPER;
    if (safe) startLaneChange(veh, 1);
    return;
  }

  // Bloqueia retorno à direita apenas dentro de D_OBRA_PROX da obra
  if (constructionOn && curLane === 1 && altLane === 0 &&
      S_CONE > veh.s && (S_CONE - veh.s) < D_OBRA_PROX) return;

  const leaderCur       = findLeader(veh, curLane);
  const leaderAlt       = findLeader(veh, altLane);
  const followerCur = findFollower(veh, curLane);
  const followerAlt = findFollower(veh, altLane);

  // Bloqueia troca se gap para líder na faixa alvo < S0 (evita sobreposição e clamping a s=0)
  if (leaderAlt && leaderAlt.s - leaderAlt.lenM - veh.s < S0) return;

  // ── CRITÉRIO DE SEGURANÇA (spec 5.2) — bloqueia todas as trocas de faixa ──
  let a_n = 0, a_n_prime = 0;
  if (followerAlt) {
    a_n = followerAlt.accel;
    a_n_prime = idmRaw(
      followerAlt.s, followerAlt.v, followerAlt.amax, followerAlt.b,
      followerAlt._v0eff, T, veh.s, veh.v, veh.lenM
    );
    if (a_n_prime < -B_SAFE) return;
  }

  // Regra: só vai à esquerda para ultrapassar ou desviar de obra
  if (altLane === 1) {
    if (!leaderCur) return;
    const thresh = veh.type === 'truck' ? 0.60 : 0.85;
    if (leaderCur.v >= v0eff * thresh) return;
  }

  // Retorno proativo à direita (spec 5.6): faixa 0 livre = ninguém mais devagar que o EGO
  if (altLane === 0 && curLane === 1) {
    const slowAhead = vehicles.some(v =>
      v !== veh && v.lane === 0 && v.s > veh.s &&
      v.s - veh.s < LOOK_AHEAD_CLEAR && v.v < veh.v
    ) || ghostsForLane(0).some(g => g.s > veh.s && g.s - veh.s < LOOK_AHEAD_CLEAR);

    if (!slowAhead) {
      startLaneChange(veh, 0);
      return;
    }
  }

  // Spec 5.7: líder na faixa esquerda quase parado (< 5 m/s), direita fluindo
  if (altLane === 0 && curLane === 1) {
    const V_CONGEST = 5, D_CONGEST = 100;
    const leftJammed = vehicles.some(v =>
      v !== veh && v.lane === 1 && v.s > veh.s &&
      v.s - veh.s < D_CONGEST && v.v < V_CONGEST
    );
    const slowAheadRight = vehicles.some(v =>
      v !== veh && v.lane === 0 && v.s > veh.s &&
      v.s - veh.s < LOOK_AHEAD_CLEAR && v.v < veh.v * 0.8
    ) || ghostsForLane(0).some(g => g.s > veh.s && g.s - veh.s < LOOK_AHEAD_CLEAR);
    if (leftJammed && !slowAheadRight) { startLaneChange(veh, 0); return; }
  }

  // Incentivo MOBIL
  const a_c = veh.accel;
  const a_c_prime = leaderAlt
    ? idmRaw(veh.s, veh.v, veh.amax, veh.b, v0eff, T,
             leaderAlt.s, leaderAlt.v, leaderAlt.lenM)
    : idmFree(veh.v, veh.amax, veh.b, v0eff);

  let a_o = 0, a_o_prime = 0;
  if (followerCur) {
    a_o = followerCur.accel;
    a_o_prime = leaderCur
      ? idmRaw(followerCur.s, followerCur.v, followerCur.amax, followerCur.b,
               followerCur._v0eff, T, leaderCur.s, leaderCur.v, leaderCur.lenM)
      : idmFree(followerCur.v, followerCur.amax, followerCur.b, followerCur._v0eff);
  }

  const toRight = altLane === 0;
  const bias    = toRight ? DA_BIAS : -DA_BIAS;
  const gain    = (a_c_prime - a_c) + P_MOBIL * ((a_n_prime - a_n) + (a_o_prime - a_o)) + bias;
  if (gain > DA_TH) startLaneChange(veh, altLane);
}

function startLaneChange(veh, targetLane) {
  veh.laneSrc      = veh.lane;
  veh.laneTarget   = targetLane;
  veh.laneProgress = 0;
  veh.state        = 'TROCANDO_FAIXA';
  veh.lane         = targetLane;
}

// ─── SPAWNER ──────────────────────────────────────────────────────────────────
function trySpawn(dt) {
  spawnAccum += params.spawnRate * dt;
  while (spawnAccum >= 1) {
    spawnAccum -= 1;
    const type = Math.random() * 100 < params.truckPct ? 'truck' : 'car';
    let spawnLane;
    if (type === 'truck') {
      if (vehicles.some(v => v.lane === 0 && v.s < D_SAFE)) continue;
      spawnLane = 0;
    } else {
      const free0 = !vehicles.some(v => v.lane === 0 && v.s < D_SAFE);
      const free1 = !vehicles.some(v => v.lane === 1 && v.s < D_SAFE);
      if (!free0 && !free1) continue;
      if (free0 && free1) {
        const cnt0 = vehicles.filter(v => v.lane === 0 && v.s < 150).length;
        const cnt1 = vehicles.filter(v => v.lane === 1 && v.s < 150).length;
        spawnLane = cnt0 <= cnt1 ? 0 : 1;
      } else {
        spawnLane = free0 ? 0 : 1;
      }
    }
    const veh    = new Vehicle(type);
    const def    = VEHICLE_DEF[type];
    const vmaxMs = type === 'car' ? params.vmaxCar : params.vmaxTruck;
    const delta  = type === 'car' ? params.vdevCar : params.vdevTruck;
    const mu     = delta > 0 ? 1 - delta + Math.random() * 2 * delta : 1.0;
    veh.lane   = spawnLane;
    veh.mu     = mu;
    veh.v0base = Math.min(def.v0base, vmaxMs);
    veh.v0inst = mu * veh.v0base;
    veh._v0eff = veh.v0inst;
    veh.v      = 0.8 * veh.v0inst;
    veh.amax   = type === 'car' ? params.amaxCar : params.amaxTruck;
    vehicles.push(veh);
  }
}

// ─── UPDATE ───────────────────────────────────────────────────────────────────
function update(dt) {
  const T = params.reaction;

  // Ruído por-frame
  const eta = params.noise;
  for (const veh of vehicles) {
    const xi = Math.random() * 2 - 1;
    veh._v0eff = Math.max(0.1, veh.v0inst * (1 + eta * xi));
  }

  // MOBIL antes do spawn: spawn vê faixas finais, evita colisão entre recém-mudados e recém-criados
  for (const veh of vehicles) evalMOBIL(veh, T);

  // Spawner
  trySpawn(dt);

  // IDM
  for (const veh of vehicles) {
    const leader = findLeader(veh);
    veh.accel = idmAccel(veh, leader, T, veh._v0eff);
  }

  // Integração Euler
  for (const veh of vehicles) {
    veh.v = Math.max(0, veh.v + veh.accel * dt);
    veh.s = veh.s + veh.v * dt;
  }

  // Correção anti-colisão
  for (let lane = 0; lane < 2; lane++) {
    const inLane = vehicles
      .filter(v => v.lane === lane)
      .sort((a, b) => b.s - a.s);
    for (let i = 1; i < inLane.length; i++) {
      const leader   = inLane[i - 1];
      const follower = inLane[i];
      const minDist  = leader.lenM + S0;
      if (follower.s + minDist > leader.s) {
        follower.s = leader.s - minDist;
        follower.v = Math.min(follower.v, leader.v);
        if (follower.s < 0) follower.s = 0;
      }
    }
  }

  // Transição visual de faixa
  for (const veh of vehicles) {
    if (veh.state === 'TROCANDO_FAIXA') {
      veh.laneProgress += dt / LANE_DUR;
      if (veh.laneProgress >= 1.0) {
        veh.laneProgress = 1.0;
        veh.state = 'NORMAL';
      }
    }
  }

  // Despawn
  vehicles = vehicles.filter(veh => {
    if (veh.s > L_TRACK) { despawnCount++; return false; }
    return true;
  });
}

// ─── MÉTRICAS ─────────────────────────────────────────────────────────────────
function computeMetrics() {
  const n = vehicles.length;
  if (n === 0) return { count: 0, avgSpeedKmh: 0, minSpeedKmh: 0, maxSpeedKmh: 0,
                        lane0Count: 0, lane1Count: 0, changingCount: 0,
                        jamCount: 0, collisions: 0 };

  const speeds = vehicles.map(v => v.v * 3.6);
  const avgSpeed = speeds.reduce((a, b) => a + b, 0) / n;

  // Detectar engarrafamentos: veículo < 5 km/h
  const jamCount = vehicles.filter(v => v.v * 3.6 < 5).length;

  // Detectar colisões (separação < 0)
  let collisions = 0;
  for (let lane = 0; lane < 2; lane++) {
    const inLane = vehicles.filter(v => v.lane === lane).sort((a, b) => a.s - b.s);
    for (let i = 0; i < inLane.length - 1; i++) {
      const gap = inLane[i + 1].s - inLane[i].s - inLane[i + 1].lenM;
      if (gap < 0) collisions++;
    }
  }

  // Distribuição de velocidades (percentis aproximados)
  const sorted = [...speeds].sort((a, b) => a - b);
  const p10 = sorted[Math.floor(n * 0.1)];
  const p50 = sorted[Math.floor(n * 0.5)];
  const p90 = sorted[Math.floor(n * 0.9)];

  // Densidade por segmento (10 segmentos de 300 m cada)
  const segments = Array(10).fill(0);
  for (const v of vehicles) {
    const seg = Math.min(9, Math.floor(v.s / 300));
    segments[seg]++;
  }

  return {
    count:         n,
    avgSpeedKmh:   avgSpeed.toFixed(1),
    minSpeedKmh:   Math.min(...speeds).toFixed(1),
    maxSpeedKmh:   Math.max(...speeds).toFixed(1),
    p10SpeedKmh:   (p10 || 0).toFixed(1),
    p50SpeedKmh:   (p50 || 0).toFixed(1),
    p90SpeedKmh:   (p90 || 0).toFixed(1),
    lane0Count:    vehicles.filter(v => v.lane === 0).length,
    lane1Count:    vehicles.filter(v => v.lane === 1).length,
    changingCount: vehicles.filter(v => v.state === 'TROCANDO_FAIXA').length,
    jamCount,
    collisions,
    densityBySegment: segments,
  };
}

// ─── ANOMALIAS ───────────────────────────────────────────────────────────────
function detectAnomalies() {
  const issues = [];

  // 1. Colisões / sobreposição
  for (let lane = 0; lane < 2; lane++) {
    const inLane = vehicles.filter(v => v.lane === lane).sort((a, b) => a.s - b.s);
    for (let i = 0; i < inLane.length - 1; i++) {
      const a = inLane[i], b = inLane[i + 1];
      const gap = b.s - a.s - b.lenM;
      if (gap < -0.5) {
        issues.push({ type: 'OVERLAP', lane, follower: b.id, leader: a.id,
                      gap: gap.toFixed(2) });
      }
    }
  }

  // 2. Velocidade negativa
  for (const v of vehicles) {
    if (v.v < -0.01) issues.push({ type: 'NEG_SPEED', id: v.id, v: v.v });
  }

  // 3. Veículo além do fim da pista ainda no array
  for (const v of vehicles) {
    if (v.s > L_TRACK) issues.push({ type: 'PAST_END', id: v.id, s: v.s });
  }

  // 4. Veículo na faixa errada (caminhão na faixa 1 por muito tempo > 10 s)
  // (não rastreamos tempo por veículo aqui, mas registramos presença)
  const trucksInL1 = vehicles.filter(v => v.type === 'truck' && v.lane === 1).length;
  if (trucksInL1 > 0) {
    issues.push({ type: 'TRUCKS_LEFT_LANE', count: trucksInL1 });
  }

  // 5. Veículos presos (v=0 sem obstáculo à frente)
  for (const v of vehicles) {
    if (v.v < 0.01 && v.accel < 0.001) {
      const leader = findLeader(v);
      if (!leader) issues.push({ type: 'STUCK_NO_LEADER', id: v.id, s: v.s, lane: v.lane });
    }
  }

  return issues;
}

// ─── MAIN ─────────────────────────────────────────────────────────────────────
const snapshots = [];
const allAnomalies = [];
let totalSteps = 0;
const stepsPerSnapshot = Math.round(SNAPSHOT_INTERVAL / DT);

console.log(`Phantom Jam headless capture`);
console.log(`  Sim duration: ${SIM_SECONDS} s`);
console.log(`  Snapshot every: ${SNAPSHOT_INTERVAL} s`);
console.log(`  Spawn rate: ${params.spawnRate} veh/s | Trucks: ${params.truckPct}%`);
console.log(`  lightRed=${lightRed} | constructionOn=${constructionOn}`);
console.log('');

const totalStepsNeeded = Math.round(SIM_SECONDS / DT);

for (let step = 0; step < totalStepsNeeded; step++) {
  update(DT);
  simTime += DT;
  totalSteps++;

  if (step % stepsPerSnapshot === 0) {
    const metrics = computeMetrics();
    const anomalies = detectAnomalies();
    snapshots.push({
      simTime: simTime.toFixed(1),
      metrics,
      anomalies,
    });
    allAnomalies.push(...anomalies.map(a => ({ ...a, simTime: simTime.toFixed(1) })));

    process.stdout.write(`\r  t=${simTime.toFixed(0).padStart(5)} s | veic=${metrics.count} | avg=${metrics.avgSpeedKmh} km/h | jammed=${metrics.jamCount} | issues=${anomalies.length}   `);
  }
}
console.log('\n');

// Resumo final
const finalMetrics = computeMetrics();
const anomalyTypes = {};
for (const a of allAnomalies) {
  anomalyTypes[a.type] = (anomalyTypes[a.type] || 0) + 1;
}

const output = {
  config: { SIM_SECONDS, SNAPSHOT_INTERVAL, params, lightRed, constructionOn,
            constants: { DA_BIAS, LOOK_AHEAD_CLEAR, D_OBRA_PROX, B_SAFE, B_SAFE_ZIPPER } },
  summary: {
    totalSteps,
    despawnCount,
    finalMetrics,
    anomalySummary: anomalyTypes,
  },
  snapshots,
};

const fs = require('fs');
fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2));

console.log('=== RESUMO FINAL ===');
console.log(`Veículos ativos: ${finalMetrics.count}`);
console.log(`Velocidade média: ${finalMetrics.avgSpeedKmh} km/h`);
console.log(`Engarrafados (< 5 km/h): ${finalMetrics.jamCount}`);
console.log(`Colisões detectadas: ${finalMetrics.collisions}`);
console.log(`Despawn total: ${despawnCount}`);
console.log('Anomalias por tipo:', anomalyTypes);
console.log(`\nSalvo em: ${OUTPUT_FILE}`);
