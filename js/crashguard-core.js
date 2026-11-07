/**
 * CrashGuard core in plain JavaScript (no dependencies).
 * Same features + model + detector as ml/features.py and android/core (Kotlin), so it runs
 * anywhere JS runs: browsers (DeviceMotion), React Native / Capacitor (iOS + Android),
 * Node on a Raspberry Pi, Electron.  `npm test` checks bit-level parity with Python.
 */
'use strict';

const FS = 50, N = 128, COUNT = 21, G = 9.80665;
const norm3 = (a) => Math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);
const mean = (x, a, b) => { let s = 0; for (let i = a; i < b; i++) s += x[i]; return s / (b - a); };
const std = (x, a, b) => {
  const m = mean(x, a, b); let s = 0;
  for (let i = a; i < b; i++) s += (x[i] - m) ** 2;
  return Math.sqrt(s / (b - a));
};

function countImpacts(mag, thr = 3.0, minGap = 5) {
  let count = 0, last = -1e9;
  for (let i = 1; i < mag.length - 1; i++) {
    if (mag[i] > thr && mag[i] >= mag[i - 1] && mag[i] > mag[i + 1] && i - last >= minGap) { count++; last = i; }
  }
  return count;
}

function unitMean(rows, a, b) {
  const m = [0, 0, 0];
  for (let i = a; i < b; i++) for (let k = 0; k < 3; k++) m[k] += rows[i][k];
  for (let k = 0; k < 3; k++) m[k] /= (b - a);
  const n = norm3(m);
  return n > 1e-9 ? m.map((v) => v / n) : m;
}

/** acc in g (gravity included), gyr in rad/s, both [128][3] @ 50 Hz. */
function extract(acc, gyr, vPre = 0, vPost = 0, gpsOk = false) {
  if (acc.length !== N || gyr.length !== N) throw new Error(`window must have ${N} samples`);
  const mag = acc.map(norm3), gm = gyr.map(norm3);
  let pk = 0;
  for (let i = 1; i < N; i++) if (mag[i] > mag[pk]) pk = i;
  const peak = mag[pk];
  let jerk = 0;
  for (let i = 1; i < N; i++) jerk = Math.max(jerk, Math.abs(mag[i] - mag[i - 1]));
  jerk *= FS;
  let energy = 0;
  for (const m of mag) energy += Math.max(m - 2, 0);
  energy /= FS;
  const pre0 = Math.max(0, pk - 25);
  let freefall = 0;
  if (pk > pre0) { let c = 0; for (let i = pre0; i < pk; i++) if (mag[i] < 0.5) c++; freefall = c / (pk - pre0); }
  const widthMs = mag.filter((m) => m > 0.5 * peak).length * 1000 / FS;
  const above3 = mag.filter((m) => m > 3).length * 1000 / FS;
  const gyroPost = mean(gm, Math.min(N - 1, pk + 5), N);
  let near = 0;
  for (let i = Math.max(0, pk - 15); i < Math.min(N, pk + 16); i++) near = Math.max(near, gm[i]);
  const g0 = unitMean(acc, 0, 15), g1 = unitMean(acc, N - 15, N);
  const cos = Math.min(1, Math.max(-1, g0[0] * g1[0] + g0[1] * g1[1] + g0[2] * g1[2]));
  const orient = Math.acos(cos) * 180 / Math.PI;
  const postStd = std(mag, N - 40, N);
  const postDev = Math.abs(mean(mag, N - 40, N) - 1);
  const preStd = std(mag, 0, 20);
  const above2 = mag.filter((m) => m > 2).length * 1000 / FS;
  let still = 0;
  for (let i = N - 40; i < N; i++) if (Math.abs(mag[i] - 1) < 0.08) still++;
  let vp = 0, vq = 0, drop = 0, ratio = 0;
  if (gpsOk) { vp = vPre; vq = vPost; drop = vp - vq; ratio = vq / Math.max(vp, 0.5); }
  return [
    Math.log1p(peak), Math.log1p(jerk), Math.log1p(energy), freefall, countImpacts(mag), widthMs, above3,
    Math.max(...gm), gyroPost, near, orient, postStd, postDev, preStd,
    vp, vq, drop, ratio, gpsOk ? 1 : 0, above2, still / 40,
  ];
}

