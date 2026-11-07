"""Impact-window feature extraction. MUST stay bit-for-bit in sync with
android/core/.../Features.kt (parity is checked via exported test vectors).

Input: a 128-sample window at 50 Hz (2.56 s), impact ~sample 40.
  acc  (128,3) specific force in g (gravity included)
  gyr  (128,3) rad/s
  v_pre, v_post: GPS speed (m/s) before / after the impact; gps_ok 0/1
"""
import numpy as np

FS = 50.0
N = 128
FEATURES = [
    "peak_log", "jerk_log", "energy_log", "freefall_frac", "n_impacts",
    "width_ms", "t_above3_ms", "gyro_peak", "gyro_post_mean", "gyro_near_peak",
    "orient_change_deg", "post_std", "post_dev", "pre_std",
    "v_pre", "v_post", "v_drop", "v_ratio", "gps_ok",
    "above2_ms", "still_frac",
]


def _count_impacts(mag, thr=3.0, min_gap=5):
    count, last = 0, -10**9
    for i in range(1, len(mag) - 1):
        if mag[i] > thr and mag[i] >= mag[i - 1] and mag[i] > mag[i + 1] and i - last >= min_gap:
            count += 1
            last = i
    return count


def _unit_mean(a):
    m = a.mean(axis=0)
    n = np.linalg.norm(m)
    return m / n if n > 1e-9 else m


def extract(acc, gyr, v_pre=0.0, v_post=0.0, gps_ok=0):
    acc = np.asarray(acc, dtype=np.float64)
    gyr = np.asarray(gyr, dtype=np.float64)
    mag = np.linalg.norm(acc, axis=1)
    gm = np.linalg.norm(gyr, axis=1)
    pk = int(np.argmax(mag))
    peak = mag[pk]
    jerk = np.max(np.abs(np.diff(mag))) * FS
    energy = np.sum(np.clip(mag - 2.0, 0.0, None)) / FS
    pre = mag[max(0, pk - 25):pk]
    freefall = float(np.mean(pre < 0.5)) if len(pre) else 0.0
    width_ms = float(np.sum(mag > 0.5 * peak)) * 1000.0 / FS
    above3_ms = float(np.sum(mag > 3.0)) * 1000.0 / FS
    post = gm[min(N - 1, pk + 5):]
    gyro_post = float(post.mean()) if len(post) else 0.0
    near = gm[max(0, pk - 15):pk + 16]
    cosang = float(np.clip(np.dot(_unit_mean(acc[:15]), _unit_mean(acc[-15:])), -1.0, 1.0))
    orient = float(np.degrees(np.arccos(cosang)))
    tail = mag[-40:]
    post_std = float(tail.std())
    post_dev = float(abs(tail.mean() - 1.0))
    pre_std = float(mag[:20].std())
    above2_ms = float(np.sum(mag > 2.0)) * 1000.0 / FS
    still_frac = float(np.mean(np.abs(tail - 1.0) < 0.08))
    if gps_ok:
        vp, vq = float(v_pre), float(v_post)
        drop = vp - vq
        ratio = vq / max(vp, 0.5)
    else:
        vp = vq = drop = ratio = 0.0
    return np.array([
        np.log1p(peak), np.log1p(jerk), np.log1p(energy), freefall,
        float(_count_impacts(mag)), width_ms, above3_ms, float(gm.max()), gyro_post,
        float(near.max()), orient, post_std, post_dev, pre_std,
        vp, vq, drop, ratio, float(1 if gps_ok else 0),
        above2_ms, still_frac,
    ], dtype=np.float64)
