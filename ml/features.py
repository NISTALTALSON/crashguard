"""Shim: the reference feature code lives in the installable package (crashguard/features.py)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crashguard.features import *  # noqa: F401,F403,E402
from crashguard.features import _count_impacts, _unit_mean  # noqa: F401,E402
