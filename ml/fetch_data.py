"""Download the real public datasets used by the training pipeline.

UCI HAR (Anguita et al., 2013): 30 volunteers, waist-mounted smartphone, 50 Hz
tri-axial accelerometer (total_acc, in g) + gyroscope (rad/s), six everyday
activities. We use it as REAL sensor texture (noise, body motion, gait) that
the simulated crash / hard-negative events are layered on top of, and to measure
how often normal human activity trips the impact trigger.
"""
import io
import sys
import zipfile
import urllib.request
from pathlib import Path

DATA = Path(__file__).parent / "data"
UCI_URL = ("https://archive.ics.uci.edu/static/public/240/"
           "human+activity+recognition+using+smartphones.zip")


def _extract(zbytes: bytes, dest: Path):
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        z.extractall(dest)
    for inner in list(dest.rglob("*.zip")):  # UCI ships a nested zip
        with zipfile.ZipFile(inner) as z:
            z.extractall(dest)


def fetch_uci_har() -> Path:
    root = DATA / "UCI HAR Dataset"
    if (root / "train" / "Inertial Signals").exists():
        return root
    DATA.mkdir(parents=True, exist_ok=True)
    print("Downloading UCI HAR dataset ...", flush=True)
    req = urllib.request.Request(UCI_URL, headers={"User-Agent": "Mozilla/5.0"})
    blob = urllib.request.urlopen(req, timeout=180).read()
    print(f"  {len(blob) / 1e6:.1f} MB", flush=True)
    _extract(blob, DATA)
    if not (root / "train" / "Inertial Signals").exists():
        found = list(DATA.rglob("Inertial Signals"))
        if not found:
            sys.exit("UCI HAR extraction failed")
        return found[0].parent.parent
    return root


if __name__ == "__main__":
    print(fetch_uci_har())
