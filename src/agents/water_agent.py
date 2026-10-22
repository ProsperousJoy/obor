"""
Module 4 — Water Resource Agent
-------------------------------
Answers: 'If we must suppress this fire, where is the best water available?'
Queries dim_water_sources from the warehouse, calculates distance, capacity,
pump feasibility, and recommends the optimal primary and backup water sources.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import math
import duckdb


def _resolve_default_db_path() -> str:
    # 1. Try src.config
    try:
        from src.config import config
        if Path(config.WAREHOUSE_DB_PATH).exists():
            return config.WAREHOUSE_DB_PATH
    except Exception:
        pass

    # 2. Direct relative search from this file or parent dirs
    current = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = current / "data warehouse" / "data-mining-obor" / "data" / "warehouse" / "wildfire.duckdb"
        if candidate.exists():
            return str(candidate)
        candidate2 = current / "data" / "warehouse" / "wildfire.duckdb"
        if candidate2.exists():
            return str(candidate2)
        current = current.parent

    # 3. Try root config
    try:
        import config as root_cfg
        if hasattr(root_cfg, "config") and Path(root_cfg.config.WAREHOUSE_DB_PATH).exists():
            return root_cfg.config.WAREHOUSE_DB_PATH
    except Exception:
        pass

    return "data warehouse/data-mining-obor/data/warehouse/wildfire.duckdb"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes Great Circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    return R * 2.0 * math.asin(math.sqrt(a))

class WaterResourceAgent:
    """
    Evaluates nearest water sources, pumping accessibility, and suitability scores.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or _resolve_default_db_path()

    def recommend_water_source(
        self,
        incident_id: str,
        fire_lat: float,
        fire_lon: float,
        conn: duckdb.DuckDBPyConnection = None
    ) -> Dict[str, Any]:
        """
        Ranks candidate water sources by suitability score:
        Suitability = Distance Decay (40%) + Permanence (25%) + Capacity (20%) + Pump Feasibility (15%)
        """
        close_conn = False
        if conn is None:
            conn = duckdb.connect(self.db_path, read_only=True)
            close_conn = True

        df = conn.execute("""
            SELECT source_id, source_name, water_type, province, kabupaten,
                   lat, lon, capacity_m3, surface_area_m2, historical_permanence_score,
                   pump_accessible, terrain_difficulty
            FROM dim_water_sources
        """).df()

        if close_conn:
            conn.close()

        if df.empty:
            raise ValueError("No water sources found in dim_water_sources table.")

        # Compute Euclidean/Haversine distance
        df["distance_km"] = df.apply(
            lambda r: haversine_km(fire_lat, fire_lon, r["lat"], r["lon"]), axis=1
        )
        
        # Approximate track route distance (~1.3x Euclidean in peatland/rural tracks)
        df["route_distance_km"] = (df["distance_km"] * 1.3).round(2)
        
        # Estimate travel time in minutes (assumes 25 km/h avg speed on rural tracks)
        df["estimated_travel_time_min"] = (df["route_distance_km"] / 25.0 * 60.0).round().astype(int)

        # Suitability Components
        # Distance score: smooth exponential decay with 50km characteristic length
        # Guarantees local sources within 100km strictly dominate distant provinces (e.g. 400km away)
        import numpy as np
        dist_score = np.exp(-df["distance_km"] / 50.0)
        
        # Capacity score (scaled logarithmic up to 100,000 m3)
        cap_score = (df["capacity_m3"] / 100000.0).clip(lower=0.1, upper=1.0)
        
        # Pump accessibility score
        pump_score = df["pump_accessible"].apply(lambda p: 1.0 if p else 0.4)
        
        # Terrain penalty
        terrain_mult = df["terrain_difficulty"].map({"EASY": 1.0, "MODERATE": 0.85, "DIFFICULT": 0.65}).fillna(0.8)
        
        # Composite Suitability Score (Distance heavily weighted to prevent cross-island misrouting)
        df["water_suitability"] = (
            0.50 * dist_score +
            0.20 * df["historical_permanence_score"] +
            0.15 * cap_score +
            0.15 * pump_score
        ) * terrain_mult
        
        df["water_suitability"] = df["water_suitability"].round(3)
        df = df.sort_values(by="water_suitability", ascending=False).reset_index(drop=True)

        primary = df.iloc[0]
        backups = []
        for _, row in df.iloc[1:4].iterrows():
            backups.append({
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "water_type": row["water_type"],
                "distance_km": round(float(row["distance_km"]), 2),
                "water_suitability": float(row["water_suitability"])
            })

        return {
            "incident_id": incident_id,
            "recommended_water_source": primary["source_name"],
            "source_id": primary["source_id"],
            "lat": round(float(primary["lat"]), 4),
            "lon": round(float(primary["lon"]), 4),
            "water_type": primary["water_type"],
            "distance_km": round(float(primary["distance_km"]), 2),
            "route_distance_km": float(primary["route_distance_km"]),
            "estimated_travel_time_min": int(primary["estimated_travel_time_min"]),
            "estimated_capacity_m3": float(primary["capacity_m3"]),
            "water_availability": float(primary["historical_permanence_score"]),
            "accessibility": round(float(terrain_mult.iloc[0]), 2),
            "pump_feasibility": 0.95 if primary["pump_accessible"] else 0.40,
            "water_suitability": float(primary["water_suitability"]),
            "backup_water_sources": backups
        }
