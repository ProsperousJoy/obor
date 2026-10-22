"""Root compatibility facade for WildfirePredictor.
Re-exports from src.ml.
"""

from src.ml import (
    AMPLIFICATION_FACTOR,
    FEATURE_COLS,
    recalibrate_probability,
    classify_risk_tier,
    estimate_ignition_eta,
    WildfirePredictor,
    get_wildfire_predictor,
)

__all__ = [
    "AMPLIFICATION_FACTOR",
    "FEATURE_COLS",
    "recalibrate_probability",
    "classify_risk_tier",
    "estimate_ignition_eta",
    "WildfirePredictor",
    "get_wildfire_predictor",
]
