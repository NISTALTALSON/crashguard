"""Streaming crash detector (same logic as js/crashguard-core.js and the Kotlin core).

    det = CrashDetector(Model.load(), on_evaluated=print)
    det.on_gyroscope(gx, gy, gz)                    # rad/s, whenever you get it
    det.on_accelerometer(t_seconds, ax, ay, az)     # m/s^2 incl. gravity, any rate >= ~100 Hz
    det.on_speed(t_seconds, metres_per_second)      # optional GPS speed
    det.tick(t_seconds)                             # ~1 Hz, so evaluation happens even if samples stall

States: MONITORING -> COLLECTING (trigger, then 5 s of context) -> ALERTING (until reset()).
"""
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

from .features import N, extract
from .model import Model

G = 9.80665
BIN = 0.02  # 50 Hz peak-hold bins


@dataclass
class Evaluation:
    probability: float
    positive: bool
    features: np.ndarray
    acc: np.ndarray
    gyr: np.ndarray
    v_pre: float
    v_post: float
    gps_ok: bool
    peak_g: float
    trigger_t: float


class Decimator:
    """Peak-hold decimation to 50 Hz: keep the largest-|a| sample of every 20 ms bin."""

    def __init__(self, emit: Callable):
        self.emit, self.bin, self.best, self.best_mag = emit, None, None, -1.0
        self.gyro = (0.0, 0.0, 0.0)

    def on_gyro(self, x, y, z):
        self.gyro = (x, y, z)

    def on_accel(self, t, ax, ay, az):
        b = int(t // BIN)
        if b != self.bin:
            if self.best is not None:
                self.emit(self.best)
            self.bin, self.best, self.best_mag = b, None, -1.0
        m = (ax * ax + ay * ay + az * az) ** 0.5
        if m > self.best_mag:
            self.best_mag, self.best = m, (t, np.array([ax, ay, az]), np.array(self.gyro))


class CrashDetector:
    MONITORING, COLLECTING, ALERTING = "MONITORING", "COLLECTING", "ALERTING"

    def __init__(self, model: Model, on_evaluated: Callable[[Evaluation], None]):
        self.model, self.on_evaluated = model, on_evaluated
        self.state = self.MONITORING
        self._buf: List[Tuple] = []
        self._seq_base = 0
        self._trig_seq, self._trig_t, self._cooldown = -1, 0.0, 0.0
        self._frozen: Optional[Tuple[np.ndarray, np.ndarray]] = None
        self._speeds: List[Tuple[float, float]] = []
        self._dec = Decimator(self._on_sample)

    def on_accelerometer(self, t, ax, ay, az, in_g=False):
        k = 1.0 if in_g else 1.0 / G
        self._dec.on_accel(t, ax * k, ay * k, az * k)

    def on_gyroscope(self, x, y, z):
        self._dec.on_gyro(x, y, z)

    def on_speed(self, t, mps):
        self._speeds.append((t, mps))
        del self._speeds[:-40]

    def reset(self, now):
        self.state, self._trig_seq, self._frozen, self._cooldown = self.MONITORING, -1, None, now + 3.0

    def tick(self, now):
        self._maybe_evaluate(now)

    def _on_sample(self, s):
        self._buf.append(s)
        if len(self._buf) > 600:
            del self._buf[:200]
            self._seq_base += 200
        seq = self._seq_base + len(self._buf) - 1
        t, acc, _ = s
        if (self.state == self.MONITORING and np.linalg.norm(acc) >= self.model.trigger_g
                and t >= self._cooldown):
            self.state, self._trig_seq, self._trig_t, self._frozen = self.COLLECTING, seq, t, None
        if self.state == self.COLLECTING and self._frozen is None and seq >= self._trig_seq + 87:
            self._freeze()
        self._maybe_evaluate(t)

    def _freeze(self):
        idx = [min(len(self._buf) - 1, max(0, self._trig_seq - 40 + k - self._seq_base)) for k in range(N)]
        self._frozen = (np.stack([self._buf[i][1] for i in idx]), np.stack([self._buf[i][2] for i in idx]))

    def _mean_speed(self, a, b):
        v = [s for t, s in self._speeds if a <= t <= b]
        return float(np.mean(v)) if v else None

    def _maybe_evaluate(self, now):
        if self.state != self.COLLECTING or now < self._trig_t + 5.0:
            return
        if self._frozen is None:
            self._freeze()
        acc, gyr = self._frozen
        vp = self._mean_speed(self._trig_t - 6.0, self._trig_t - 1 / 3)
        vq = self._mean_speed(self._trig_t + 3.0, self._trig_t + 5.2)
        gps_ok = vp is not None and vq is not None
        f = extract(acc, gyr, vp or 0.0, vq or 0.0, gps_ok)
        p = self.model.predict_features(f)
        positive = p >= self.model.threshold
        peak = float(np.linalg.norm(acc, axis=1).max())
        if positive:
            self.state = self.ALERTING
        else:
            self.reset(now)
        self._trig_seq, self._frozen = -1, None
        self.on_evaluated(Evaluation(p, positive, f, acc, gyr, vp or 0.0, vq or 0.0, gps_ok, peak, self._trig_t))
