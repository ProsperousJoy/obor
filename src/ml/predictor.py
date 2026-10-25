"""Operational Wildfire Risk Predictor & Inference Engine."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import duckdb
import joblib
import numpy as np
import pandas as pd

from src.config import config
from src.ml.diurnal import (
    AMPLIFICATION_FACTOR,
    FEATURE_COLS,
    classify_risk_tier,
    estimate_ignition_eta,
    recalibrate_probability,
)

logger = logging.getLogger("wildfire_predictor")

PROJECT_ROOT = config.PROJECT_ROOT
DB_PATH = Path(config.WAREHOUSE_DB_PATH)
MODEL_DIR = PROJECT_ROOT / "outputs" / "models"
CLF_PATH = MODEL_DIR / "best_wildfire_classifier.joblib"
REG_PATH = MODEL_DIR / "best_wildfire_regressor.joblib"


class WildfirePredictor:
    def __init__(self, clf_path: Path = CLF_PATH, reg_path: Path = REG_PATH, db_path: Path = DB_PATH):
        self.clf_path = clf_path
        self.reg_path = reg_path
        self.db_path = db_path

        self.clf_artifact = None
        self.reg_artifact = None
        self._cached_cells: List[Dict[str, Any]] = []
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
            return self._cached_cells[:limit] if self._cached_cells else []

        try:
            con = duckdb.connect(str(self.db_path))
            try:
                query = f"""
                    SELECT 
                        grid_id, centroid_lat, centroid_lon, province,
                        {', '.join(FEATURE_COLS)}
                    FROM vw_training_dataset
                    WHERE split = 'TEST' AND month IN (8, 9, 10)
                    ORDER BY hotspot_count_prev_7d DESC, consecutive_dry_days DESC
                    LIMIT 1000
                """
                df = con.execute(query).df()
            finally:
                con.close()

            if len(df) == 0:
                return self._cached_cells[:limit] if self._cached_cells else []

            df["has_recent_fire_7d"] = df["has_recent_fire_7d"].astype(int)
            scored_df = self.predict_features(df)

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
            if results:
                self._cached_cells = results
            return results
        except Exception as e:
            logger.warning(f"Error querying top at risk cells from DuckDB: {e}")
            return self._cached_cells[:limit] if self._cached_cells else []

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


_predictor = None


def get_wildfire_predictor() -> WildfirePredictor:
    global _predictor
    if _predictor is None:
        _predictor = WildfirePredictor()
    return _predictor
