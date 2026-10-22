"""Wildfire Machine Learning and Predictive Analytics Package."""

from src.ml.diurnal import (
    AMPLIFICATION_FACTOR,
    FEATURE_COLS,
    recalibrate_probability,
    classify_risk_tier,
    estimate_ignition_eta,
)
from src.ml.predictor import (
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
