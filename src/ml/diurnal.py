"""Diurnal cycle modeling and King & Zeng probability recalibration for Borneo wildfires."""

from datetime import datetime, timezone, timedelta
from typing import Optional
import numpy as np

# King & Zeng (2001) empirical sampling amplification factor for 1:3 spine vs 0.081% base rate
AMPLIFICATION_FACTOR = 641.5

FEATURE_COLS = [
    "prev_day_t2m_max_c",
    "prev_day_rh_min_pct",
    "prev_day_precip_mm",
    "prev_day_wind_speed_kmh",
    "prev_day_soil_moisture",
    "rain_accum_7d_mm",
    "rain_accum_30d_mm",
    "consecutive_dry_days",
    "t2m_anomaly_vs_30d_mean",
    "hotspot_count_prev_24h",
    "hotspot_count_prev_7d",
    "max_frp_prev_7d",
    "has_recent_fire_7d",
    "month",
    "centroid_lat",
    "centroid_lon",
]


def recalibrate_probability(p_hat: np.ndarray, alpha: float = AMPLIFICATION_FACTOR, eps: float = 1e-12) -> np.ndarray:
    """
    Recalibrate model predicted probabilities using King & Zeng (2001) log-odds shift:
        logit(p_calibrated) = logit(p_hat) - ln(alpha)
    """
    p_clipped = np.clip(p_hat, eps, 1.0 - eps)
    logit_p_hat = np.log(p_clipped / (1.0 - p_clipped))
    logit_calibrated = logit_p_hat - np.log(alpha)
    return 1.0 / (1.0 + np.exp(-logit_calibrated))


def classify_risk_tier(p_cal: float) -> str:
    """Classify calibrated ignition risk into standard disaster management tiers."""
    if p_cal < 0.05:
        return "NORMAL"
    elif p_cal < 0.15:
        return "WASPADA (ALERT)"
    elif p_cal < 0.35:
        return "SIAGA (HIGH)"
    else:
        return "AWAS (CRITICAL)"


def estimate_ignition_eta(risk_prob: float, dry_days: int, current_dt_utc: Optional[datetime] = None) -> dict:
    """
    Compute operational ignition ETA and peak fire threat window.
    Calibrated against Kalimantan's diurnal meteorological curve where peak solar insolation
    and minimum relative humidity occur between 13:00 - 16:30 local time (WIB/WITA).
    """
    if current_dt_utc is None:
        current_dt_utc = datetime.now(timezone.utc)

    # Reference to Central/East Kalimantan (WITA = UTC+8)
    local_time = current_dt_utc + timedelta(hours=8)
    local_hour = local_time.hour + local_time.minute / 60.0

    peak_start = 13.0
    peak_end = 16.5

    if local_hour < peak_start:
        hours_to_start = max(0.5, peak_start - local_hour)
        hours_to_end = peak_end - local_hour
        if dry_days > 14 and risk_prob > 0.25:
            eta_low = max(0.5, hours_to_start - 0.5)
            eta_high = max(eta_low + 1.0, hours_to_end - 0.5)
        else:
            eta_low = hours_to_start
            eta_high = hours_to_end

        eta_display = f"⚡ {eta_low:.0f}-{eta_high:.0f} jam (Puncak: 13:00-16:30 WITA)"
        urgency = "Siang Ini (13:00-16:30)"
    elif local_hour <= peak_end:
        rem = max(1.0, peak_end - local_hour)
        eta_low = 0.5
        eta_high = rem
        eta_display = f"🚨 Segera (< {rem:.0f} jam / Puncak Aktif)"
        urgency = "Jendela Kritis Aktif"
    else:
        hours_tomorrow = (24.0 - local_hour) + peak_start
        eta_low = hours_tomorrow
        eta_high = hours_tomorrow + 3.5
        eta_display = f"🌅 Besok Siang (~{eta_low:.0f} jam / 13:00-16:30)"
        urgency = "Besok Siang"

    return {
        "eta_display": eta_display,
        "eta_hours_min": round(eta_low, 1),
        "eta_hours_max": round(eta_high, 1),
        "peak_window": urgency
    }
