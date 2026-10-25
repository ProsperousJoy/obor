"""
Warehouse Bootstrapper: Auto-initialize dimension tables for offline / fresh installs.
Guarantees that Water Resource Agent, Impact Agent, and Response System Orchestrator
work out-of-the-box on any machine without requiring manual database downloads.
"""

import logging
from typing import Optional
import duckdb
import pandas as pd

from src.data.spatial import assign_grid_id

logger = logging.getLogger("warehouse.bootstrap")

# Canonical Water Sources matching Module 4
WATER_SOURCES_DATA = [
    {"source_id": "WTR-RIV-01", "source_name": "Sungai Kapuas (Hulu)", "water_type": "RIVER", "province": "Kalimantan Barat", "kabupaten": "Sintang", "lat": 0.050, "lon": 111.490, "capacity_m3": 500000.0, "surface_area_m2": 250000.0, "historical_permanence_score": 1.0, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-RIV-02", "source_name": "Sungai Kapuas (Hilir)", "water_type": "RIVER", "province": "Kalimantan Barat", "kabupaten": "Kubu Raya", "lat": -0.060, "lon": 109.320, "capacity_m3": 800000.0, "surface_area_m2": 400000.0, "historical_permanence_score": 1.0, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-RIV-03", "source_name": "Sungai Kahayan", "water_type": "RIVER", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.215, "lon": 113.925, "capacity_m3": 450000.0, "surface_area_m2": 200000.0, "historical_permanence_score": 0.98, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-RIV-04", "source_name": "Sungai Barito (Marabahan)", "water_type": "RIVER", "province": "Kalimantan Selatan", "kabupaten": "Barito Kuala", "lat": -2.990, "lon": 114.770, "capacity_m3": 950000.0, "surface_area_m2": 600000.0, "historical_permanence_score": 1.0, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-RIV-05", "source_name": "Sungai Mahakam", "water_type": "RIVER", "province": "Kalimantan Timur", "kabupaten": "Kutai Kartanegara", "lat": -0.450, "lon": 117.020, "capacity_m3": 900000.0, "surface_area_m2": 550000.0, "historical_permanence_score": 1.0, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-RIV-06", "source_name": "Sungai Martapura", "water_type": "RIVER", "province": "Kalimantan Selatan", "kabupaten": "Banjar", "lat": -3.320, "lon": 114.610, "capacity_m3": 350000.0, "surface_area_m2": 150000.0, "historical_permanence_score": 0.95, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-RIV-07", "source_name": "Sungai Kayan", "water_type": "RIVER", "province": "Kalimantan Utara", "kabupaten": "Bulungan", "lat": 2.850, "lon": 117.360, "capacity_m3": 600000.0, "surface_area_m2": 300000.0, "historical_permanence_score": 1.0, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-RIV-08", "source_name": "Sungai Mentaya", "water_type": "RIVER", "province": "Kalimantan Tengah", "kabupaten": "Kotawaringin Timur", "lat": -2.530, "lon": 112.950, "capacity_m3": 400000.0, "surface_area_m2": 180000.0, "historical_permanence_score": 0.95, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-EMB-01", "source_name": "Embung Gambut Sebangau 01", "water_type": "EMBUNG", "province": "Kalimantan Tengah", "kabupaten": "Pulang Pisau", "lat": -2.450, "lon": 114.050, "capacity_m3": 15000.0, "surface_area_m2": 8000.0, "historical_permanence_score": 0.88, "pump_accessible": True, "terrain_difficulty": "MODERATE"},
    {"source_id": "WTR-EMB-02", "source_name": "Embung Gambut Sebangau 02", "water_type": "EMBUNG", "province": "Kalimantan Tengah", "kabupaten": "Pulang Pisau", "lat": -2.580, "lon": 114.120, "capacity_m3": 12000.0, "surface_area_m2": 6500.0, "historical_permanence_score": 0.82, "pump_accessible": True, "terrain_difficulty": "MODERATE"},
    {"source_id": "WTR-EMB-03", "source_name": "Embung Gambut Liang Anggang", "water_type": "EMBUNG", "province": "Kalimantan Selatan", "kabupaten": "Banjarbaru", "lat": -3.460, "lon": 114.730, "capacity_m3": 18000.0, "surface_area_m2": 9500.0, "historical_permanence_score": 0.90, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-EMB-04", "source_name": "Embung Gambut Rasau Jaya", "water_type": "EMBUNG", "province": "Kalimantan Barat", "kabupaten": "Kubu Raya", "lat": -0.180, "lon": 109.390, "capacity_m3": 20000.0, "surface_area_m2": 10000.0, "historical_permanence_score": 0.89, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-CAN-01", "source_name": "Saluran Primer Induk Eks-PLG Blok A", "water_type": "CANAL", "province": "Kalimantan Tengah", "kabupaten": "Kapuas", "lat": -2.850, "lon": 114.450, "capacity_m3": 85000.0, "surface_area_m2": 45000.0, "historical_permanence_score": 0.85, "pump_accessible": True, "terrain_difficulty": "MODERATE"},
    {"source_id": "WTR-CAN-02", "source_name": "Kanal Peatland Kalampangan", "water_type": "CANAL", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.310, "lon": 113.980, "capacity_m3": 35000.0, "surface_area_m2": 18000.0, "historical_permanence_score": 0.80, "pump_accessible": True, "terrain_difficulty": "EASY"},
    {"source_id": "WTR-LAK-01", "source_name": "Danau Sentarum", "water_type": "LAKE", "province": "Kalimantan Barat", "kabupaten": "Kapuas Hulu", "lat": 0.850, "lon": 112.080, "capacity_m3": 1200000.0, "surface_area_m2": 800000.0, "historical_permanence_score": 0.95, "pump_accessible": True, "terrain_difficulty": "MODERATE"},
    {"source_id": "WTR-LAK-02", "source_name": "Danau Jempang", "water_type": "LAKE", "province": "Kalimantan Timur", "kabupaten": "Kutai Barat", "lat": -0.420, "lon": 116.180, "capacity_m3": 750000.0, "surface_area_m2": 500000.0, "historical_permanence_score": 0.92, "pump_accessible": True, "terrain_difficulty": "MODERATE"},
    {"source_id": "WTR-LAK-03", "source_name": "Danau Sembuluh", "water_type": "LAKE", "province": "Kalimantan Tengah", "kabupaten": "Seruyan", "lat": -2.580, "lon": 112.550, "capacity_m3": 900000.0, "surface_area_m2": 600000.0, "historical_permanence_score": 0.97, "pump_accessible": True, "terrain_difficulty": "EASY"}
]

