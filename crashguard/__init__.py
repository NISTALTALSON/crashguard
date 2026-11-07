"""CrashGuard: an open crash-detection model for phone / watch / bike motion sensors."""
from .detector import CrashDetector, Evaluation
from .features import FEATURES, extract
from .model import Model

__version__ = "0.1.0"
__all__ = ["Model", "CrashDetector", "Evaluation", "extract", "FEATURES", "__version__"]
