import json
from pathlib import Path

import numpy as np
import pytest

from crashguard import CrashDetector, Model, extract

ROOT = Path(__file__).resolve().parent.parent
PARITY = json.loads((ROOT / "ml" / "model" / "parity.json").read_text())
MODEL = Model.load()
G = 9.80665


def test_bundled_model_matches_training_export():
    assert json.loads((ROOT / "ml/model/crash_model.json").read_text()) == \
        json.loads((ROOT / "crashguard/data/crash_model.json").read_text())


@pytest.mark.parametrize("case", PARITY, ids=[c["name"] for c in PARITY])
def test_features_and_probability_match_export(case):
    f = extract(case["acc"], case["gyr"], case["v_pre"], case["v_post"], bool(case["gps_ok"]))
    np.testing.assert_allclose(f, case["features"], rtol=1e-3, atol=1e-3)
    assert abs(MODEL.predict_features(f) - case["probability"]) < 1e-3


@pytest.mark.parametrize("case", PARITY, ids=[c["name"] for c in PARITY])
def test_streaming_detector_replay(case):
    out = []
    det = CrashDetector(MODEL, out.append)
    t0, trig_t = 10.0, None
    for k, (a, g) in enumerate(zip(case["acc"], case["gyr"])):
        t = t0 + k * 0.02
        det.on_gyroscope(*g)
        det.on_accelerometer(t, *(np.array(a) * G))
        if trig_t is None and np.linalg.norm(a) >= MODEL.trigger_g:
            trig_t = t
    if case["gps_ok"]:
        det.on_speed(trig_t - 2.0, case["v_pre"])
        det.on_speed(trig_t + 4.0, case["v_post"])
    for k in range(128, 128 + 260):
        det.on_gyroscope(0, 0, 0)
        det.on_accelerometer(t0 + k * 0.02, 0, 0, G)
    det.tick(t0 + 400 * 0.02)
    assert len(out) == 1
    py = case["probability"]
    if abs(py - MODEL.threshold) > 0.2:
        assert out[0].positive == (py >= MODEL.threshold)


def test_rejects_wrong_window_size():
    with pytest.raises(Exception):
        extract(np.zeros((10, 3)), np.zeros((10, 3)))
