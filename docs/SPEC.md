# CrashGuard algorithm spec (v0.1)

Everything needed to port the model to another language. The Python, JS and Kotlin implementations all follow this document, and `ml/model/parity.json` contains test vectors (raw windows + expected features + expected probability) so you can prove your port is identical.

## 1. Inputs
- Accelerometer: **g units, gravity included**, 3 axes, any device orientation. (Android `TYPE_ACCELEROMETER` is m/s^2: divide by 9.80665.)
- Gyroscope: rad/s, 3 axes.
- Optional GPS speed, m/s, with timestamps.
- Raw rate >= ~100 Hz recommended (200 Hz used in development).

## 2. Peak-hold decimation to 50 Hz
Split time into 20 ms bins. Per bin keep the accelerometer sample with the **largest magnitude** (and the latest gyro reading at that moment). Peak-hold keeps short 5 to 20 ms impact spikes that averaging would erase.

## 3. Trigger
When MONITORING and a decimated sample has `|a| >= trigger_g` (3.5 g, from the model file) and cooldown has expired, remember the sample index `T` and start COLLECTING.

## 4. Window
Window = decimated samples `T-40 ... T+87` (128 samples = 2.56 s; clamp at buffer start). Freeze it when sample `T+87` arrives.

## 5. GPS context (evaluated at trigger time + 5 s)
- `v_pre`  = mean speed of fixes in `[T-6 s, T-0.33 s]`
- `v_post` = mean speed of fixes in `[T+3 s, T+5.2 s]`
- `gps_ok` = both exist. If not, all four speed features are 0.

## 6. Features
`acc`, `gyr` are `[128][3]`; `mag = |acc|`, `gm = |gyr|`; `pk = argmax(mag)` (first max); `FS = 50`. All std are population std.

| # | name | definition |
|---|---|---|
| 0 | peak_log | ln(1 + mag[pk]) |
| 1 | jerk_log | ln(1 + FS * max_i abs(mag[i] - mag[i-1])) |
| 2 | energy_log | ln(1 + sum(max(mag - 2, 0)) / FS) |
| 3 | freefall_frac | fraction of the up to 25 samples before `pk` with mag < 0.5 (0 if none) |
| 4 | n_impacts | local maxima with mag > 3, at least 5 samples apart (greedy, left to right) |
| 5 | width_ms | 1000/FS * count(mag > 0.5 * peak) |
| 6 | t_above3_ms | 1000/FS * count(mag > 3) |
| 7 | gyro_peak | max(gm) |
| 8 | gyro_post_mean | mean(gm[min(127, pk+5) ... 127]) |
| 9 | gyro_near_peak | max(gm[max(0,pk-15) ... min(127, pk+15)]) |
| 10 | orient_change_deg | degrees(acos(clip(dot(u0, u1), -1, 1))), u0 / u1 = unit vector of mean acc over first 15 / last 15 samples |
| 11 | post_std | std(mag[88..127]) |
| 12 | post_dev | abs(mean(mag[88..127]) - 1) |
| 13 | pre_std | std(mag[0..19]) |
| 14 | v_pre | v_pre if gps_ok else 0 |
| 15 | v_post | v_post if gps_ok else 0 |
| 16 | v_drop | v_pre - v_post (0 if no gps) |
| 17 | v_ratio | v_post / max(v_pre, 0.5) (0 if no gps) |
| 18 | gps_ok | 1 or 0 |
| 19 | above2_ms | 1000/FS * count(mag > 2) |
| 20 | still_frac | fraction of mag[88..127] with abs(mag - 1) < 0.08 |

## 7. Model
`x = (features - mean) / std`; for each layer `h = h @ W[l] + b[l]`, ReLU on all but the last, sigmoid on the last. `W[l]` has shape `[in][out]`. `crash = p >= threshold`. All constants are in `crash_model.json` (`mean`, `std`, `weights`, `biases`, `threshold`, `trigger_g`).

## 8. After a positive
The model only says "this looks like a crash". What you do next (countdown, haptics, alerts) is yours. Keep a cancel step. State machine reference: `crashguard/detector.py`.

## 9. Porting checklist
1. Implement features, then check them against `parity.json` (`features`, tolerance 1e-3).
2. Implement the MLP, then check `probability` (tolerance 1e-3).
3. Implement the streaming layer (sections 2 to 5) and replay `parity.json` windows through it.
