"""Model loading + inference for the CrashGuard impact classifier (pure numpy)."""
import json
from importlib import resources
from pathlib import Path

import numpy as np

from .features import extract


class Model:
    """Small MLP exported by ml/train.py: standardise -> ReLU layers -> sigmoid."""

    def __init__(self, spec: dict):
        self.version = spec.get("version")
        self.trigger_g = float(spec["trigger_g"])
        self.threshold = float(spec["threshold"])
        self.feature_names = spec["features"]
        self.mean = np.asarray(spec["mean"])
        self.std = np.asarray(spec["std"])
        self.weights = [np.asarray(w) for w in spec["weights"]]
        self.biases = [np.asarray(b) for b in spec["biases"]]

    @classmethod
    def load(cls, path=None) -> "Model":
        """Load the bundled model, or any model file exported by ml/train.py."""
        if path is None:
            text = resources.files("crashguard").joinpath("data/crash_model.json").read_text()
        else:
            text = Path(path).read_text()
        return cls(json.loads(text))

    def predict_features(self, x) -> float:
        h = (np.asarray(x, dtype=np.float64) - self.mean) / self.std
        for i, (w, b) in enumerate(zip(self.weights, self.biases)):
            h = h @ w + b
            h = np.maximum(h, 0.0) if i < len(self.weights) - 1 else 1.0 / (1.0 + np.exp(-h))
        return float(h[0])

    def predict(self, acc, gyr, v_pre=0.0, v_post=0.0, gps_ok=False) -> float:
        """Crash probability for one 128-sample, 50 Hz window (acc in g incl. gravity, gyr in rad/s)."""
        return self.predict_features(extract(acc, gyr, v_pre, v_post, gps_ok))

    def is_crash(self, *args, **kw) -> bool:
        return self.predict(*args, **kw) >= self.threshold
