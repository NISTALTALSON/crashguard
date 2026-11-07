# Model Card: CrashGuard v0.1

## Model details
- **Type:** MLP classifier (21 inputs, hidden 64-32-16 ReLU, sigmoid output), 88 KB JSON, plus a fixed trigger gate and hand-built features.
- **Task:** given a 2.56 s, 50 Hz window of accelerometer + gyroscope data around a high-g impact, plus optional GPS speed context, output p(vehicle/bike/pedestrian crash).
- **Version:** 0.1.0 (research preview). **License:** MIT. **Author:** Nistal (NISTALTALSON).
- **Reproduce:** `ml/train.py` regenerates the model, the report and all port artefacts.

## Intended use
Research, prototypes and open-source projects that need a starting point for sensor-based crash detection (two-wheelers, cars, bicycles, pedestrians) on phones, watches, helmets or handlebar units, **always with a human-cancel step**.

## Out of scope
- Use as a certified or sole safety system, or any medical/insurance/legal decision.
- Sensors that are not worn/mounted on a person or vehicle, or devices sampling below ~50 Hz.
- Impacts that never reach 3.5 g at the sensor (the trigger gate will not fire).

## Training data
| Source | Role | Real? |
|---|---|---|
| UCI HAR (30 volunteers, waist phone, 50 Hz accel+gyro, 7.3 h) | real sensor noise / body-motion texture; measures natural trigger rate | **real** |
| Physics-based simulator (`ml/simulate.py`): 23 scenario types, 23,000 events | crash and hard-negative signals | **simulated** |

- 9 crash scenarios (car frontal/side, rollover, rickshaw rollover, motorcycle high-side/low-side, scooter fall, bicycle crash, pedestrian hit) and 14 non-crash scenarios (phone drop, drop in vehicle, pothole, door slam, jump landing, roller coaster, sustained-g ride, hand slam, thrown on seat, parking bump, sports impact, bike bump, train jolt, motorcycle speed bump).
- Crash pulses follow half-sine crash-pulse physics (peak ~ pi/2 * dV / (g * T)). The simulator also models phone accelerometer saturation (±8/±16 g), tumbling (gravity rotates with the device), sensor noise and 50 Hz peak-hold decimation.
- GPS missing in 12% of samples to teach the model to cope without it.
- **No real crash data was used.** Parameters are my assumptions from published crash-pulse physics, not field measurements.

## Evaluation (simulated test events passing the trigger)
| Protocol | Crash recall | False-alarm rate | AUC |
|---|---|---|---|
| Scenario-held-out 6-fold (test scenario types never seen in training) | 93.4% | 1.00% | 0.9934 |
| Random split (optimistic) | 97.2% | 0.12% | n/a |

Per-scenario numbers: [`ml/REPORT.md`](ml/REPORT.md). The decision threshold (0.859) was set for <= 1% false alarms on the held-out predictions. Real-data check: 0 trigger events in 10,299 real HAR windows (7.3 h).

## Limitations and known failure modes
- **Simulation gap.** Real crashes will differ from the simulator; real-world recall and false-alarm rates are unknown and may be considerably worse.
- Weakest held-out scenarios: pedestrian hit (71% recall), frontal car crash (89%).
- Ambiguous by nature: a tackled athlete or a low-speed cycling fall can look like a scooter fall; parking taps below ~2.5 m/s are treated as non-crash.
- Depends on GPS speed for its best performance; accuracy without it is lower.
- Not tested on: real watches, helmets, e-scooters, non-Indian road conditions, or sensor mounts other than those simulated.
- Latency: a decision needs ~5 s after impact (to see the vehicle's speed settle).

## Ethical considerations
- **False alarms** waste emergency resources; **missed detections** can cost lives. Keep a cancel step, publish your own measured rates, and test before shipping.
- Crash-adjacent data is sensitive (location, health). The contribution format deliberately excludes location and identity.
- Do not stage dangerous events to collect data.

## How to cite
See [CITATION.cff](CITATION.cff).
