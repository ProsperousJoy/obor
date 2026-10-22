"""
Module 3 — Impact Assessment Agent
----------------------------------
Calculates the danger and urgency of an active fire incident:
Evaluates proximity to settlements, schools, hospitals, peatland ecosystems,
and computes a composite Impact Score (0–100) and response Priority.
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

class ImpactAgent:
    """
    Answers: 'If this fire is real, how dangerous and destructive is it?'
    Queries dim_vulnerable_assets from the warehouse to assess nearby exposure.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or _resolve_default_db_path()

    def assess_impact(
        self,
        incident_id: str,
        fire_lat: float,
        fire_lon: float,
        fire_probability: float,
        fire_intensity: str = "MEDIUM",
        estimated_area_ha: float = 5.0,
        wind_speed_kph: float = 15.0,
        wind_direction_deg: float = 90.0,
        conn: duckdb.DuckDBPyConnection = None
    ) -> Dict[str, Any]:
        """
        Assesses population, ecological, and infrastructural risk.
        """
        close_conn = False
        if conn is None:
            conn = duckdb.connect(self.db_path, read_only=True)
            close_conn = True

        # Query all vulnerable assets from warehouse
        assets_df = conn.execute("""
            SELECT asset_id, asset_name, asset_type, province, kabupaten, 
                   lat, lon, estimated_population, is_peatland, is_protected_area
            FROM dim_vulnerable_assets
        """).df()

        if close_conn:
            conn.close()

        # Compute distances to all assets
        assets_df["distance_km"] = assets_df.apply(
            lambda r: haversine_km(fire_lat, fire_lon, r["lat"], r["lon"]), axis=1
        )
        assets_df = assets_df.sort_values(by="distance_km").reset_index(drop=True)

        # Distances to specific categories
        settlements = assets_df[assets_df["asset_type"] == "SETTLEMENT"]
        min_settlement_km = float(settlements["distance_km"].min()) if not settlements.empty else 25.0

        hospitals = assets_df[assets_df["asset_type"] == "HOSPITAL"]
        min_hospital_km = float(hospitals["distance_km"].min()) if not hospitals.empty else 50.0

        protected = assets_df[assets_df["is_protected_area"] == True]
        min_protected_km = float(protected["distance_km"].min()) if not protected.empty else 50.0

        # Assets within 15 km impact buffer
        threatened_assets = assets_df[assets_df["distance_km"] <= 15.0]
        infra_at_risk = []
        pop_at_risk = 0

        for _, asset in threatened_assets.iterrows():
            d = asset["distance_km"]
            name = asset["asset_name"]
            infra_at_risk.append(f"{name} ({d:.1f} km)")
            
            # Weighted population exposure by distance decay
            if d <= 5.0:
                pop_at_risk += int(asset["estimated_population"])
            elif d <= 15.0:
                pop_at_risk += int(asset["estimated_population"] * (15.0 - d) / 10.0)

        # Check peatland presence from nearest assets or coordinates
        is_peatland = bool(threatened_assets["is_peatland"].any()) if not threatened_assets.empty else False

        # Ecosystem Risk
        if min_protected_km <= 5.0 or (is_peatland and fire_intensity == "HIGH"):
            ecosystem_risk = "CRITICAL"
        elif min_protected_km <= 15.0 or is_peatland:
            ecosystem_risk = "HIGH"
        else:
            ecosystem_risk = "MEDIUM"

        # Calculate Composite Impact Score (0 - 100)
        # Factors: Proximity to settlement (30%), Population (25%), Fire Intensity (20%), Peat/Ecosystem (25%)
        score = 0.0

        # Proximity score (closer = higher)
        if min_settlement_km <= 2.0:
            score += 30.0
        elif min_settlement_km <= 5.0:
            score += 20.0
        elif min_settlement_km <= 10.0:
            score += 10.0
        else:
            score += 5.0

        # Population score
        if pop_at_risk >= 10000:
            score += 25.0
        elif pop_at_risk >= 3000:
            score += 18.0
        elif pop_at_risk >= 500:
            score += 10.0
        else:
            score += 5.0

        # Fire Intensity / Area
        intensity_mult = {"HIGH": 20.0, "MEDIUM": 12.0, "LOW": 6.0}.get(fire_intensity, 10.0)
        area_bonus = min(5.0, estimated_area_ha * 0.2)
        score += min(20.0, intensity_mult + area_bonus)

        # Peatland & Ecosystem
        if is_peatland:
            score += 15.0
        if min_protected_km <= 10.0:
            score += 10.0

        impact_score = int(min(100.0, max(1.0, score * fire_probability)))

        # Assign Priority
        if impact_score >= 80 or (min_settlement_km <= 2.5 and fire_probability >= 0.70):
            priority = "CRITICAL"
        elif impact_score >= 55:
            priority = "HIGH"
        elif impact_score >= 30:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        # Smoke exposure heuristic: wind blowing toward settlement
        wind_toward_population = (min_settlement_km <= 8.0 and wind_speed_kph >= 10.0)
        smoke_risk = "HIGH" if wind_toward_population and is_peatland else ("MEDIUM" if min_settlement_km <= 10.0 else "LOW")

        return {
            "incident_id": incident_id,
            "impact_score": impact_score,
            "priority": priority,
            "population_at_risk": pop_at_risk,
            "infrastructure_at_risk": infra_at_risk[:5], # top 5 closest
            "settlement_distance_km": round(min_settlement_km, 2),
            "hospital_distance_km": round(min_hospital_km, 2),
            "ecosystem_risk": ecosystem_risk,
            "smoke_exposure_risk": smoke_risk,
            "wind_toward_population": wind_toward_population,
            "is_peatland_threat": is_peatland
        }
