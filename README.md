# CrashGuard

**An open, tiny (88 KB) crash-detection model for motion sensors: phone, watch, handlebar or helmet. Take it, port it, improve it, build whatever you want on top.**

[![CI](https://github.com/NISTALTALSON/crashguard/actions/workflows/ci.yml/badge.svg)](https://github.com/NISTALTALSON/crashguard/actions)
![license](https://img.shields.io/badge/code%20%26%20weights-MIT-blue)
![status](https://img.shields.io/badge/status-v0.1%20research%20preview-orange)

This repo is a **model and a spec**, not an app or a product. It gives you:

- 📦 a trained classifier (`crash_model.json`, plain JSON weights, no ML framework needed to run it)
- 🧮 reference code in **Python**, **JavaScript** and **Kotlin** that all produce identical outputs
- 🧪 the simulator and training pipeline, so you can retrain or extend it
- 📐 a language-neutral [spec](docs/SPEC.md) so anyone can port it to Swift, Dart, Rust, C for microcontrollers, etc.
- 🔌 two *example* integrations (Android + Wear OS app, escalation backend) showing one way to use it

> ⚠️ **Research preview. Not a certified safety device.** The model is trained on *simulated* crashes layered on real sensor noise because no public dataset of real phone-sensor crashes exists. Read the [Model Card](MODEL_CARD.md) before using it in anything that matters. The best way to improve it is [contributing real data](CONTRIBUTING.md).

## Use it in 10 lines

```bash
pip install git+https://github.com/NISTALTALSON/crashguard
```
```python
from crashguard import Model, CrashDetector

model = Model.load()                              # bundled 88 KB model
detector = CrashDetector(model, on_evaluated=lambda e: print(
    f"impact! p(crash)={e.probability:.2f} peak={e.peak_g:.1f}g crash={e.positive}"))

# feed your sensor stream (any rate >= ~100 Hz works; it decimates to 50 Hz internally)
detector.on_gyroscope(gx, gy, gz)                 # rad/s
detector.on_accelerometer(t, ax, ay, az)          # m/s^2 incl. gravity, t in seconds
detector.on_speed(t, gps_speed_mps)               # optional, but it helps a lot
detector.tick(t)                                  # ~1 Hz
```
Or classify a single pre-cut window: `model.predict(acc_128x3_in_g, gyr_128x3, v_pre, v_post, gps_ok)`.

JavaScript (browser, React Native, Node, Raspberry Pi): see [`js/`](js). Kotlin / Android / Wear OS: see [`examples/android`](examples/android).

## How it works

```
sensors ──▶ peak-hold 50 Hz ──▶ TRIGGER |a| ≥ 3.5 g ──▶ 2.56 s window + GPS speed context ──▶ 21 features ──▶ MLP ──▶ p(crash)
```

1. **Trigger gate.** Everyday life almost never reaches 3.5 g: on 7.3 h of real activity data it fired **0 times**.
2. **Window.** 2.56 s around the impact, plus GPS speed in the 6 s before and 3 to 5 s after (did the vehicle actually stop?).
3. **Features.** 21 hand-built, orientation-independent features: peak, jerk, free-fall before impact, bounce count, rotation, post-impact stillness, speed drop, and so on ([full list](docs/SPEC.md#features)).
4. **Classifier.** A small MLP (64-32-16) outputs a crash probability. A threshold (0.859 in v0.1) turns it into a decision.

The classifier is trained to tell a crash from the things that fool naive detectors: **dropped phone, pothole, speed bump, door slam, roller coaster, sports impact, train jolt, parking tap**. Scenarios include cars, rollovers, motorcycles (high-side and low-side), scooters, bicycles, auto-rickshaws and pedestrian hits.

## Honest accuracy

Full details in [`ml/REPORT.md`](ml/REPORT.md) and the [Model Card](MODEL_CARD.md).

| Test | Crash recall | False alarms |
|---|---|---|
| **Scenario-held-out** (test scenarios never seen in training), 6-fold | **93.4%** | **1.0%** |
| Random split (same scenarios in train and test, optimistic) | 97.2% | 0.12% |
| Real everyday activity, 7.3 h (UCI HAR) | n/a | **0 trigger events** |

These are **simulated** crashes, so they show the model separates scenario families under my physics assumptions. They are **not** a real-world accuracy claim. Weakest cases: pedestrian hits (71%) and frontal car crashes (89%) when held out. Many phones saturate at ±8 g or ±16 g; the simulator models that.

## Repo map

| Path | What |
|---|---|
| [`crashguard/`](crashguard) | pip-installable Python package: features, model, streaming detector |
| [`js/`](js) | dependency-free JS port (`npm test` checks parity with Python) |
| [`ml/`](ml) | data fetch, physics simulator, training, evaluation, exported model + parity vectors |
| [`docs/SPEC.md`](docs/SPEC.md) | exact algorithm spec for porting |
| [`docs/DATA_FORMAT.md`](docs/DATA_FORMAT.md) | event format for contributing real data |
| [`examples/android`](examples/android) | example Android + Wear OS app (Kotlin; **not yet compiled or device-tested**) |
| [`examples/backend`](examples/backend) | example FastAPI contact-escalation service (6 tests pass) |

## Retrain / extend

```bash
pip install -e . scikit-learn pandas scipy
cd ml && python fetch_data.py && python train.py   # ~20 min, rewrites model + REPORT.md + exports for every port
```
Add a scenario in `ml/simulate.py`, retrain, and the report shows how it generalises.

## Contribute

The most valuable thing is **real data** (safe, consented, anonymised) in the [standard format](docs/DATA_FORMAT.md). Also welcome: ports (Swift, Dart, Rust, C), better scenarios, field evaluations. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Safety and legal

- Not a certified safety or medical device. No warranty (MIT).
- Never test with real emergency calls. Check your local rules before automating them.
- If you build a product on this, you own its false-alarm and missed-detection risk. Test it, keep a human-cancel step, and don't make it someone's only safety measure.

## Credits and license

Code and model weights: **MIT**. Sensor texture comes from the UCI HAR dataset (CC BY 4.0): Anguita, Ghio, Oneto, Parra, Reyes-Ortiz, *A Public Domain Dataset for Human Activity Recognition Using Smartphones*, ESANN 2013. If you use CrashGuard, see [CITATION.cff](CITATION.cff).
