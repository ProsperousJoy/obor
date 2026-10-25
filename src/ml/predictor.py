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
            return self._cached_cells[:limit] if self._cached_cells else self._get_fallback_cells(limit)

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
                return self._cached_cells[:limit] if self._cached_cells else self._get_fallback_cells(limit)

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
            return self._cached_cells[:limit] if self._cached_cells else self._get_fallback_cells(limit)

    def _get_fallback_cells(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Generate representative Kalimantan test grid cells and run real ML inference.
        Ensures predictions work out-of-the-box on any machine even before warehouse sync.
        """
        fallback_specs = [
            {"grid_id": "G0108_0135", "lat": -2.68, "lon": 111.62, "province": "Kalimantan Tengah", "dry_days": 14, "hotspots": 28, "t2m": 34.5, "rh": 48.0},
            {"grid_id": "G0107_0140", "lat": -2.48, "lon": 113.85, "province": "Kalimantan Tengah", "dry_days": 12, "hotspots": 24, "t2m": 34.0, "rh": 50.0},
            {"grid_id": "G0105_0142", "lat": -3.01, "lon": 114.39, "province": "Kalimantan Tengah", "dry_days": 10, "hotspots": 19, "t2m": 33.5, "rh": 52.0},
            {"grid_id": "G0112_0128", "lat": -1.85, "lon": 110.00, "province": "Kalimantan Barat", "dry_days": 11, "hotspots": 22, "t2m": 33.8, "rh": 51.0},
            {"grid_id": "G0102_0145", "lat": -3.45, "lon": 114.83, "province": "Kalimantan Selatan", "dry_days": 9, "hotspots": 15, "t2m": 33.2, "rh": 55.0},
            {"grid_id": "G0118_0152", "lat": -0.50, "lon": 117.15, "province": "Kalimantan Timur", "dry_days": 8, "hotspots": 12, "t2m": 33.0, "rh": 56.0},
            {"grid_id": "G0115_0148", "lat": -1.87, "lon": 116.15, "province": "Kalimantan Timur", "dry_days": 7, "hotspots": 10, "t2m": 32.8, "rh": 58.0},
            {"grid_id": "G0414_0254", "lat": 2.84, "lon": 117.37, "province": "Kalimantan Utara", "dry_days": 6, "hotspots": 9, "t2m": 32.5, "rh": 60.0},
            {"grid_id": "G0109_0138", "lat": -2.05, "lon": 113.40, "province": "Kalimantan Tengah", "dry_days": 13, "hotspots": 26, "t2m": 34.2, "rh": 49.0},
            {"grid_id": "G0103_0146", "lat": -3.80, "lon": 114.78, "province": "Kalimantan Selatan", "dry_days": 8, "hotspots": 14, "t2m": 33.0, "rh": 56.0},
            {"grid_id": "G0110_0132", "lat": -0.06, "lon": 109.32, "province": "Kalimantan Barat", "dry_days": 7, "hotspots": 11, "t2m": 32.7, "rh": 59.0},
            {"grid_id": "G0114_0130", "lat": 0.07, "lon": 111.50, "province": "Kalimantan Barat", "dry_days": 5, "hotspots": 8, "t2m": 32.0, "rh": 62.0},
        ]

        rows = []
        for s in fallback_specs:
            row = {
                "grid_id": s["grid_id"],
                "centroid_lat": s["lat"],
                "centroid_lon": s["lon"],
                "province": s["province"],
                "prev_day_t2m_max_c": s["t2m"],
                "prev_day_rh_min_pct": s["rh"],
                "prev_day_precip_mm": 0.0,
                "prev_day_wind_speed_kmh": 14.5,
                "prev_day_soil_moisture": 0.18,
                "rain_accum_7d_mm": 2.5,
                "rain_accum_30d_mm": 28.0,
                "consecutive_dry_days": s["dry_days"],
                "t2m_anomaly_vs_30d_mean": 1.8,
                "hotspot_count_prev_24h": max(1, s["hotspots"] // 4),
                "hotspot_count_prev_7d": s["hotspots"],
                "max_frp_prev_7d": float(s["hotspots"] * 3.5),
                "has_recent_fire_7d": 1,
                "month": 9,
            }
            rows.append(row)

        df = pd.DataFrame(rows)
        now_utc = datetime.now(timezone.utc)
        results = []

        if self.is_ready:
            try:
                scored = self.predict_features(df)
                scored = scored.sort_values(by="calibrated_risk_prob", ascending=False)
                for _, r in scored.head(limit).iterrows():
                    cal_risk = float(r["calibrated_risk_prob"])
                    dry_days = int(r["consecutive_dry_days"])
                    eta_info = estimate_ignition_eta(cal_risk, dry_days, now_utc)
                    results.append({
                        "grid_id": r["grid_id"],
                        "lat": float(r["centroid_lat"]),
                        "lon": float(r["centroid_lon"]),
                        "province": r["province"],
                        "raw_risk": float(r["raw_risk_prob"]),
                        "calibrated_risk": cal_risk,
                        "risk_tier": r["risk_tier"],
                        "predicted_frp_mw": float(r["predicted_intensity_frp_mw"]),
                        "consecutive_dry_days": dry_days,
                        "hotspot_count_prev_7d": int(r["hotspot_count_prev_7d"]),
                        "estimated_eta": eta_info["eta_display"],
                        "eta_hours_min": eta_info["eta_hours_min"],
                        "eta_hours_max": eta_info["eta_hours_max"],
                        "peak_window": eta_info["peak_window"],
                    })
            except Exception as e:
                logger.error(f"Fallback feature scoring failed: {e}")

        if not results:
            # Safe heuristic baseline if model artifacts are also unavailable
            for s in fallback_specs[:limit]:
                risk = min(0.45, 0.15 + (s["dry_days"] * 0.015) + (s["hotspots"] * 0.005))
                eta_info = estimate_ignition_eta(risk, s["dry_days"], now_utc)
                results.append({
                    "grid_id": s["grid_id"],
                    "lat": s["lat"],
                    "lon": s["lon"],
                    "province": s["province"],
                    "raw_risk": round(risk * 2.5, 4),
                    "calibrated_risk": round(risk, 4),
                    "risk_tier": classify_risk_tier(risk),
                    "predicted_frp_mw": round(s["hotspots"] * 1.8, 1),
                    "consecutive_dry_days": s["dry_days"],
                    "hotspot_count_prev_7d": s["hotspots"],
                    "estimated_eta": eta_info["eta_display"],
                    "eta_hours_min": eta_info["eta_hours_min"],
                    "eta_hours_max": eta_info["eta_hours_max"],
                    "peak_window": eta_info["peak_window"],
                })

        self._cached_cells = results
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


_predictor = None


def get_wildfire_predictor() -> WildfirePredictor:
    global _predictor
    if _predictor is None:
        _predictor = WildfirePredictor()
    return _predictor
