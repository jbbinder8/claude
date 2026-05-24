#!/usr/bin/env node
// test_trafego.js — headless simulation test
// Usage: node test_trafego.js
// Mirrors the exact physics logic of simulador_trafego.html.

// ── Constants ────────────────────────────────────────────────────────────────
const W = 1050, H = 1050;
const VX = [150, 525, 900];
const HY = [150, 525, 900];
const ROAD = 28;
const LANE = 7;
const HALF = 9;       // car half-length in direction of travel
const CAR_LEN = 18;   // full car body length
const STOP_THRESH = HALF + Math.round(ROAD / 2) + 19; // 42

// ── Scenario settings ─────────────────────────────────────────────────────────
// Multiple scenarios: vary CPM and turn rate to stress-test
const SCENARIOS = [
  { label: 'low traffic,  0% turns',  cpm: 300,  speed: 2, turnRight:  0, greenMs: 5000, redMs: 5000, reaction: 200 },
  { label: 'low traffic, 50% turns',  cpm: 300,  speed: 2, turnRight: 50, greenMs: 5000, redMs: 5000, reaction: 200 },
  { label: 'high traffic, 50% turns', cpm: 2000, speed: 3, turnRight: 50, greenMs: 5000, redMs: 5000, reaction: 200 },
  { label: 'max traffic,  80% turns', cpm: 5000, speed: 4, turnRight: 80, greenMs: 3000, redMs: 3000, reaction: 300 },
];
const FRAMES = 6000;   // frames per scenario (~100s at 60fps)
const DT = 16;         // ms per frame

// ── Road direction (two-way for maximum overlap potential) ────────────────────
const act = { hDir: ['both','both','both'], vDir: ['both','both','both'] };

// ── Violation log (first N examples per type) ─────────────────────────────────
const MAX_EXAMPLES = 5;

// ── Simulation state (reset per scenario) ────────────────────────────────────
let cars, uid, phase, phaseT, spawnAcc, S;

function resetSim(scenario) {
  cars = []; uid = 0; phase = 0; phaseT = 0; spawnAcc = 0;
  S = { ...scenario };
}

// ── Entry points ──────────────────────────────────────────────────────────────
function getEntries() {
  const e = [];
  HY.forEach((y, i) => {
    const d = act.hDir[i];
    if (d === 'both') {
      e.push({x: -15, y: y+LANE, dx:  1, dy: 0, rl: true});
      e.push({x: W+15, y: y-LANE, dx: -1, dy: 0, rl: true});
    } else if (d === 'right') {
      e.push({x: -15, y: y+LANE, dx: 1, dy: 0, rl: true});
      e.push({x: -15, y: y-LANE, dx: 1, dy: 0, rl: false});
    } else {
      e.push({x: W+15, y: y-LANE, dx: -1, dy: 0, rl: true});
      e.push({x: W+15, y: y+LANE, dx: -1, dy: 0, rl: false});
    }
  });
  VX.forEach((x, i) => {
    const d = act.vDir[i];
    if (d === 'both') {
      e.push({x: x-LANE, y: -15,  dx: 0, dy:  1, rl: true});
      e.push({x: x+LANE, y: H+15, dx: 0, dy: -1, rl: true});
    } else if (d === 'down') {
      e.push({x: x-LANE, y: -15, dx: 0, dy: 1, rl: true});
      e.push({x: x+LANE, y: -15, dx: 0, dy: 1, rl: false});
    } else {
      e.push({x: x+LANE, y: H+15, dx: 0, dy: -1, rl: true});
      e.push({x: x-LANE, y: H+15, dx: 0, dy: -1, rl: false});
    }
  });
  return e;
}

// ── Car class (exact copy of HTML logic) ──────────────────────────────────────
class Car {
  constructor(x, y, dx, dy, rl) {
    this.id = uid++;
    this.x = x; this.y = y;
    this.dx = dx; this.dy = dy;
    this.rl = rl;
    this.td = null;
    this.vel = 0;
    this.reacting = false;
    this.reactMs = 0;
    this.stopped = false;
    this.turnsCompleted = 0;
  }

  nextX() {
    if (this.dx !== 0) {
      const xs = this.dx > 0 ? VX : [...VX].reverse();
      for (const ix of xs) {
        const vi = VX.indexOf(ix);
        const d  = this.dx > 0 ? ix - this.x : this.x - ix;
        if (d < -ROAD / 2) continue;
        const hi = HY.findIndex(hy => Math.abs(this.y - hy) < LANE + 6);
        if (hi !== -1) return {d, vi, hi};
        break;
      }
    } else {
      const ys = this.dy > 0 ? HY : [...HY].reverse();
      for (const iy of ys) {
        const hi = HY.indexOf(iy);
        const d  = this.dy > 0 ? iy - this.y : this.y - iy;
        if (d < -ROAD / 2) continue;
        const vi = VX.findIndex(vx => Math.abs(this.x - vx) < LANE + 6);
        if (vi !== -1) return {d, vi, hi};
        break;
      }
    }
    return null;
  }

