"""
Module 5 — Resource Agent
-------------------------
Answers: 'Who and what is available to respond to the wildfire?'
Identifies the nearest Daops Manggala Agni / BPBD responder post,
matches available personnel & equipment to fire priority, and calculates ETA.
"""

from typing import Dict, Any, List
import math
import duckdb

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes Great Circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    return R * 2.0 * math.asin(math.sqrt(a))

class ResourceAgent:
    """
    Allocates firefighting personnel and equipment from dim_responder_hq.
    """
    def __init__(self, db_path: str = "data/warehouse/wildfire.duckdb"):
        self.db_path = db_path

    def allocate_resources(
        self,
        incident_id: str,
        fire_lat: float,
        fire_lon: float,
        priority: str = "MEDIUM",
        fire_intensity: str = "MEDIUM",
        estimated_area_ha: float = 5.0,
        conn: duckdb.DuckDBPyConnection = None
    ) -> Dict[str, Any]:
        """
        Selects nearest responder station and computes required resources.
        """
        close_conn = False
        if conn is None:
            conn = duckdb.connect(self.db_path, read_only=True)
            close_conn = True

        df = conn.execute("""
            SELECT hq_id, hq_name, agency, province, kabupaten,
                   lat, lon, crew_available, crew_on_duty,
                   fire_trucks, portable_pumps, water_tankers, drones,
                   helicopter_available, radio_channel, phone_contact
            FROM dim_responder_hq
        """).df()

        if close_conn:
            conn.close()

        if df.empty:
            raise ValueError("No responder headquarters found in dim_responder_hq table.")

        # Compute distances
        df["distance_km"] = df.apply(
            lambda r: haversine_km(fire_lat, fire_lon, r["lat"], r["lon"]), axis=1
        )
        df = df.sort_values(by="distance_km").reset_index(drop=True)
        primary_hq = df.iloc[0]

        # Dispatch logistics estimation
        dist_km = float(primary_hq["distance_km"])
        # Average road speed ~40 km/h with 10 min muster time
        eta_minutes = int(10 + (dist_km / 40.0 * 60.0))

        # Crew sizing heuristic based on priority and fire size
        if priority == "CRITICAL" or estimated_area_ha >= 20.0:
            recommended_crew = 12
            rec_pumps = 4
            rec_tankers = 2
            rec_drones = 1
        elif priority == "HIGH" or estimated_area_ha >= 10.0:
            recommended_crew = 8
            rec_pumps = 3
            rec_tankers = 1
            rec_drones = 1
        elif priority == "MEDIUM":
            recommended_crew = 6
            rec_pumps = 2
            rec_tankers = 1
            rec_drones = 1
        else: # LOW
            recommended_crew = 4
            rec_pumps = 1
            rec_tankers = 0
            rec_drones = 0

        # Check equipment sufficiency
        allocated_equipment = {
            "fire_truck": min(int(primary_hq["fire_trucks"]), 2),
            "portable_pump": min(int(primary_hq["portable_pumps"]), rec_pumps),
            "water_tanker": min(int(primary_hq["water_tankers"]), rec_tankers),
            "drone": min(int(primary_hq["drones"]), rec_drones)
        }

        missing_equipment = []
        if allocated_equipment["portable_pump"] < rec_pumps:
            missing_equipment.append(f"{rec_pumps - allocated_equipment['portable_pump']} additional pumps")
        if allocated_equipment["water_tanker"] < rec_tankers:
            missing_equipment.append("water tanker")
        if priority == "CRITICAL" and not primary_hq["helicopter_available"]:
            missing_equipment.append("water bombing helicopter")

        # Readiness score based on crew availability and proximity
        crew_ratio = min(1.0, float(primary_hq["crew_available"]) / recommended_crew)
        dist_factor = max(0.2, 1.0 - (dist_km / 120.0))
        readiness_score = round(0.55 * crew_ratio + 0.45 * dist_factor, 2)

        return {
            "incident_id": incident_id,
            "hq_id": primary_hq["hq_id"],
            "hq": primary_hq["hq_name"],
            "agency": primary_hq["agency"],
            "hq_lat": round(float(primary_hq["lat"]), 4),
            "hq_lon": round(float(primary_hq["lon"]), 4),
            "distance_km": round(dist_km, 2),
            "eta_minutes": eta_minutes,
            "available_crew": int(primary_hq["crew_available"]),
            "recommended_crew": recommended_crew,
            "equipment": allocated_equipment,
            "missing_equipment": missing_equipment,
            "hq_contact": primary_hq["phone_contact"],
            "radio_channel": primary_hq["radio_channel"],
            "readiness_score": readiness_score
        }