# Canonical Responder Daops HQs matching Module 5
RESPONDER_HQ_DATA = [
    {"hq_id": "HQ-MA-KT-01", "hq_name": "Manggala Agni Daops Palangka Raya", "agency": "MANGGALA_AGNI", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.2065, "lon": 113.9165, "crew_available": 30, "crew_on_duty": 18, "fire_trucks": 4, "portable_pumps": 8, "water_tankers": 2, "drones": 2, "helicopter_available": True, "radio_channel": "VHF-142.500MHz", "phone_contact": "+62-536-3221234"},
    {"hq_id": "HQ-MA-KT-02", "hq_name": "Manggala Agni Daops Kapuas", "agency": "MANGGALA_AGNI", "province": "Kalimantan Tengah", "kabupaten": "Kapuas", "lat": -3.0092, "lon": 114.3876, "crew_available": 25, "crew_on_duty": 15, "fire_trucks": 3, "portable_pumps": 6, "water_tankers": 2, "drones": 1, "helicopter_available": False, "radio_channel": "VHF-142.600MHz", "phone_contact": "+62-536-3225678"},
    {"hq_id": "HQ-MA-KT-03", "hq_name": "Manggala Agni Daops Kotawaringin Barat", "agency": "MANGGALA_AGNI", "province": "Kalimantan Tengah", "kabupaten": "Kotawaringin Barat", "lat": -2.6833, "lon": 111.6167, "crew_available": 20, "crew_on_duty": 12, "fire_trucks": 2, "portable_pumps": 5, "water_tankers": 1, "drones": 1, "helicopter_available": False, "radio_channel": "VHF-142.700MHz", "phone_contact": "+62-532-21234"},
    {"hq_id": "HQ-MA-KT-04", "hq_name": "Manggala Agni Daops Muara Teweh", "agency": "MANGGALA_AGNI", "province": "Kalimantan Tengah", "kabupaten": "Barito Utara", "lat": -0.9500, "lon": 114.8833, "crew_available": 18, "crew_on_duty": 10, "fire_trucks": 2, "portable_pumps": 4, "water_tankers": 1, "drones": 1, "helicopter_available": False, "radio_channel": "VHF-142.800MHz", "phone_contact": "+62-538-21098"},
    {"hq_id": "HQ-MA-KB-01", "hq_name": "Manggala Agni Daops Pontianak", "agency": "MANGGALA_AGNI", "province": "Kalimantan Barat", "kabupaten": "Kubu Raya", "lat": -0.0500, "lon": 109.3500, "crew_available": 30, "crew_on_duty": 18, "fire_trucks": 4, "portable_pumps": 8, "water_tankers": 2, "drones": 2, "helicopter_available": True, "radio_channel": "VHF-143.100MHz", "phone_contact": "+62-561-734567"},
    {"hq_id": "HQ-MA-KB-02", "hq_name": "Manggala Agni Daops Ketapang", "agency": "MANGGALA_AGNI", "province": "Kalimantan Barat", "kabupaten": "Ketapang", "lat": -1.8333, "lon": 109.9833, "crew_available": 25, "crew_on_duty": 14, "fire_trucks": 3, "portable_pumps": 6, "water_tankers": 1, "drones": 1, "helicopter_available": False, "radio_channel": "VHF-143.200MHz", "phone_contact": "+62-534-32111"},
    {"hq_id": "HQ-MA-KB-03", "hq_name": "Manggala Agni Daops Sintang", "agency": "MANGGALA_AGNI", "province": "Kalimantan Barat", "kabupaten": "Sintang", "lat": 0.0667, "lon": 111.5000, "crew_available": 20, "crew_on_duty": 12, "fire_trucks": 2, "portable_pumps": 5, "water_tankers": 1, "drones": 1, "helicopter_available": False, "radio_channel": "VHF-143.300MHz", "phone_contact": "+62-565-21444"},
    {"hq_id": "HQ-MA-KS-01", "hq_name": "Manggala Agni Daops Banjar", "agency": "MANGGALA_AGNI", "province": "Kalimantan Selatan", "kabupaten": "Banjar / Banjarbaru", "lat": -3.4500, "lon": 114.8333, "crew_available": 30, "crew_on_duty": 18, "fire_trucks": 4, "portable_pumps": 8, "water_tankers": 3, "drones": 2, "helicopter_available": True, "radio_channel": "VHF-143.500MHz", "phone_contact": "+62-511-4772345"},
    {"hq_id": "HQ-MA-KS-02", "hq_name": "Manggala Agni Daops Tanah Laut", "agency": "MANGGALA_AGNI", "province": "Kalimantan Selatan", "kabupaten": "Tanah Laut", "lat": -3.8000, "lon": 114.7833, "crew_available": 20, "crew_on_duty": 12, "fire_trucks": 2, "portable_pumps": 5, "water_tankers": 1, "drones": 1, "helicopter_available": False, "radio_channel": "VHF-143.600MHz", "phone_contact": "+62-512-21888"},
    {"hq_id": "HQ-MA-KI-01", "hq_name": "Manggala Agni Daops Samarinda", "agency": "MANGGALA_AGNI", "province": "Kalimantan Timur", "kabupaten": "Samarinda", "lat": -0.5014, "lon": 117.1536, "crew_available": 25, "crew_on_duty": 15, "fire_trucks": 3, "portable_pumps": 6, "water_tankers": 2, "drones": 1, "helicopter_available": False, "radio_channel": "VHF-144.100MHz", "phone_contact": "+62-541-741234"},
    {"hq_id": "HQ-MA-KI-02", "hq_name": "Manggala Agni Daops Paser", "agency": "MANGGALA_AGNI", "province": "Kalimantan Timur", "kabupaten": "Paser", "lat": -1.8667, "lon": 116.1500, "crew_available": 20, "crew_on_duty": 10, "fire_trucks": 2, "portable_pumps": 4, "water_tankers": 1, "drones": 1, "helicopter_available": False, "radio_channel": "VHF-144.200MHz", "phone_contact": "+62-543-21999"},
    {"hq_id": "HQ-MA-KU-01", "hq_name": "Manggala Agni Daops Bulungan / Tarakan", "agency": "MANGGALA_AGNI", "province": "Kalimantan Utara", "kabupaten": "Bulungan", "lat": 2.8400, "lon": 117.3700, "crew_available": 20, "crew_on_duty": 12, "fire_trucks": 2, "portable_pumps": 5, "water_tankers": 1, "drones": 1, "helicopter_available": False, "radio_channel": "VHF-144.500MHz", "phone_contact": "+62-552-21333"}
]

