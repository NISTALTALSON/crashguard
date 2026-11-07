"""Physics-based crash / hard-negative event simulator layered on REAL sensor texture.

Why simulated: no public labelled dataset of smartphone sensor traces from real
vehicle crashes exists. So we (1) take real UCI HAR body-motion + gyro noise as
the sensor texture, (2) simulate the kinematics of each scenario at 200 Hz,
(3) push it through a rigid-body model (gravity vector rotates with the tumbling
phone), (4) emulate a real phone sensor: +-8 g / +-16 g saturation, noise, and
50 Hz peak-hold decimation, exactly like the Android pipeline does.
Crash pulse magnitudes follow published half-sine crash-pulse physics
(peak ~ (pi/2) * dV / (g * T)).  Numbers are assumptions, not field data:
results measure separability under these assumptions only.
"""
import numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation

from features import extract, N

RATE, DT = 200, 1.0 / 200
L = 4 * N                  # 512 internal samples == 128 @ 50 Hz
I0 = 160                   # impact index (== sample 40 @ 50 Hz)
TRIGGER_G = 3.5
Z = np.array([0.0, 0.0, 1.0])

_HAR = None


def _load_har():
    global _HAR
    if _HAR is not None:
        return _HAR
    root = next((Path(__file__).parent / "data").rglob("Inertial Signals")).parent.parent
    acc, gyr = [], []
    for split in ("train", "test"):
        base = root / split / "Inertial Signals"
        a = np.stack([np.loadtxt(base / f"body_acc_{ax}_{split}.txt") for ax in "xyz"], -1)
        g = np.stack([np.loadtxt(base / f"body_gyro_{ax}_{split}.txt") for ax in "xyz"], -1)
        acc.append(a); gyr.append(g)
    _HAR = (np.concatenate(acc), np.concatenate(gyr))
    return _HAR


def total_acc_windows():
    """Real total_acc windows (g) for measuring the natural trigger rate."""
    root = next((Path(__file__).parent / "data").rglob("Inertial Signals")).parent.parent
    out = []
    for split in ("train", "test"):
        base = root / split / "Inertial Signals"
        out.append(np.stack([np.loadtxt(base / f"total_acc_{ax}_{split}.txt") for ax in "xyz"], -1))
    return np.concatenate(out)


def rdir(rng, horizontal=False):
    v = rng.normal(size=3)
    if horizontal:
        v[2] = 0
    return v / np.linalg.norm(v)


def pulse(a, i0, dur, peak, d):
    n = max(2, int(round(dur * RATE)))
    j1 = min(L, i0 + n)
    if i0 >= L or j1 <= i0:
        return
    s = np.sin(np.pi * (np.arange(n) + 0.5) / n)[: j1 - i0]
    a[i0:j1] += peak * s[:, None] * d


def spin(w, i0, dur, rate, rng):
    n = int(dur * RATE)
    j1 = min(L, i0 + n)
    if i0 >= L or j1 <= i0:
        return
    env = np.linspace(1.0, 0.2, n)[: j1 - i0]
    w[i0:j1] += rate * env[:, None] * rdir(rng)


def jit(rng):
    return I0 + int(rng.integers(-8, 9))


# ---------------- crash scenarios (label 1) ----------------
def car_crash(rng, side=False):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    dv = rng.uniform(6, 20) if side else rng.uniform(6, 30)
    T = rng.uniform(0.07, 0.15)
    peak = min(60.0, np.pi / 2 * dv / (9.81 * T))
    d, i0 = rdir(rng, True), jit(rng)
    if rng.random() < 0.5:
        a[max(0, i0 - int(rng.uniform(0.5, 1.5) * RATE)):i0] += rng.uniform(0.3, 0.8) * d
    pulse(a, i0, T, peak, d)
    pulse(a, i0 + int(T * RATE), 0.05, 0.2 * peak, -d)
    spin(w, i0, rng.uniform(1, 2), rng.uniform(2, 6) if side else rng.uniform(0, 3), rng)
    partial = rng.random() < 0.3
    vpre = dv * rng.uniform(0.9, 1.2) + (rng.uniform(0, 10) if partial else 0)
    vpost = max(0.0, vpre - 0.8 * dv) if partial else rng.uniform(0, 2)
    return a, w, dict(vpre=vpre, vpost=vpost, vehicle=True)


def rollover(rng, vmin=10, vmax=30):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0 = jit(rng)
    for k in range(int(rng.integers(3, 7))):
        pulse(a, i0 + int(k * rng.uniform(0.1, 0.35) * RATE), rng.uniform(0.03, 0.08),
              rng.uniform(3.5, 10), rdir(rng))
    spin(w, i0 - 10, rng.uniform(1.5, 2.5), rng.uniform(2, 8), rng)
    return a, w, dict(vpre=rng.uniform(vmin, vmax), vpost=rng.uniform(0, 1), vehicle=True)