class Model {
  constructor(j) { Object.assign(this, { triggerG: j.trigger_g, threshold: j.threshold, mean: j.mean, std: j.std, W: j.weights, b: j.biases }); }
  predict(x) {
    let h = x.map((v, i) => (v - this.mean[i]) / this.std[i]);
    for (let l = 0; l < this.W.length; l++) {
      const W = this.W[l], b = this.b[l];
      const out = b.map((bj, j) => { let s = bj; for (let i = 0; i < h.length; i++) s += h[i] * W[i][j]; return s; });
      h = l < this.W.length - 1 ? out.map((v) => Math.max(v, 0)) : out;
    }
    return 1 / (1 + Math.exp(-h[0]));
  }
}

/** Peak-hold decimation to 50 Hz (what the training simulator assumes). Times in milliseconds. */
class Decimator {
  constructor(emit) { this.emit = emit; this.bin = null; this.best = null; this.bestMag = -1; this.gyro = [0, 0, 0]; }
  onGyro(x, y, z) { this.gyro = [x, y, z]; }
  onAccel(tMs, ax, ay, az) {
    const b = Math.floor(tMs / 20);
    if (b !== this.bin) { if (this.best) this.emit(this.best); this.bin = b; this.bestMag = -1; this.best = null; }
    const m = Math.hypot(ax, ay, az);
    if (m > this.bestMag) { this.bestMag = m; this.best = { t: tMs, acc: [ax, ay, az], gyr: this.gyro }; }
  }
}

/** MONITORING -> COLLECTING (trigger + 5 s) -> ALERTING (until reset()). Times in ms. */
class CrashDetector {
  constructor(model, onEvaluated) {
    this.model = model; this.onEvaluated = onEvaluated; this.state = 'MONITORING';
    this.buf = []; this.seqBase = 0; this.trigSeq = -1; this.trigT = 0; this.cooldown = 0;
    this.frozen = null; this.speeds = []; this.dec = new Decimator((s) => this._onSample(s));
  }
  /** m/s^2 accelerometer values (DeviceMotionEvent.accelerationIncludingGravity works; sign irrelevant). */
  onAccelerometer(tMs, ax, ay, az) { this.dec.onAccel(tMs, ax / G, ay / G, az / G); }
  onGyroscope(x, y, z) { this.dec.onGyro(x, y, z); }
  onSpeed(tMs, mps) { this.speeds.push([tMs, mps]); if (this.speeds.length > 40) this.speeds.shift(); }
  reset(nowMs) { this.state = 'MONITORING'; this.trigSeq = -1; this.frozen = null; this.cooldown = nowMs + 3000; }
  tick(nowMs) { this._maybeEvaluate(nowMs); }
  _onSample(s) {
    this.buf.push(s);
    if (this.buf.length > 600) { this.buf.splice(0, 200); this.seqBase += 200; }
    const seq = this.seqBase + this.buf.length - 1;
    if (this.state === 'MONITORING' && norm3(s.acc) >= this.model.triggerG && s.t >= this.cooldown) {
      this.state = 'COLLECTING'; this.trigSeq = seq; this.trigT = s.t; this.frozen = null;
    }
    if (this.state === 'COLLECTING' && !this.frozen && seq >= this.trigSeq + 87) this._freeze();
    this._maybeEvaluate(s.t);
  }
  _freeze() {
    const acc = [], gyr = [];
    for (let k = 0; k < N; k++) {
      const idx = Math.min(this.buf.length - 1, Math.max(0, this.trigSeq - 40 + k - this.seqBase));
      acc.push(this.buf[idx].acc.slice()); gyr.push(this.buf[idx].gyr.slice());
    }
    this.frozen = { acc, gyr };
  }
  _meanSpeed(a, b) { const v = this.speeds.filter(([t]) => t >= a && t <= b).map(([, s]) => s); return v.length ? v.reduce((x, y) => x + y) / v.length : null; }
  _maybeEvaluate(now) {
    if (this.state !== 'COLLECTING' || now < this.trigT + 5000) return;
    if (!this.frozen) this._freeze();
    const { acc, gyr } = this.frozen;
    const vp = this._meanSpeed(this.trigT - 6000, this.trigT - 333);
    const vq = this._meanSpeed(this.trigT + 3000, this.trigT + 5200);
    const gpsOk = vp !== null && vq !== null;
    const f = extract(acc, gyr, vp ?? 0, vq ?? 0, gpsOk);
    const p = this.model.predict(f), positive = p >= this.model.threshold;
    const peak = Math.max(...acc.map(norm3));
    if (positive) this.state = 'ALERTING'; else this.reset(now);
    this.trigSeq = -1; this.frozen = null;
    this.onEvaluated({ probability: p, positive, features: f, acc, gyr, vPre: vp ?? 0, vPost: vq ?? 0, gpsOk, peakG: peak, triggerT: this.trigT });
  }
}

module.exports = { extract, Model, Decimator, CrashDetector, FS, N, COUNT };
