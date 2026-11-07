"""Validate a contributed CrashGuard event file:  python tools/validate_event.py event.json [...]"""
import json
import sys

import numpy as np

VEHICLES = {"car", "motorcycle", "scooter", "bicycle", "auto_rickshaw", "pedestrian", "none", "other"}
FORBIDDEN = {"lat", "lon", "latitude", "longitude", "location", "name", "phone", "email", "timestamp", "t"}


def validate(e: dict) -> list:
    errs = []
    if e.get("schema_version") != 1:
        errs.append("schema_version must be 1")
    if e.get("label") not in ("crash", "not_crash"):
        errs.append("label must be 'crash' or 'not_crash'")
    if e.get("vehicle") not in VEHICLES:
        errs.append(f"vehicle must be one of {sorted(VEHICLES)}")
    if e.get("sample_rate_hz") != 50:
        errs.append("sample_rate_hz must be 50")
    for k in ("acc", "gyr"):
        try:
            a = np.asarray(e[k], dtype=float)
            if a.shape != (128, 3):
                errs.append(f"{k} must be 128x3, got {a.shape}")
            elif not np.isfinite(a).all():
                errs.append(f"{k} has NaN/inf")
        except Exception:
            errs.append(f"{k} missing or malformed")
    try:
        mag = np.linalg.norm(np.asarray(e["acc"], dtype=float), axis=1)
        if mag.max() < 3.5:
            errs.append(f"peak {mag.max():.2f} g is below the 3.5 g trigger; it would never reach the model")
        elif not 25 <= int(mag.argmax()) <= 60:
            errs.append("impact should be near sample 40 (peak at index %d)" % mag.argmax())
    except Exception:
        pass
    if e.get("gps_ok") and not all(isinstance(e.get(k), (int, float)) for k in ("v_pre", "v_post")):
        errs.append("gps_ok=true needs numeric v_pre and v_post (m/s)")
    if e.get("consent") is not True:
        errs.append("consent must be true")
    bad = FORBIDDEN & set(e)
    if bad:
        errs.append(f"remove personal/location fields: {sorted(bad)}")
    return errs


if __name__ == "__main__":
    bad = 0
    for path in sys.argv[1:]:
        errs = validate(json.load(open(path)))
        print(("OK   " if not errs else "FAIL ") + path)
        for x in errs:
            print("   -", x)
        bad += bool(errs)
    sys.exit(1 if bad or len(sys.argv) < 2 else 0)