# Canonical Vulnerable Assets matching Module 3
VULNERABLE_ASSETS_DATA = [
    {"asset_id": "AST-SET-01", "asset_name": "Pemukiman Sebangau Permai", "asset_type": "SETTLEMENT", "province": "Kalimantan Tengah", "kabupaten": "Pulang Pisau", "lat": -2.480, "lon": 114.070, "estimated_population": 4200, "is_peatland": True, "is_protected_area": False},
    {"asset_id": "AST-SET-02", "asset_name": "Kawasan Transmigrasi Kalampangan", "asset_type": "SETTLEMENT", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.320, "lon": 113.970, "estimated_population": 6800, "is_peatland": True, "is_protected_area": False},
    {"asset_id": "AST-SET-03", "asset_name": "Pemukiman Liang Anggang Selatan", "asset_type": "SETTLEMENT", "province": "Kalimantan Selatan", "kabupaten": "Banjarbaru", "lat": -3.470, "lon": 114.720, "estimated_population": 9100, "is_peatland": True, "is_protected_area": False},
    {"asset_id": "AST-SET-04", "asset_name": "Kawasan Pemukiman Rasau Jaya Tiga", "asset_type": "SETTLEMENT", "province": "Kalimantan Barat", "kabupaten": "Kubu Raya", "lat": -0.220, "lon": 109.420, "estimated_population": 5400, "is_peatland": True, "is_protected_area": False},
    {"asset_id": "AST-SET-05", "asset_name": "Desa Gambut Jaya Sampit", "asset_type": "SETTLEMENT", "province": "Kalimantan Tengah", "kabupaten": "Kotawaringin Timur", "lat": -2.520, "lon": 112.920, "estimated_population": 3800, "is_peatland": True, "is_protected_area": False},
    {"asset_id": "AST-HSP-01", "asset_name": "RSUD Pulang Pisau", "asset_type": "HOSPITAL", "province": "Kalimantan Tengah", "kabupaten": "Pulang Pisau", "lat": -2.750, "lon": 114.240, "estimated_population": 1500, "is_peatland": True, "is_protected_area": False},
    {"asset_id": "AST-HSP-02", "asset_name": "RSUD dr. Doris Sylvanus", "asset_type": "HOSPITAL", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.210, "lon": 113.918, "estimated_population": 2800, "is_peatland": False, "is_protected_area": False},
    {"asset_id": "AST-HSP-03", "asset_name": "RSUD Idaman Banjarbaru", "asset_type": "HOSPITAL", "province": "Kalimantan Selatan", "kabupaten": "Banjarbaru", "lat": -3.455, "lon": 114.830, "estimated_population": 1900, "is_peatland": False, "is_protected_area": False},
    {"asset_id": "AST-INF-01", "asset_name": "Bandara Tjilik Riwut Palangka Raya", "asset_type": "CRITICAL_INFRA", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.225, "lon": 113.945, "estimated_population": 850, "is_peatland": True, "is_protected_area": False},
    {"asset_id": "AST-INF-02", "asset_name": "Bandara Internasional Syamsudin Noor", "asset_type": "CRITICAL_INFRA", "province": "Kalimantan Selatan", "kabupaten": "Banjarbaru", "lat": -3.442, "lon": 114.760, "estimated_population": 1200, "is_peatland": False, "is_protected_area": False},
    {"asset_id": "AST-INF-03", "asset_name": "Gardu Induk PLN Sebangau", "asset_type": "CRITICAL_INFRA", "province": "Kalimantan Tengah", "kabupaten": "Pulang Pisau", "lat": -2.420, "lon": 114.010, "estimated_population": 200, "is_peatland": True, "is_protected_area": False},
    {"asset_id": "AST-SCH-01", "asset_name": "Kompleks Pendidikan Palangka Raya Barat", "asset_type": "SCHOOL", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.230, "lon": 113.895, "estimated_population": 3200, "is_peatland": True, "is_protected_area": False},
    {"asset_id": "AST-SCH-02", "asset_name": "Kampus Terpadu UNLAM Banjarbaru", "asset_type": "SCHOOL", "province": "Kalimantan Selatan", "kabupaten": "Banjarbaru", "lat": -3.442, "lon": 114.845, "estimated_population": 8500, "is_peatland": False, "is_protected_area": False},
    {"asset_id": "AST-PRT-01", "asset_name": "Taman Nasional Sebangau (Kubah Gambut)", "asset_type": "PROTECTED_FOREST", "province": "Kalimantan Tengah", "kabupaten": "Katingan / Pulang Pisau", "lat": -2.550, "lon": 113.750, "estimated_population": 450, "is_peatland": True, "is_protected_area": True},
    {"asset_id": "AST-PRT-02", "asset_name": "Taman Nasional Tanjung Puting", "asset_type": "PROTECTED_FOREST", "province": "Kalimantan Tengah", "kabupaten": "Kotawaringin Barat", "lat": -3.050, "lon": 111.950, "estimated_population": 250, "is_peatland": True, "is_protected_area": True},
    {"asset_id": "AST-PRT-03", "asset_name": "Taman Nasional Betung Kerihun", "asset_type": "PROTECTED_FOREST", "province": "Kalimantan Barat", "kabupaten": "Kapuas Hulu", "lat": 1.150, "lon": 113.200, "estimated_population": 120, "is_peatland": False, "is_protected_area": True},
    {"asset_id": "AST-PRT-04", "asset_name": "Taman Nasional Kutai", "asset_type": "PROTECTED_FOREST", "province": "Kalimantan Timur", "kabupaten": "Kutai Timur", "lat": 0.450, "lon": 117.250, "estimated_population": 300, "is_peatland": False, "is_protected_area": True}
]