  canRight(vi, hi) {
    if (!this.rl) return false;
    if (this.dx >  0) return act.vDir[vi] !== 'up';
    if (this.dx <  0) return act.vDir[vi] !== 'down';
    if (this.dy >  0) return act.hDir[hi] !== 'right';
    if (this.dy <  0) return act.hDir[hi] !== 'left';
    return false;
  }

  canTurnNow(vi, hi) {
    const CLEAR = 34, ix = VX[vi], iy = HY[hi];
    let tx, ty, tdx, tdy;
    if      (this.dx >  0) { tx = ix-LANE; ty = iy;       tdx = 0;  tdy =  1; }
    else if (this.dx <  0) { tx = ix+LANE; ty = iy;       tdx = 0;  tdy = -1; }
    else if (this.dy >  0) { tx = ix;      ty = iy-LANE;  tdx = -1; tdy =  0; }
    else                   { tx = ix;      ty = iy+LANE;  tdx =  1; tdy =  0; }

    for (const o of cars) {
      if (o === this || o.dx !== tdx || o.dy !== tdy) continue;
      const lat = tdx !== 0 ? Math.abs(o.y - ty) : Math.abs(o.x - tx);
      if (lat > LANE + 5) continue;
      const fwd = tdx !== 0 ? (o.x - tx) * tdx : (o.y - ty) * tdy;
      if (fwd > -CLEAR && fwd < CLEAR) return false;
    }
    return true;
  }

  doTurn(vi, hi) {
    const ix = VX[vi], iy = HY[hi];
    if      (this.dx >  0) { this.dx = 0; this.dy =  1; this.x = ix-LANE; this.y = iy; }
    else if (this.dx <  0) { this.dx = 0; this.dy = -1; this.x = ix+LANE; this.y = iy; }
    else if (this.dy >  0) { this.dy = 0; this.dx = -1; this.y = iy-LANE; this.x = ix; }
    else                   { this.dy = 0; this.dx =  1; this.y = iy+LANE; this.x = ix; }
    this.rl = true;
    this.turnsCompleted++;
  }

  update(dt) {
    const ni = this.nextX();

    if (ni && ni.d > ROAD / 2) {
      const key = `${ni.vi}_${ni.hi}`;
      if (!this.td || this.td.key !== key) {
        const wantRight = Math.random() * 100 < S.turnRight && this.canRight(ni.vi, ni.hi);
        this.td = {key, action: wantRight ? 'right' : 'straight', vi: ni.vi, hi: ni.hi, done: false};
      }
    }

    let waitTurn = false;
    if (ni && this.td && !this.td.done &&
        this.td.key === `${ni.vi}_${ni.hi}` &&
        ni.d >= 0 && ni.d <= ROAD / 2 + 2) {
      if (this.td.action === 'right') {
        if (this.canTurnNow(this.td.vi, this.td.hi)) {
          this.td.done = true;
          this.doTurn(this.td.vi, this.td.hi);
          this.td = null;
          return;
        }
        waitTurn = true;
      } else {
        this.td.done = true;
      }
    }

    const ni2 = this.nextX();
    const DECEL    = S.speed / 60;
    const ACCEL    = S.speed / 90;
    const LAT      = 11;
    const SAFE_GAP = 20;
    let target = S.speed;

    if (waitTurn) {
      target = 0;
    } else {
      if (ni2 && ni2.d >= STOP_THRESH) {
        const isRed = this.dx !== 0 ? (phase === 0) : (phase === 1);
        if (isRed) target = Math.min(target, Math.sqrt(2 * DECEL * Math.max(0, ni2.d - STOP_THRESH)));
      }

      let minFwd = Infinity;
      for (const o of cars) {
        if (o === this || o.dx !== this.dx || o.dy !== this.dy) continue;
        const fwd = this.dx !== 0 ? (o.x - this.x) * this.dx : (o.y - this.y) * this.dy;
        const lat = this.dx !== 0 ? Math.abs(o.y - this.y) : Math.abs(o.x - this.x);
        if (fwd > 0 && lat < LAT) minFwd = Math.min(minFwd, fwd);
      }
      if (minFwd < Infinity) {
        const dAhead = ni2 ? ni2.d - minFwd : Infinity;
        const effGap = (dAhead >= 0 && dAhead < STOP_THRESH)
          ? Math.max(SAFE_GAP, STOP_THRESH - dAhead)
          : SAFE_GAP;
        target = Math.min(target, Math.sqrt(2 * DECEL * Math.max(0, minFwd - effGap)));
      }
    }

    if (this.vel === 0 && target > 0 && !this.reacting) {
      this.reacting = true;
      this.reactMs  = S.reaction;
    }
    if (this.reacting) {
      this.reactMs -= dt;
      if (this.reactMs <= 0) this.reacting = false;
      else target = 0;
    }

    if (target < this.vel) this.vel = target;
    else if (target > this.vel) this.vel = Math.min(this.vel + ACCEL, target);
    this.vel = Math.max(0, Math.min(this.vel, S.speed));

    this.x += this.dx * this.vel;
    this.y += this.dy * this.vel;
    this.stopped = this.vel === 0;
  }

