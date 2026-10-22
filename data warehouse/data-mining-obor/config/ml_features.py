"""
Machine Learning Feature Definitions & Calibration Configuration
----------------------------------------------------------------
Authoritative specification of feature vectors, target definitions,
and sampling recalibration parameters for Kalimantan Wildfire Risk Modeling.
"""

from typing import List, Union
import numpy as np

# ─────────────────────────────────────────────────────────────────────
# 1. Metadata and Identification Columns
# ─────────────────────────────────────────────────────────────────────
METADATA_COLS: List[str] = [
    "sample_id",
    "grid_id",
    "target_datetime",
    "split",
    "year",
    "month",
    "centroid_lat",
    "centroid_lon",
    "province",
    "is_land",
]

# ─────────────────────────────────────────────────────────────────────
# 2. Baseline Model Feature Vector (Non-Null, Scientifically Valid)
# ─────────────────────────────────────────────────────────────────────
# Weather features: strictly antecedent (T-1 day), IDW interpolated
WEATHER_FEATURE_COLS: List[str] = [
    "prev_day_t2m_max_c",
    "prev_day_rh_min_pct",
    "prev_day_precip_mm",
    "prev_day_wind_speed_kmh",
    "prev_day_soil_moisture",
    "rain_accum_7d_mm",
    "rain_accum_30d_mm",
    "consecutive_dry_days",
    "t2m_anomaly_vs_30d_mean",
]

# Fire history features: strictly antecedent (T-24h, T-7d)
FIRE_HISTORY_FEATURE_COLS: List[str] = [
    "hotspot_count_prev_24h",
    "hotspot_count_prev_7d",
    "max_frp_prev_7d",
    "has_recent_fire_7d",
]

# Spatial/temporal context features useful as model inputs
CONTEXT_FEATURE_COLS: List[str] = [
    "month",
    "centroid_lat",
    "centroid_lon",
]

# Complete baseline feature set for ML model training
BASELINE_FEATURE_COLS: List[str] = (
    WEATHER_FEATURE_COLS + FIRE_HISTORY_FEATURE_COLS + CONTEXT_FEATURE_COLS
)

# ─────────────────────────────────────────────────────────────────────
# 3. Target Variable Definitions (Strictly in (T, T+24h])
# ─────────────────────────────────────────────────────────────────────
TARGET_COLS: List[str] = [
    "target_fire_count_24h",     # Count regression target
    "target_has_fire_24h",      # Binary classification target (0 or 1)
    "target_fire_intensity_24h", # Intensity regression target (max FRP in MW)
]

PRIMARY_BINARY_TARGET: str = "target_has_fire_24h"

# ─────────────────────────────────────────────────────────────────────
# 4. Quarantined & Excluded Columns (Must NOT be fed to model)
# ─────────────────────────────────────────────────────────────────────
# Thermal features: Himawari-8/9 NetCDF thermal features are unpopulated
# for historical training period (2021-2025) and currently 100% NULL.
EXCLUDED_THERMAL_COLS: List[str] = [
    "th_bt_mean_k",
    "th_bt_max_k",
    "th_bt_min_k",
    "th_bt_std_k",
    "th_valid_pixel_pct",
    "th_hotspot_candidate_count",
    "th_bt_anomaly_k",
    "th_bt_change_1h",
    "prev_day_bt_mean_k",
    "prev_day_bt_max_k",
    "prev_day_thermal_persistence",
]

# Fuel features: Synthetic sine-wave vegetation indices quarantined
# to avoid training on artificial data.
EXCLUDED_FUEL_COLS: List[str] = [
    "fuel_ndvi",
    "fuel_evi",
    "fuel_ndmi",
    "fuel_days_since_update",
]

# All excluded columns combined
EXCLUDED_COLS: List[str] = EXCLUDED_THERMAL_COLS + EXCLUDED_FUEL_COLS

# ─────────────────────────────────────────────────────────────────────
# 5. Sampling Calibration & Prior Correction (FIX-06)
# ─────────────────────────────────────────────────────────────────────
# In the training spine, presence-background sampling uses a 1:3 positive-to-background ratio.
# In the full Kalimantan spatiotemporal population (~152,837 land cells * 1,826 days = ~279M cell-days),
# true positive prevalence is ~0.081% (226,639 / 279,080,362).
# In the training dataset, sampled prevalence is 25.0% (1 / 4).
# This results in an empirical positive amplification factor alpha ≈ 641.5x:
#   alpha = (p_sample / (1 - p_sample)) / (p_pop / (1 - p_pop))
DEFAULT_AMPLIFICATION_FACTOR: float = 641.5

def recalibrate_probability(
    p_hat: Union[float, np.ndarray],
    amplification_factor: float = DEFAULT_AMPLIFICATION_FACTOR,
    eps: float = 1e-12
) -> Union[float, np.ndarray]:
    """
    Recalibrate model predicted probabilities using King & Zeng (2001) log-odds shift:
        logit(p_calibrated) = logit(p_hat) - ln(alpha)
        
    Args:
        p_hat: Raw model predicted probability in [0, 1] trained on 1:3 sampled spine.
        amplification_factor: Ratio of sample odds to population odds (default 641.5).
        eps: Small constant to avoid log(0) and division by zero.
        
    Returns:
        Calibrated true risk probability reflecting real Kalimantan population base rate.
    """
    p_clipped = np.clip(p_hat, eps, 1.0 - eps)
    logit_p_hat = np.log(p_clipped / (1.0 - p_clipped))
    logit_calibrated = logit_p_hat - np.log(amplification_factor)
    return 1.0 / (1.0 + np.exp(-logit_calibrated))