def bootstrap_response_warehouse(conn: duckdb.DuckDBPyConnection) -> None:
    """
    Ensure all response system dimension and fact tables exist and are populated.
    Called on-demand when agents initialize or query tables.
    """
    try:
        tables = set(conn.execute("SHOW TABLES").df()["name"].tolist())
    except Exception:
        tables = set()

    # 1. dim_grid minimal stub (needed by foreign key relations)
    if "dim_grid" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_grid (
                grid_id VARCHAR PRIMARY KEY,
                centroid_lat DOUBLE,
                centroid_lon DOUBLE,
                province VARCHAR,
                is_land BOOLEAN DEFAULT TRUE
            );
        """)

    # 2. dim_water_sources
    if "dim_water_sources" not in tables or conn.execute("SELECT COUNT(*) FROM dim_water_sources").fetchone()[0] == 0:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_water_sources (
                source_id VARCHAR PRIMARY KEY,
                source_name VARCHAR NOT NULL,
                water_type VARCHAR NOT NULL,
                province VARCHAR NOT NULL,
                kabupaten VARCHAR NOT NULL,
                lat DOUBLE NOT NULL,
                lon DOUBLE NOT NULL,
                nearest_grid_id VARCHAR,
                capacity_m3 DOUBLE NOT NULL,
                surface_area_m2 DOUBLE NOT NULL,
                historical_permanence_score DOUBLE DEFAULT 0.85,
                pump_accessible BOOLEAN DEFAULT TRUE,
                terrain_difficulty VARCHAR DEFAULT 'MODERATE'
            );
        """)
        df_wtr = pd.DataFrame(WATER_SOURCES_DATA)
        df_wtr["nearest_grid_id"] = df_wtr.apply(lambda r: assign_grid_id(r["lat"], r["lon"]), axis=1)
        conn.register("stage_wtr", df_wtr)
        conn.execute("INSERT OR REPLACE INTO dim_water_sources BY NAME SELECT * FROM stage_wtr")
        conn.unregister("stage_wtr")

    # 3. dim_responder_hq
    if "dim_responder_hq" not in tables or conn.execute("SELECT COUNT(*) FROM dim_responder_hq").fetchone()[0] == 0:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_responder_hq (
                hq_id VARCHAR PRIMARY KEY,
                hq_name VARCHAR NOT NULL,
                agency VARCHAR NOT NULL,
                province VARCHAR NOT NULL,
                kabupaten VARCHAR NOT NULL,
                lat DOUBLE NOT NULL,
                lon DOUBLE NOT NULL,
                nearest_grid_id VARCHAR,
                crew_available INTEGER DEFAULT 10,
                crew_on_duty INTEGER DEFAULT 6,
                fire_trucks INTEGER DEFAULT 2,
                portable_pumps INTEGER DEFAULT 4,
                water_tankers INTEGER DEFAULT 1,
                drones INTEGER DEFAULT 1,
                helicopter_available BOOLEAN DEFAULT FALSE,
                radio_channel VARCHAR DEFAULT 'VHF-142.500MHz',
                phone_contact VARCHAR NOT NULL
            );
        """)
        df_hq = pd.DataFrame(RESPONDER_HQ_DATA)
        df_hq["nearest_grid_id"] = df_hq.apply(lambda r: assign_grid_id(r["lat"], r["lon"]), axis=1)
        conn.register("stage_hq", df_hq)
        conn.execute("INSERT OR REPLACE INTO dim_responder_hq BY NAME SELECT * FROM stage_hq")
        conn.unregister("stage_hq")

    # 4. dim_vulnerable_assets
    if "dim_vulnerable_assets" not in tables or conn.execute("SELECT COUNT(*) FROM dim_vulnerable_assets").fetchone()[0] == 0:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_vulnerable_assets (
                asset_id VARCHAR PRIMARY KEY,
                asset_name VARCHAR NOT NULL,
                asset_type VARCHAR NOT NULL,
                province VARCHAR NOT NULL,
                kabupaten VARCHAR NOT NULL,
                lat DOUBLE NOT NULL,
                lon DOUBLE NOT NULL,
                nearest_grid_id VARCHAR,
                estimated_population INTEGER DEFAULT 0,
                is_peatland BOOLEAN DEFAULT FALSE,
                is_protected_area BOOLEAN DEFAULT FALSE
            );
        """)
        df_ast = pd.DataFrame(VULNERABLE_ASSETS_DATA)
        df_ast["nearest_grid_id"] = df_ast.apply(lambda r: assign_grid_id(r["lat"], r["lon"]), axis=1)
        conn.register("stage_ast", df_ast)
        conn.execute("INSERT OR REPLACE INTO dim_vulnerable_assets BY NAME SELECT * FROM stage_ast")
        conn.unregister("stage_ast")

    # 5. fact_incident_records
    if "fact_incident_records" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fact_incident_records (
                incident_id VARCHAR PRIMARY KEY,
                plan_id VARCHAR NOT NULL,
                target_datetime TIMESTAMP NOT NULL,
                grid_id VARCHAR,
                fire_probability DOUBLE NOT NULL,
                fire_intensity VARCHAR NOT NULL,
                impact_score INTEGER NOT NULL,
                priority VARCHAR NOT NULL,
                recommended_action VARCHAR NOT NULL,
                assigned_hq_id VARCHAR,
                assigned_water_id VARCHAR,
                eta_minutes INTEGER NOT NULL,
                steps_json VARCHAR,
                authorization_level VARCHAR NOT NULL,
                execution_status VARCHAR NOT NULL,
                replan_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

    # 6. fact_incident_feedback
    if "fact_incident_feedback" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fact_incident_feedback (
                feedback_id VARCHAR PRIMARY KEY,
                incident_id VARCHAR,
                real_fire_confirmed BOOLEAN NOT NULL,
                actual_lat DOUBLE,
                actual_lon DOUBLE,
                actual_burn_area_ha DOUBLE,
                actual_response_time_min INTEGER,
                actual_water_source_used VARCHAR,
                prediction_error DOUBLE,
                plan_success_score DOUBLE,
                water_accuracy_score DOUBLE,
                retraining_candidate BOOLEAN DEFAULT FALSE,
                feedback_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