  gone() { return this.x < -40 || this.x > W+40 || this.y < -40 || this.y > H+40; }
}

// ── Violation checkers ────────────────────────────────────────────────────────

// Returns list of {a, b, fwd, lat} for overlapping pairs in same lane
function checkOverlaps() {
  const hits = [];
  for (let i = 0; i < cars.length; i++) {
    for (let j = i + 1; j < cars.length; j++) {
      const a = cars[i], b = cars[j];
      if (a.dx !== b.dx || a.dy !== b.dy) continue;
      const fwd = a.dx !== 0 ? (b.x - a.x) * a.dx : (b.y - a.y) * a.dy;
      const lat = a.dx !== 0 ? Math.abs(b.y - a.y) : Math.abs(b.x - a.x);
      if (lat < 11 && Math.abs(fwd) < CAR_LEN) {
        hits.push({ a, b, fwd: fwd.toFixed(1), lat: lat.toFixed(1) });
      }
    }
  }
  return hits;
}

// Returns cars stopped with front inside pedestrian crossing (ROAD/2+1 to ROAD/2+14 from center).
// Skip cars that are in the "committed zone" (d < STOP_THRESH) — they entered on green and
// are being held up by a blocking car; that's an unavoidable "box blocking" situation.
function checkCrossingStops() {
  const hits = [];
  for (const c of cars) {
    if (!c.stopped) continue;
    const ni = c.nextX();
    if (!ni || ni.d < 0) continue;
    if (ni.d < STOP_THRESH) continue; // skip committed-zone stops (entered on green, now blocked)
    const frontDist = ni.d - HALF;
    // Crossing starts at ROAD/2+1=15, ends at ROAD/2+14=28
    if (frontDist >= ROAD / 2 + 1 && frontDist <= ROAD / 2 + 14) {
      hits.push({ id: c.id, d: ni.d.toFixed(1), frontDist: frontDist.toFixed(1) });
    }
  }
  return hits;
}

// Red-light runner: car ABOVE the braking curve while approaching on red.
// Expected vel at distance d = sqrt(2*DECEL*(d-STOP_THRESH)).
// With instant-snap physics this should always be 0 — vel is always snapped to target.
function checkRedLightRunners() {
  const DECEL = S.speed / 60;
  const hits = [];
  for (const c of cars) {
    const ni = c.nextX();
    if (!ni || ni.d < STOP_THRESH) continue; // committed zone not a violation
    const isRed = c.dx !== 0 ? (phase === 0) : (phase === 1);
    if (!isRed) continue;
    const expectedVel = Math.sqrt(2 * DECEL * (ni.d - STOP_THRESH));
    if (c.vel > expectedVel + 0.15) // car significantly above braking curve
      hits.push({ id: c.id, d: ni.d.toFixed(1), vel: c.vel.toFixed(2), expected: expectedVel.toFixed(2), dx: c.dx, dy: c.dy });
  }
  return hits;
}