def moto_highside(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0 = jit(rng)
    pulse(a, i0, rng.uniform(0.015, 0.04), rng.uniform(10, 35), rdir(rng))
    t = i0
    for _ in range(int(rng.integers(2, 6))):
        t += int(rng.uniform(0.1, 0.4) * RATE)
        pulse(a, t, rng.uniform(0.02, 0.06), rng.uniform(4, 15), rdir(rng))
    spin(w, i0, rng.uniform(1, 2), rng.uniform(6, 20), rng)
    return a, w, dict(vpre=rng.uniform(8, 25), vpost=rng.uniform(0, 2), vehicle=False)


def moto_lowside(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0 = jit(rng)
    d = rdir(rng, True)
    pulse(a, i0, rng.uniform(0.03, 0.08), rng.uniform(3.5, 9), rdir(rng))
    n = int(rng.uniform(1, 3) * RATE)
    a[i0:i0 + n] += rng.uniform(0.5, 0.9) * d
    spin(w, i0, rng.uniform(1, 2), rng.uniform(2, 8), rng)
    return a, w, dict(vpre=rng.uniform(5, 16), vpost=rng.uniform(0, 1), vehicle=False)


def scooter_fall(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0 = jit(rng)
    pulse(a, i0, rng.uniform(0.03, 0.07), rng.uniform(3.8, 8), rdir(rng))
    spin(w, i0, rng.uniform(0.5, 1.5), rng.uniform(3, 10), rng)
    return a, w, dict(vpre=rng.uniform(3, 8), vpost=rng.uniform(0, 0.8), vehicle=False)


# ---------------- hard negatives (label 0) ----------------
def phone_drop(rng, in_vehicle=False):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    t_fall = np.sqrt(2 * rng.uniform(0.3, 2.0) / 9.81)
    i0 = jit(rng)
    a[max(0, i0 - int(t_fall * RATE)):i0] = -Z * rng.uniform(0.9, 1.0)
    spin(w, max(0, i0 - int(t_fall * RATE)), t_fall, rng.uniform(3, 20), rng)
    pulse(a, i0, rng.uniform(0.002, 0.008), rng.uniform(10, 80), Z)
    t, amp = i0, rng.uniform(5, 20)
    for _ in range(int(rng.integers(0, 4))):
        t += int(rng.uniform(0.03, 0.15) * RATE)
        amp *= rng.uniform(0.3, 0.6)
        pulse(a, t, 0.004, amp, Z)
    v = rng.uniform(5, 25) if in_vehicle else rng.uniform(0, 1.5)
    return a, w, dict(vpre=v, vpost=v * (rng.uniform(0.85, 1.0) if in_vehicle else 1),
                      vehicle=in_vehicle)


def pothole(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0 = jit(rng)
    if rng.random() < 0.4:
        a[i0 - int(rng.uniform(0.5, 1.5) * RATE):i0] += rng.uniform(0.3, 0.9) * rdir(rng, True)
    p = rng.uniform(3.5, 10)
    pulse(a, i0, rng.uniform(0.03, 0.09), p, Z)
    pulse(a, i0 + int(0.08 * RATE), 0.04, 0.5 * p, -Z)
    spin(w, i0, 0.3, rng.uniform(0, 2), rng)
    v = rng.uniform(4, 25)
    return a, w, dict(vpre=v, vpost=v * rng.uniform(0.8, 1.0), vehicle=True)


def door_slam(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    pulse(a, jit(rng), rng.uniform(0.01, 0.03), rng.uniform(3.5, 8), rdir(rng, True))
    spin(w, I0, 0.3, rng.uniform(0, 1.5), rng)
    v = rng.choice([0.0, rng.uniform(1, 15)])
    return a, w, dict(vpre=v, vpost=v, vehicle=v > 0)


def jump_landing(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    pulse(a, jit(rng), rng.uniform(0.04, 0.1), rng.uniform(3.6, 6), Z)
    spin(w, I0 - 20, 0.5, rng.uniform(1, 6), rng)
    v = rng.uniform(0, 3)
    return a, w, dict(vpre=v, vpost=v, vehicle=False)


def roller_coaster(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0, n = jit(rng) - 40, int(rng.uniform(1, 2) * RATE)
    m = min(n, L - i0)
    a[i0:i0 + m] += rng.uniform(3.0, 4.8) * rdir(rng) * np.hanning(n)[:m, None]
    spin(w, i0, 1.5, rng.uniform(1, 3), rng)
    v = rng.uniform(5, 20)
    return a, w, dict(vpre=v, vpost=v * rng.uniform(0.8, 1.1), vehicle=True)


def hand_slam(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    pulse(a, jit(rng), rng.uniform(0.005, 0.012), rng.uniform(4, 20), rdir(rng))
    spin(w, I0, 0.2, rng.uniform(0, 2), rng)
    v = rng.uniform(0, 1)
    return a, w, dict(vpre=v, vpost=v, vehicle=False)


def thrown_on_seat(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0, tf = jit(rng), rng.uniform(0.1, 0.3)
    a[i0 - int(tf * RATE):i0] = -Z * 0.95
    pulse(a, i0, rng.uniform(0.02, 0.06), rng.uniform(3.5, 10), Z)
    spin(w, i0 - int(tf * RATE), tf, rng.uniform(2, 10), rng)
    v = rng.uniform(0, 25)
    return a, w, dict(vpre=v, vpost=v * rng.uniform(0.9, 1.0), vehicle=v > 1)


def parking_bump(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    pulse(a, jit(rng), rng.uniform(0.08, 0.15), rng.uniform(3.2, 5), rdir(rng, True))
    return a, w, dict(vpre=rng.uniform(0.3, 2.5), vpost=rng.uniform(0, 0.5), vehicle=True)


def sustained_ride(rng):
    """Fairground / aggressive-cornering: 2.6-4.6 g held for seconds, vehicle keeps moving."""
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0, n = jit(rng) - 60, int(rng.uniform(1.5, 5) * RATE)
    m = min(n, L - i0)
    a[i0:i0 + m] += rng.uniform(2.6, 4.6) * rdir(rng) * (np.hanning(n)[:m, None] ** 0.5)
    spin(w, i0, rng.uniform(1, 3), rng.uniform(0.5, 3), rng)
    v = rng.uniform(3, 25)
    return a, w, dict(vpre=v, vpost=v * rng.uniform(0.7, 1.1), vehicle=True)


def sports_impact(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0 = jit(rng)
    for k in range(int(rng.integers(1, 4))):
        pulse(a, i0 + int(k * rng.uniform(0.05, 0.3) * RATE), rng.uniform(0.01, 0.05),
              rng.uniform(3.5, 15), rdir(rng))
    spin(w, i0, 0.4, rng.uniform(1, 10), rng)
    v = rng.uniform(0, 6)
    return a, w, dict(vpre=v, vpost=v * rng.uniform(0.5, 1.1), vehicle=False)


def bike_bump(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0 = jit(rng)
    pulse(a, i0, rng.uniform(0.03, 0.08), rng.uniform(3.5, 8), Z)
    pulse(a, i0 + int(rng.uniform(0.1, 0.3) * RATE), 0.04, rng.uniform(2, 6), Z)
    spin(w, i0, 0.3, rng.uniform(0.5, 3), rng)
    v = rng.uniform(3, 9)
    return a, w, dict(vpre=v, vpost=v * rng.uniform(0.7, 1.0), vehicle=False)


def train_jolt(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    pulse(a, jit(rng), rng.uniform(0.1, 0.25), rng.uniform(3.5, 5), rdir(rng, True))
    v = rng.uniform(8, 30)
    return a, w, dict(vpre=v, vpost=v * rng.uniform(0.9, 1.05), vehicle=True)


def moto_speed_bump(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0 = jit(rng)
    pulse(a, i0, rng.uniform(0.03, 0.07), rng.uniform(3.5, 7), Z)
    pulse(a, i0 + int(rng.uniform(0.15, 0.3) * RATE), 0.05, rng.uniform(3, 6), Z)
    spin(w, i0, 0.4, rng.uniform(0.5, 3), rng)
    v = rng.uniform(3, 12)
    return a, w, dict(vpre=v, vpost=v * rng.uniform(0.6, 1.0), vehicle=False)


def bicycle_crash(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0 = jit(rng)
    pulse(a, i0, rng.uniform(0.03, 0.08), rng.uniform(3.6, 9), rdir(rng))
    n = int(rng.uniform(0.5, 1.5) * RATE)
    a[i0:i0 + n] += rng.uniform(0.3, 0.6) * rdir(rng, True)
    spin(w, i0, rng.uniform(0.5, 1.5), rng.uniform(3, 12), rng)
    return a, w, dict(vpre=rng.uniform(3, 10), vpost=rng.uniform(0, 1), vehicle=False)


def pedestrian_hit(rng):
    a, w = np.zeros((L, 3)), np.zeros((L, 3))
    i0 = jit(rng)
    pulse(a, i0, rng.uniform(0.02, 0.06), rng.uniform(4, 20), rdir(rng, True))
    pulse(a, i0 + int(rng.uniform(0.2, 0.6) * RATE), rng.uniform(0.02, 0.06), rng.uniform(4, 10), rdir(rng))
    spin(w, i0, rng.uniform(1, 2), rng.uniform(3, 12), rng)
    return a, w, dict(vpre=rng.uniform(0.5, 2), vpost=rng.uniform(0, 0.5), vehicle=False)


def rickshaw_rollover(rng):
    return rollover(rng, 4, 14)


SCENARIOS = {
    # name: (fn, label)
    "sustained_ride": (sustained_ride, 0),
    "sports_impact": (sports_impact, 0),
    "bike_bump": (bike_bump, 0),
    "train_jolt": (train_jolt, 0),
    "moto_speed_bump": (moto_speed_bump, 0),
    "bicycle_crash": (bicycle_crash, 1),
    "pedestrian_hit": (pedestrian_hit, 1),
    "rickshaw_rollover": (rickshaw_rollover, 1),
    "car_frontal": (lambda r: car_crash(r, False), 1),
    "car_side": (lambda r: car_crash(r, True), 1),
    "rollover": (rollover, 1),
    "moto_highside": (moto_highside, 1),
    "moto_lowside": (moto_lowside, 1),
    "scooter_fall": (scooter_fall, 1),
    "phone_drop": (lambda r: phone_drop(r, False), 0),
    "phone_drop_in_vehicle": (lambda r: phone_drop(r, True), 0),
    "pothole": (pothole, 0),
    "door_slam": (door_slam, 0),
    "jump_landing": (jump_landing, 0),
    "roller_coaster": (roller_coaster, 0),
    "hand_slam": (hand_slam, 0),
    "thrown_on_seat": (thrown_on_seat, 0),
    "parking_bump": (parking_bump, 0),
}


def _rotations(omega, R0):
    R = np.empty((L, 3, 3))
    cur = R0
    for i in range(L):
        R[i] = cur
        w = omega[i] * DT
        th = np.linalg.norm(w)
        if th > 1e-9:
            k = w / th
            K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
            cur = cur @ (np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * (K @ K))
    return R


def render(name, rng):
    """Simulate one event and return (acc50 [128,3], gyr50 [128,3], meta)."""
    fn, label = SCENARIOS[name]
    a_kin, omega, meta = fn(rng)
    har_a, har_g = _load_har()
    k = int(rng.integers(len(har_a)))
    a_kin = a_kin + np.repeat(har_a[k], 4, axis=0) * rng.uniform(0.3, 1.5)
    omega = omega + np.repeat(har_g[k], 4, axis=0) * rng.uniform(0.3, 1.5)
    if meta["vehicle"]:
        vib = np.apply_along_axis(lambda x: np.convolve(x, np.ones(5) / 5, "same"), 0,
                                  rng.normal(size=(L, 3)))
        a_kin += vib * rng.uniform(0.03, 0.12) * 3 * np.array([0.6, 0.6, 1.0])
    R = _rotations(omega, Rotation.random(random_state=int(rng.integers(2**31))).as_matrix())
    f = np.einsum("lji,lj->li", R, a_kin + Z)
    rng_g = 16.0 if rng.random() < 0.6 else 8.0           # phone accelerometer range
    f = np.clip(f + rng.normal(0, 0.012, f.shape), -rng_g, rng_g)
    gyr = np.clip(omega + rng.normal(0, 0.01, omega.shape), -34.9, 34.9)  # ~2000 dps
    idx = np.arange(N)[:, None] * 4 + np.arange(4)[None, :]               # peak-hold decimation
    pick = idx[np.arange(N), np.argmax(np.linalg.norm(f, axis=1)[idx], axis=1)]
    gps_ok = int(rng.random() < 0.88)
    meta = dict(meta, label=label, name=name, gps_ok=gps_ok,
                vpre=max(0.0, meta["vpre"] + rng.normal(0, 0.6)),
                vpost=max(0.0, meta["vpost"] + rng.normal(0, 0.6)))
    return f[pick], gyr[pick], meta


def make_sample(args):
    name, seed = args
    rng = np.random.default_rng(seed)
    acc, gyr, m = render(name, rng)
    peak = float(np.linalg.norm(acc, axis=1).max())
    x = extract(acc, gyr, m["vpre"], m["vpost"], m["gps_ok"])
    return x, m["label"], name, peak >= TRIGGER_G


def build_dataset(per_scenario=900, seed=7, workers=None):
    from concurrent.futures import ProcessPoolExecutor
    jobs = [(n, seed * 1_000_003 + i * 131 + j) for i, n in enumerate(SCENARIOS)
            for j in range(per_scenario)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(make_sample, jobs, chunksize=64))
    X = np.stack([r[0] for r in res])
    y = np.array([r[1] for r in res])
    sc = np.array([r[2] for r in res])
    trig = np.array([r[3] for r in res])
    return X, y, sc, trig
