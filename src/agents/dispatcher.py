"""Emergency Dispatcher — Manggala Agni & BPBD Incident Dispatch Allocation."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import math
import random
import sqlite3
import time
from typing import Optional, List, Dict, Any
import uuid
import duckdb

from src.config import config

logger = logging.getLogger("wildfire.dispatcher")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two coordinates in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    return R * 2.0 * math.asin(math.sqrt(max(0.0, a)))


# ─── 12 Manggala Agni Daops Headquarters (synchronized with dim_responder_hq) ──

MANGGALA_AGNI_DAOPS = [
    {"hq_id": "HQ-MA-KT-01", "name": "Daops Manggala Agni Palangka Raya", "agency": "MANGGALA_AGNI", "province": "Kalimantan Tengah", "regency": "Kota Palangka Raya", "lat": -2.2065, "lon": 113.9165, "crew": 18, "radio": "VHF-142.500MHz"},
    {"hq_id": "HQ-MA-KT-02", "name": "Daops Manggala Agni Kapuas", "agency": "MANGGALA_AGNI", "province": "Kalimantan Tengah", "regency": "Kapuas", "lat": -3.0092, "lon": 114.3876, "crew": 15, "radio": "VHF-142.600MHz"},
    {"hq_id": "HQ-MA-KT-03", "name": "Daops Manggala Agni Kotawaringin Barat", "agency": "MANGGALA_AGNI", "province": "Kalimantan Tengah", "regency": "Kotawaringin Barat", "lat": -2.6833, "lon": 111.6167, "crew": 12, "radio": "VHF-142.700MHz"},
    {"hq_id": "HQ-MA-KT-04", "name": "Daops Manggala Agni Muara Teweh", "agency": "MANGGALA_AGNI", "province": "Kalimantan Tengah", "regency": "Barito Utara", "lat": -0.9500, "lon": 114.8833, "crew": 10, "radio": "VHF-142.800MHz"},
    {"hq_id": "HQ-MA-KB-01", "name": "Daops Manggala Agni Pontianak", "agency": "MANGGALA_AGNI", "province": "Kalimantan Barat", "regency": "Kubu Raya", "lat": -0.0500, "lon": 109.3500, "crew": 18, "radio": "VHF-143.100MHz"},
    {"hq_id": "HQ-MA-KB-02", "name": "Daops Manggala Agni Ketapang", "agency": "MANGGALA_AGNI", "province": "Kalimantan Barat", "regency": "Ketapang", "lat": -1.8333, "lon": 109.9833, "crew": 14, "radio": "VHF-143.200MHz"},
    {"hq_id": "HQ-MA-KB-03", "name": "Daops Manggala Agni Sintang", "agency": "MANGGALA_AGNI", "province": "Kalimantan Barat", "regency": "Sintang", "lat": 0.0667, "lon": 111.5000, "crew": 12, "radio": "VHF-143.300MHz"},
    {"hq_id": "HQ-MA-KS-01", "name": "Daops Manggala Agni Banjar", "agency": "MANGGALA_AGNI", "province": "Kalimantan Selatan", "regency": "Banjar / Banjarbaru", "lat": -3.4500, "lon": 114.8333, "crew": 18, "radio": "VHF-143.500MHz"},
    {"hq_id": "HQ-MA-KS-02", "name": "Daops Manggala Agni Tanah Laut", "agency": "MANGGALA_AGNI", "province": "Kalimantan Selatan", "regency": "Tanah Laut", "lat": -3.8000, "lon": 114.7833, "crew": 12, "radio": "VHF-143.600MHz"},
    {"hq_id": "HQ-MA-KI-01", "name": "Daops Manggala Agni Samarinda", "agency": "MANGGALA_AGNI", "province": "Kalimantan Timur", "regency": "Samarinda", "lat": -0.5014, "lon": 117.1536, "crew": 15, "radio": "VHF-144.100MHz"},
    {"hq_id": "HQ-MA-KI-02", "name": "Daops Manggala Agni Paser", "agency": "MANGGALA_AGNI", "province": "Kalimantan Timur", "regency": "Paser", "lat": -1.8667, "lon": 116.1500, "crew": 10, "radio": "VHF-144.200MHz"},
    {"hq_id": "HQ-MA-KU-01", "name": "Daops Manggala Agni Bulungan / Tarakan", "agency": "MANGGALA_AGNI", "province": "Kalimantan Utara", "regency": "Bulungan", "lat": 2.8400, "lon": 117.3700, "crew": 12, "radio": "VHF-144.500MHz"},
]

# ─── Strategic Water Sources (synchronized with dim_water_sources) ───────────

STRATEGIC_WATER_SOURCES = [
    {"source_id": "WTR-RIV-03", "name": "Sungai Kahayan", "type": "RIVER", "lat": -2.215, "lon": 113.925, "capacity_m3": 450000.0, "province": "Kalimantan Tengah"},
    {"source_id": "WTR-LAK-03", "name": "Danau Sembuluh", "type": "LAKE", "lat": -2.580, "lon": 112.550, "capacity_m3": 900000.0, "province": "Kalimantan Tengah"},
    {"source_id": "WTR-EMB-01", "name": "Embung Gambut Sebangau 01", "type": "EMBUNG", "lat": -2.450, "lon": 114.050, "capacity_m3": 15000.0, "province": "Kalimantan Tengah"},
    {"source_id": "WTR-RIV-02", "name": "Sungai Kapuas (Hilir)", "type": "RIVER", "lat": -0.060, "lon": 109.320, "capacity_m3": 800000.0, "province": "Kalimantan Barat"},
    {"source_id": "WTR-CAN-01", "name": "Saluran Primer Induk Eks-PLG", "type": "CANAL", "lat": -2.850, "lon": 114.450, "capacity_m3": 85000.0, "province": "Kalimantan Tengah"},
    {"source_id": "WTR-RIV-04", "name": "Sungai Barito (Marabahan)", "type": "RIVER", "lat": -2.990, "lon": 114.770, "capacity_m3": 950000.0, "province": "Kalimantan Selatan"},
    {"source_id": "WTR-RIV-05", "name": "Sungai Mahakam", "type": "RIVER", "lat": -0.450, "lon": 117.020, "capacity_m3": 900000.0, "province": "Kalimantan Timur"},
    {"source_id": "WTR-RIV-07", "name": "Sungai Kayan", "type": "RIVER", "lat": 2.850, "lon": 117.360, "capacity_m3": 600000.0, "province": "Kalimantan Utara"},
]

RESOURCE_TYPES = {
    "regu_manggala_agni": {
        "name": "Regu Pemadam Manggala Agni (Ground Crew)",
        "personnel": 6,
        "icon": "👨‍🚒"
    },
    "pompa_jinjing": {
        "name": "Unit Pompa Jinjing & Selang Peatland",
        "personnel": 2,
        "icon": "🚒"
    },
    "mobil_tangki": {
        "name": "Mobil Tangki Suplai Air (5000L)",
        "personnel": 2,
        "icon": "🚚"
    },
    "drone_thermal": {
        "name": "Drone Pantau Termal Karhutla",
        "personnel": 2,
        "icon": "🚁"
    },
    "helikopter_water_bombing": {
        "name": "Helikopter Water Bombing (BNPB Task Force)",
        "personnel": 3,
        "icon": "🛩️"
    },
    "tim_evakuasi_bpbd": {
        "name": "Tim Reaksi Cepat & Evakuasi BPBD",
        "personnel": 6,
        "icon": "🚑"
    },
    "posko_ics": {
        "name": "Posko Komando Lapangan (ICS Karhutla)",
        "personnel": 10,
        "icon": "📋"
    },
}


@dataclass
class DispatchReport:
    """A structured emergency dispatch report."""
    dispatch_id: str
    timestamp: str
    fire_id: str
    fire_name: str
    severity: str
    location: dict
    nearest_station: str
    assigned_hq_id: str
    nearest_water_source: str
    assigned_water_id: str
    resources_deployed: list[dict]
    total_personnel: int
    estimated_response_time_min: int
    priority_code: str
    evacuation_advisory: bool
    notes: str

    def to_dict(self) -> dict:
        return {
            "dispatch_id": self.dispatch_id,
            "timestamp": self.timestamp,
            "fire_id": self.fire_id,
            "fire_name": self.fire_name,
            "severity": self.severity,
            "location": self.location,
            "nearest_station": self.nearest_station,
            "assigned_hq_id": self.assigned_hq_id,
            "nearest_water_source": self.nearest_water_source,
            "assigned_water_id": self.assigned_water_id,
            "resources_deployed": self.resources_deployed,
            "total_personnel": self.total_personnel,
            "estimated_response_time_min": self.estimated_response_time_min,
            "priority_code": self.priority_code,
            "evacuation_advisory": self.evacuation_advisory,
            "notes": self.notes,
        }


class EmergencyDispatcher:
    """
    Emergency Dispatcher for Manggala Agni and BPBD fire response.
    Connects to DuckDB Data Warehouse for station and water source optimization.
    """

    def __init__(self):
        self.dispatch_history: list = []
        self._last_dispatch: dict[str, float] = {}
        self._load_warehouse_dimensions()
        self._preload_historical_dispatches()

    def _preload_historical_dispatches(self):
        """Preload recent dispatches from SQLite if available."""
        try:
            con = sqlite3.connect(config.DB_PATH)
            con.row_factory = sqlite3.Row
            rows = con.cursor().execute(
                "SELECT * FROM alerts WHERE dispatched = 1 ORDER BY timestamp ASC LIMIT 50"
            ).fetchall()
            for r in rows:
                if r["dispatch_details"]:
                    try:
                        d = json.loads(r["dispatch_details"])
                        self.dispatch_history.append(d)
                        fid = d.get("fire_id")
                        ts = d.get("timestamp") or r["timestamp"]
                        if fid and ts:
                            self._last_dispatch[fid] = float(ts)
                    except Exception:
                        pass
            con.close()
            if self.dispatch_history:
                logger.info(f"Preloaded {len(self.dispatch_history)} historical dispatches from database")
        except Exception as e:
            logger.debug(f"Could not preload dispatches: {e}")

    def _load_warehouse_dimensions(self):
        """Load Daops HQs and water sources from DuckDB if available."""
        self.daops_list = MANGGALA_AGNI_DAOPS
        self.water_list = STRATEGIC_WATER_SOURCES

        try:
            conn = duckdb.connect(config.WAREHOUSE_DB_PATH, read_only=True)
            try:
                hq_df = conn.execute("""
                    SELECT hq_id, hq_name, agency, province, kabupaten, lat, lon, crew_available, radio_channel
                    FROM dim_responder_hq
                """).df()
                if not hq_df.empty:
                    self.daops_list = [
                        {
                            "hq_id": row["hq_id"],
                            "name": row["hq_name"],
                            "agency": row["agency"],
                            "province": row["province"],
                            "regency": row["kabupaten"],
                            "lat": float(row["lat"]),
                            "lon": float(row["lon"]),
                            "crew": int(row["crew_available"]),
                            "radio": row.get("radio_channel", "VHF-142.500MHz"),
                        }
                        for _, row in hq_df.iterrows()
                    ]

                w_df = conn.execute("""
                    SELECT source_id, source_name, water_type, lat, lon, capacity_m3, province
                    FROM dim_water_sources
                """).df()
                if not w_df.empty:
                    self.water_list = [
                        {
                            "source_id": row["source_id"],
                            "name": row["source_name"],
                            "type": row["water_type"],
                            "lat": float(row["lat"]),
                            "lon": float(row["lon"]),
                            "capacity_m3": float(row["capacity_m3"]),
                            "province": row["province"],
                        }
                        for _, row in w_df.iterrows()
                    ]
                logger.info(f"Loaded {len(self.daops_list)} Daops HQs and {len(self.water_list)} Water Sources from DuckDB")
            finally:
                conn.close()
        except Exception as e:
            logger.info(f"Using built-in Manggala Agni and Water registry (DuckDB offline: {e})")

    def can_dispatch(self, fire_id: str) -> bool:
        """Enforce cooldown interval to avoid duplicate dispatch calls."""
        last_time = self._last_dispatch.get(fire_id, 0)
        return (time.time() - last_time) > config.DISPATCH_COOLDOWN

    def find_nearest_hq(self, lat: float, lon: float) -> tuple[dict, float]:
        """Find the closest Manggala Agni Daops headquarters."""
        best_hq = self.daops_list[0]
        min_dist = float("inf")
        for hq in self.daops_list:
            d = haversine_km(lat, lon, hq["lat"], hq["lon"])
            if d < min_dist:
                min_dist = d
                best_hq = hq
        return best_hq, min_dist

    def find_nearest_water(self, lat: float, lon: float) -> tuple[dict, float]:
        """Find the closest strategic water source for pumping and tankers."""
        best_water = self.water_list[0]
        min_dist = float("inf")
        for w in self.water_list:
            d = haversine_km(lat, lon, w["lat"], w["lon"])
            if d < min_dist:
                min_dist = d
                best_water = w
        return best_water, min_dist

    def dispatch(
        self,
        fire: dict,
        alert_level: str,
        ai_analysis: Optional[dict] = None
    ) -> DispatchReport:
        """Execute simulated Manggala Agni / BPBD emergency dispatch."""
        fire_id = fire["fire_id"]
        acres = fire.get("daily_acres", 0) or 0
        hectares = fire.get("hectares", acres / 2.47105)
        containment = fire.get("percent_contained", 0) or 0
        lat = fire.get("latitude", 0.0)
        lon = fire.get("longitude", 0.0)
        is_peat = fire.get("is_peatland", False)
        prov = fire.get("province", fire.get("state", "Kalimantan Tengah"))
        county = fire.get("county", "Pulang Pisau")

        severity, resources, priority = self._determine_resources(hectares, containment, alert_level, is_peat)
        nearest_hq, hq_dist_km = self.find_nearest_hq(lat, lon)
        nearest_water, water_dist_km = self.find_nearest_water(lat, lon)

        response_time = int(12 + (hq_dist_km / 35.0 * 60.0))
        evacuation = (hectares > 1000 or (is_peat and hectares > 400)) and containment < 25

        notes_parts = [
            f"Manggala Agni Daops Dispatch [AVF Automated System].",
            f"Incident: {fire.get('name', 'Unknown')} | {hectares:.0f} ha ({acres:.0f} ac) | {containment:.0f}% terkendali.",
            f"Peatland Status: {'🔥 LAHAN GAMBUT KRITIS (Smoldering Peat)' if is_peat else 'Vegetasi Mineral'}.",
            f"Posko Daops: {nearest_hq['name']} ({hq_dist_km:.1f} km, {nearest_hq.get('radio', 'VHF')}).",
            f"Sumber Air Pemadaman: {nearest_water['name']} ({nearest_water['type']}, {water_dist_km:.1f} km).",
        ]
        if ai_analysis and ai_analysis.get("risk_assessment"):
            notes_parts.append(f"AI Risk Assessment: {ai_analysis['risk_assessment']}")
        if evacuation:
            notes_parts.append("🚨 EVAKUASI / PERINGATAN WARGA: Risiko asap pekat gambut (ISPU Berbahaya).")

        dispatch_id = f"ID-MA-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        total_personnel = sum(r.get("personnel", 0) for r in resources)

        report = DispatchReport(
            dispatch_id=dispatch_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            fire_id=fire_id,
            fire_name=fire.get("name", "Unknown Fire"),
            severity=severity,
            location={
                "latitude": lat,
                "longitude": lon,
                "province": prov,
                "county": county,
                "is_peatland": is_peat,
            },
            nearest_station=f"{nearest_hq['name']} ({hq_dist_km:.1f} km)",
            assigned_hq_id=nearest_hq["hq_id"],
            nearest_water_source=f"{nearest_water['name']} ({nearest_water['type']}, {water_dist_km:.1f} km)",
            assigned_water_id=nearest_water["source_id"],
            resources_deployed=resources,
            total_personnel=total_personnel,
            estimated_response_time_min=response_time,
            priority_code=priority,
            evacuation_advisory=evacuation,
            notes=" ".join(notes_parts),
        )

        self.dispatch_history.append(report)
        self._last_dispatch[fire_id] = time.time()

        self._log_to_warehouse(report)

        logger.warning(
            f"🚨 MANGGALA AGNI DISPATCH {dispatch_id}\n"
            f"   Fire: {fire.get('name')} ({hectares:.0f} ha | Peat: {is_peat})\n"
            f"   HQ: {nearest_hq['name']} (ETA: {response_time} min)\n"
            f"   Water: {nearest_water['name']}\n"
            f"   Personnel: {total_personnel} crew | Priority: {priority}"
        )

        return report

    def _log_to_warehouse(self, report: DispatchReport):
        """Append dispatch action to fact_incident_records in DuckDB."""
        try:
            conn = duckdb.connect(config.WAREHOUSE_DB_PATH, read_only=False)
            try:
                conn.execute("""
                    INSERT INTO fact_incident_records (
                        incident_id, plan_id, target_datetime, grid_id,
                        fire_probability, fire_intensity, impact_score,
                        priority, recommended_action, assigned_hq_id,
                        assigned_water_id, eta_minutes, steps_json,
                        authorization_level, execution_status
                    ) VALUES (
                        ?, ?, CURRENT_TIMESTAMP, NULL,
                        0.95, ?, 85,
                        ?, 'GROUND_RESPONSE', ?,
                        ?, ?, ?,
                        'AUTO_MEDIUM', 'EXECUTING'
                    )
                    ON CONFLICT (incident_id) DO UPDATE SET
                        plan_id = EXCLUDED.plan_id,
                        target_datetime = EXCLUDED.target_datetime,
                        fire_intensity = EXCLUDED.fire_intensity,
                        priority = EXCLUDED.priority,
                        assigned_hq_id = EXCLUDED.assigned_hq_id,
                        assigned_water_id = EXCLUDED.assigned_water_id,
                        eta_minutes = EXCLUDED.eta_minutes,
                        steps_json = EXCLUDED.steps_json,
                        execution_status = EXCLUDED.execution_status
                """, [
                    report.dispatch_id,
                    f"PLAN-{report.dispatch_id}",
                    report.severity,
                    report.priority_code,
                    report.assigned_hq_id,
                    report.assigned_water_id,
                    report.estimated_response_time_min,
                    json.dumps(report.resources_deployed)
                ])
                logger.info(f"Recorded dispatch {report.dispatch_id} into DuckDB fact_incident_records")
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"DuckDB incident log skipped ({e})")

    def _determine_resources(
        self, hectares: float, containment: float, alert_level: str, is_peat: bool
    ):
        """Determine required Manggala Agni and BPBD deployment package."""
        if alert_level == "EMERGENCY" and (hectares > 1500 or (is_peat and hectares > 800)):
            severity = "CRITICAL"
            priority = "SIAGA-1 (DARURAT TINGGI)"
            resources = [
                {**RESOURCE_TYPES["posko_ics"], "quantity": 1},
                {**RESOURCE_TYPES["regu_manggala_agni"], "quantity": 4},
                {**RESOURCE_TYPES["pompa_jinjing"], "quantity": 4},
                {**RESOURCE_TYPES["mobil_tangki"], "quantity": 3},
                {**RESOURCE_TYPES["drone_thermal"], "quantity": 2},
                {**RESOURCE_TYPES["helikopter_water_bombing"], "quantity": 2},
            ]
            if containment < 20 or is_peat:
                resources.append({**RESOURCE_TYPES["tim_evakuasi_bpbd"], "quantity": 2})

        elif alert_level == "EMERGENCY" or hectares > 500:
            severity = "HIGH"
            priority = "SIAGA-2 (TANGGAP DARURAT)"
            resources = [
                {**RESOURCE_TYPES["regu_manggala_agni"], "quantity": 2},
                {**RESOURCE_TYPES["pompa_jinjing"], "quantity": 2},
                {**RESOURCE_TYPES["mobil_tangki"], "quantity": 2},
                {**RESOURCE_TYPES["drone_thermal"], "quantity": 1},
                {**RESOURCE_TYPES["helikopter_water_bombing"], "quantity": 1},
            ]

        elif alert_level == "WARNING":
            severity = "MODERATE"
            priority = "SIAGA-3 (WASPADA)"
            resources = [
                {**RESOURCE_TYPES["regu_manggala_agni"], "quantity": 2},
                {**RESOURCE_TYPES["pompa_jinjing"], "quantity": 1},
                {**RESOURCE_TYPES["mobil_tangki"], "quantity": 1},
            ]

        else:
            severity = "LOW"
            priority = "MONITORING RUTIN"
            resources = [
                {**RESOURCE_TYPES["regu_manggala_agni"], "quantity": 1},
            ]

        for r in resources:
            qty = r.pop("quantity", 1)
            r["personnel"] = r["personnel"] * qty
            r["quantity"] = qty
            r["display"] = f"{r['icon']} {qty}× {r['name']} ({r['personnel']} personel)"

        return severity, resources, priority

    def get_recent_dispatches(self, limit: int = 20) -> list[dict]:
        """Get recent dispatch reports."""
        res = []
        for d in self.dispatch_history[-limit:]:
            if isinstance(d, dict):
                res.append(d)
            elif hasattr(d, "to_dict"):
                res.append(d.to_dict())
        return res