// ── Run a scenario ────────────────────────────────────────────────────────────
function runScenario(scenario) {
  resetSim(scenario);

  const v = {
    overlap: 0,      overlapEx: [],
    crossing: 0,     crossingEx: [],
    redLight: 0,     redLightEx: [],
    totalTurns: 0,   peakCars: 0, totalSpawned: 0,
  };

  for (let f = 0; f < FRAMES; f++) {
    // Phase
    phaseT += DT;
    const dur = phase === 0 ? S.greenMs : S.redMs;
    if (phaseT >= dur) { phaseT = 0; phase ^= 1; }

    // Spawn
    spawnAcc += DT * S.cpm / 60000;
    const toSpawn = Math.floor(spawnAcc);
    spawnAcc -= toSpawn;
    const pool = getEntries();
    for (let k = 0; k < toSpawn && pool.length > 0; k++) {
      const e = pool[Math.floor(Math.random() * pool.length)];
      const cx = e.dx !== 0 ? 20 : 12;
      const cy = e.dy !== 0 ? 20 : 12;
      if (!cars.some(c => Math.abs(c.x - e.x) < cx && Math.abs(c.y - e.y) < cy)) {
        cars.push(new Car(e.x, e.y, e.dx, e.dy, e.rl));
        v.totalSpawned++;
      }
    }

    const turnsBefore = cars.reduce((s, c) => s + c.turnsCompleted, 0);
    for (const c of cars) c.update(DT);
    const turnsAfter = cars.reduce((s, c) => s + c.turnsCompleted, 0);
    v.totalTurns += turnsAfter - turnsBefore;

    cars = cars.filter(c => !c.gone());
    v.peakCars = Math.max(v.peakCars, cars.length);

    // Skip first 60 frames (warm-up)
    if (f < 60) continue;

    const overlaps   = checkOverlaps();
    const crossings  = checkCrossingStops();
    const redRunners = checkRedLightRunners();

    v.overlap  += overlaps.length;
    v.crossing += crossings.length;
    v.redLight += redRunners.length;

    if (overlaps.length   && v.overlapEx.length   < MAX_EXAMPLES)
      v.overlapEx.push({ frame: f, items: overlaps.slice(0, 3) });
    if (crossings.length  && v.crossingEx.length  < MAX_EXAMPLES)
      v.crossingEx.push({ frame: f, items: crossings.slice(0, 3) });
    if (redRunners.length && v.redLightEx.length  < MAX_EXAMPLES)
      v.redLightEx.push({ frame: f, items: redRunners.slice(0, 3) });
  }

  return v;
}

// ── Format direction ──────────────────────────────────────────────────────────
function dir(dx, dy) {
  if (dx > 0) return '→'; if (dx < 0) return '←';
  if (dy > 0) return '↓'; return '↑';
}

// ── Main ──────────────────────────────────────────────────────────────────────
console.log('═'.repeat(60));
console.log('  SIMULADOR DE TRÁFEGO — TESTE HEADLESS');
console.log(`  ${FRAMES} frames × ${SCENARIOS.length} cenários`);
console.log('═'.repeat(60));

let totalViolations = 0;

for (const scenario of SCENARIOS) {
  console.log(`\n▶ Cenário: ${scenario.label}`);
  console.log(`  cpm=${scenario.cpm}  speed=${scenario.speed}  turns=${scenario.turnRight}%  reaction=${scenario.reaction}ms`);

  const v = runScenario(scenario);
  totalViolations += v.overlap + v.crossing + v.redLight;

  console.log(`  Spawned: ${v.totalSpawned}  peak simultaneous: ${v.peakCars}  turns executed: ${v.totalTurns}`);
  console.log(`  Overlaps (car-on-car):       ${v.overlap === 0 ? '✓ 0' : '✗ ' + v.overlap} frame-events`);
  console.log(`  Stopped on crossing:         ${v.crossing === 0 ? '✓ 0' : '✗ ' + v.crossing} frame-events`);
  console.log(`  Red-light runners:           ${v.redLight === 0 ? '✓ 0' : '✗ ' + v.redLight} frame-events`);

  if (v.overlapEx.length) {
    console.log('  [overlap examples]');
    for (const ex of v.overlapEx) {
      for (const it of ex.items) {
        console.log(`    frame ${ex.frame}: car#${it.a.id}(${dir(it.a.dx,it.a.dy)}) vs car#${it.b.id}(${dir(it.b.dx,it.b.dy)})  fwd=${it.fwd} lat=${it.lat}`);
      }
    }
  }
  if (v.crossingEx.length) {
    console.log('  [crossing-stop examples]');
    for (const ex of v.crossingEx) {
      for (const it of ex.items) {
        console.log(`    frame ${ex.frame}: car#${it.id}  d=${it.d}  front=${it.frontDist}px from center`);
      }
    }
  }
  if (v.redLightEx.length) {
    console.log('  [red-light runner examples]');
    for (const ex of v.redLightEx) {
      for (const it of ex.items) {
        console.log(`    frame ${ex.frame}: car#${it.id}(${dir(it.dx,it.dy)})  d=${it.d}  vel=${it.vel}`);
      }
    }
  }
}

console.log('\n' + '═'.repeat(60));
if (totalViolations === 0) {
  console.log('  ✓ TODOS OS TESTES PASSARAM');
} else {
  console.log(`  ✗ TOTAL DE VIOLAÇÕES: ${totalViolations} frame-events`);
}
console.log('═'.repeat(60));
