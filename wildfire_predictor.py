"""
Wildfire Sentinel — Operational Wildfire Risk Predictor & Inference Engine
--------------------------------------------------------------------------
Loads the serialized winning machine learning model from outputs/models/
and computes real-time calibrated 24-hour wildfire ignition probability
and fire intensity (FRP in MW) across Kalimantan 2km grid cells.

Applies King & Zeng (2001) probability recalibration to map from
1:3 sampled spine back to true Kalimantan spatiotemporal base rate.
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

import duckdb
import numpy as np
import pandas as pd
import joblib

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wildfire_predictor")

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "data warehouse" / "data-mining-obor" / "data" / "warehouse" / "wildfire.duckdb"
MODEL_DIR = PROJECT_ROOT / "outputs" / "models"
CLF_PATH = MODEL_DIR / "best_wildfire_classifier.joblib"
REG_PATH = MODEL_DIR / "best_wildfire_regressor.joblib"

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


class WildfirePredictor:
    def __init__(self, clf_path: Path = CLF_PATH, reg_path: Path = REG_PATH, db_path: Path = DB_PATH):
        self.clf_path = clf_path
        self.reg_path = reg_path
        self.db_path = db_path
        
        self.clf_artifact = None
        self.reg_artifact = None
        self._load_models()

    def _load_models(self):
        if self.clf_path.exists():
            try:
                self.clf_artifact = joblib.load(self.clf_path)
                logger.info(f"Loaded classifier: {self.clf_artifact.get('model_key', 'Unknown')}")
            except Exception as e:
                logger.error(f"Failed to load classifier from {self.clf_path}: {e}")
                
        if self.reg_path.exists():
            try:
                self.reg_artifact = joblib.load(self.reg_path)
                logger.info(f"Loaded regressor: {self.reg_artifact.get('model_key', 'Unknown')}")
            except Exception as e:
                logger.error(f"Failed to load regressor from {self.reg_path}: {e}")

    @property
    def is_ready(self) -> bool:
        return self.clf_artifact is not None

    def predict_features(self, df_features: pd.DataFrame) -> pd.DataFrame:
        """Run model inference on a DataFrame of features."""
        if not self.is_ready:
            raise RuntimeError("Classifier model is not loaded.")

        imputer = self.clf_artifact["imputer"]
        scaler = self.clf_artifact.get("scaler")
        model = self.clf_artifact["model"]

        # Ensure all columns present
        for col in FEATURE_COLS:
            if col not in df_features.columns:
                df_features[col] = 0.0

        X = imputer.transform(df_features[FEATURE_COLS])
        if scaler is not None:
            X = scaler.transform(X)

        # 1. Raw Probability & Recalibration
        p_raw = model.predict_proba(X)[:, 1]
        p_cal = recalibrate_probability(p_raw)

        # 2. Predicted Intensity (FRP in MW)
        predicted_frp = np.zeros_like(p_cal)
        if self.reg_artifact is not None:
            reg_model = self.reg_artifact["model"]
            reg_imputer = self.reg_artifact["imputer"]
            reg_scaler = self.reg_artifact.get("scaler")
            
            X_reg = reg_imputer.transform(df_features[FEATURE_COLS])
            if reg_scaler is not None:
                X_reg = reg_scaler.transform(X_reg)
            predicted_frp = np.clip(reg_model.predict(X_reg), 0, None)

        out_df = df_features.copy()
        out_df["raw_risk_prob"] = np.round(p_raw, 4)
        out_df["calibrated_risk_prob"] = np.round(p_cal, 4)
        out_df["risk_tier"] = [classify_risk_tier(p) for p in p_cal]
        out_df["predicted_intensity_frp_mw"] = np.round(predicted_frp, 2)
        return out_df

    def get_top_at_risk_cells(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Query analytical warehouse for active test/inference grid cells and return
        the highest ignition probability locations in Kalimantan for early dispatch.
        """
        if not self.db_path.exists():
            return []

        con = duckdb.connect(str(self.db_path), read_only=True)
        # Query 1,000 candidate grid cells with recent fire or high drought
        query = f"""
            SELECT 
                grid_id, centroid_lat, centroid_lon, province,
                {', '.join(FEATURE_COLS)}
            FROM vw_training_dataset
            WHERE split = 'TEST' AND month IN (8, 9, 10)
            ORDER BY hotspot_count_prev_7d DESC, consecutive_dry_days DESC
            LIMIT 1000
        """
        try:
            df = con.execute(query).df()
        finally:
            con.close()

        if len(df) == 0:
            return []

        df["has_recent_fire_7d"] = df["has_recent_fire_7d"].astype(int)
        scored_df = self.predict_features(df)
        
        # Sort by calibrated risk probability descending
        top_df = scored_df.sort_values(by="calibrated_risk_prob", ascending=False).head(limit)
        
        results = []
        now_utc = datetime.now(timezone.utc)
        for _, row in top_df.iterrows():
            cal_risk = float(row["calibrated_risk_prob"])
            dry_days = int(row.get("consecutive_dry_days", 0))
            eta_info = estimate_ignition_eta(cal_risk, dry_days, now_utc)
            results.append({
                "grid_id": row["grid_id"],
                "lat": float(row["centroid_lat"]),
                "lon": float(row["centroid_lon"]),
                "province": row.get("province", "Kalimantan"),
                "raw_risk": float(row["raw_risk_prob"]),
                "calibrated_risk": cal_risk,
                "risk_tier": row["risk_tier"],
                "predicted_frp_mw": float(row["predicted_intensity_frp_mw"]),
                "consecutive_dry_days": dry_days,
                "hotspot_count_prev_7d": int(row.get("hotspot_count_prev_7d", 0)),
                "estimated_eta": eta_info["eta_display"],
                "eta_hours_min": eta_info["eta_hours_min"],
                "eta_hours_max": eta_info["eta_hours_max"],
                "peak_window": eta_info["peak_window"],
            })
        return results

    def get_risk_heatmap_geojson(self, limit: int = 200) -> Dict[str, Any]:
        """Generate GeoJSON FeatureCollection of predicted high-risk grid cells for Leaflet."""
        cells = self.get_top_at_risk_cells(limit=limit)
        features = []
        for c in cells:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [c["lon"], c["lat"]]
                },
                "properties": {
                    "grid_id": c["grid_id"],
                    "province": c["province"],
                    "calibrated_risk": c["calibrated_risk"],
                    "risk_tier": c["risk_tier"],
                    "predicted_frp_mw": c["predicted_frp_mw"],
                    "dry_days": c["consecutive_dry_days"],
                    "estimated_eta": c["estimated_eta"],
                    "peak_window": c["peak_window"],
                }
            })
        return {
            "type": "FeatureCollection",
            "features": features,
            "total": len(features)
        }


# Global singleton predictor instance
_predictor = None

def get_wildfire_predictor() -> WildfirePredictor:
    global _predictor
    if _predictor is None:
        _predictor = WildfirePredictor()
    return _predictor
