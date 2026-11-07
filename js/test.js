'use strict';
const assert = require('assert');
const fs = require('fs');
const { extract, Model, CrashDetector, COUNT } = require('./crashguard-core');

const modelJson = JSON.parse(fs.readFileSync(__dirname + '/crash_model.json', 'utf8'));
const model = new Model(modelJson);
const parity = JSON.parse(fs.readFileSync(__dirname + '/parity.json', 'utf8'));
const G = 9.80665;
let failures = 0;
const ok = (name, fn) => { try { fn(); console.log('ok   -', name); } catch (e) { failures++; console.log('FAIL -', name, '\n      ', e.message); } };

for (const c of parity) {
  ok(`parity ${c.name}`, () => {
    const f = extract(c.acc, c.gyr, c.v_pre, c.v_post, c.gps_ok === 1);
    assert.strictEqual(f.length, COUNT);
    f.forEach((v, i) => assert(Math.abs(v - c.features[i]) <= 1e-3 + 1e-3 * Math.abs(c.features[i]), `feature ${i}: ${v} vs ${c.features[i]}`));
    assert(Math.abs(model.predict(f) - c.probability) < 1e-3, 'probability mismatch');
  });
}

// End-to-end: replay each simulated event through the streaming detector.
for (const c of parity) {
  ok(`detector replay ${c.name}`, () => {
    let res = null;
    const d = new CrashDetector(model, (e) => { res = e; });
    const t0 = 10000;
    let trigT = null;
    c.acc.forEach((a, k) => {
      const t = t0 + k * 20;
      d.onGyroscope(...c.gyr[k]);
      d.onAccelerometer(t, a[0] * G, a[1] * G, a[2] * G);
      if (trigT === null && Math.hypot(...a) >= model.triggerG) trigT = t;
    });
    if (c.gps_ok) { d.onSpeed(trigT - 2000, c.v_pre); d.onSpeed(trigT + 4000, c.v_post); }
    for (let k = 128; k < 128 + 260; k++) { d.onGyroscope(0, 0, 0); d.onAccelerometer(t0 + k * 20, 0, 0, G); }
    d.tick(t0 + 400 * 20);
    assert(res, 'detector never evaluated the event');
    const py = c.probability;
    if (Math.abs(py - model.threshold) > 0.2) assert.strictEqual(res.positive, py >= model.threshold, `p=${res.probability.toFixed(3)} python=${py.toFixed(3)}`);
  });
}
if (failures) { console.log(`${failures} failed`); process.exit(1); }
console.log('all passed');
