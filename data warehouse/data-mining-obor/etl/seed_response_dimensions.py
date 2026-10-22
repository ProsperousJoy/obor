"""
ETL Seeder: Populate Response System Dimension Tables (Modules 3-5)
------------------------------------------------------------------
Populates dim_responder_hq, dim_water_sources, and dim_vulnerable_assets
with authentic Kalimantan geospatial and operational assets.
"""

import sys
import logging
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etl.load_warehouse import get_connection, assign_grid_id, export_to_parquet

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_response_dimensions")

def seed_responder_hq(conn):
    logger.info("Seeding dim_responder_hq...")
    hqs = [
        # Kalimantan Tengah (High Peat Fire Risk)
        {
            "hq_id": "HQ-MA-KT-01",
            "hq_name": "Manggala Agni Daops Palangka Raya",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Tengah",
            "kabupaten": "Kota Palangka Raya",
            "lat": -2.2065, "lon": 113.9165,
            "crew_available": 30, "crew_on_duty": 18,
            "fire_trucks": 4, "portable_pumps": 8, "water_tankers": 2, "drones": 2,
            "helicopter_available": True,
            "radio_channel": "VHF-142.500MHz", "phone_contact": "+62-536-3221234"
        },
        {
            "hq_id": "HQ-MA-KT-02",
            "hq_name": "Manggala Agni Daops Kapuas",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Tengah",
            "kabupaten": "Kapuas",
            "lat": -3.0092, "lon": 114.3876,
            "crew_available": 25, "crew_on_duty": 15,
            "fire_trucks": 3, "portable_pumps": 6, "water_tankers": 2, "drones": 1,
            "helicopter_available": False,
            "radio_channel": "VHF-142.600MHz", "phone_contact": "+62-536-3225678"
        },
        {
            "hq_id": "HQ-MA-KT-03",
            "hq_name": "Manggala Agni Daops Kotawaringin Barat",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Tengah",
            "kabupaten": "Kotawaringin Barat",
            "lat": -2.6833, "lon": 111.6167,
            "crew_available": 20, "crew_on_duty": 12,
            "fire_trucks": 2, "portable_pumps": 5, "water_tankers": 1, "drones": 1,
            "helicopter_available": False,
            "radio_channel": "VHF-142.700MHz", "phone_contact": "+62-532-21234"
        },
        {
            "hq_id": "HQ-MA-KT-04",
            "hq_name": "Manggala Agni Daops Muara Teweh",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Tengah",
            "kabupaten": "Barito Utara",
            "lat": -0.9500, "lon": 114.8833,
            "crew_available": 18, "crew_on_duty": 10,
            "fire_trucks": 2, "portable_pumps": 4, "water_tankers": 1, "drones": 1,
            "helicopter_available": False,
            "radio_channel": "VHF-142.800MHz", "phone_contact": "+62-538-21098"
        },
        # Kalimantan Barat
        {
            "hq_id": "HQ-MA-KB-01",
            "hq_name": "Manggala Agni Daops Pontianak",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Barat",
            "kabupaten": "Kubu Raya",
            "lat": -0.0500, "lon": 109.3500,
            "crew_available": 30, "crew_on_duty": 18,
            "fire_trucks": 4, "portable_pumps": 8, "water_tankers": 2, "drones": 2,
            "helicopter_available": True,
            "radio_channel": "VHF-143.100MHz", "phone_contact": "+62-561-734567"
        },
        {
            "hq_id": "HQ-MA-KB-02",
            "hq_name": "Manggala Agni Daops Ketapang",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Barat",
            "kabupaten": "Ketapang",
            "lat": -1.8333, "lon": 109.9833,
            "crew_available": 25, "crew_on_duty": 14,
            "fire_trucks": 3, "portable_pumps": 6, "water_tankers": 1, "drones": 1,
            "helicopter_available": False,
            "radio_channel": "VHF-143.200MHz", "phone_contact": "+62-534-32111"
        },
        {
            "hq_id": "HQ-MA-KB-03",
            "hq_name": "Manggala Agni Daops Sintang",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Barat",
            "kabupaten": "Sintang",
            "lat": 0.0667, "lon": 111.5000,
            "crew_available": 20, "crew_on_duty": 12,
            "fire_trucks": 2, "portable_pumps": 5, "water_tankers": 1, "drones": 1,
            "helicopter_available": False,
            "radio_channel": "VHF-143.300MHz", "phone_contact": "+62-565-21444"
        },
        # Kalimantan Selatan
        {
            "hq_id": "HQ-MA-KS-01",
            "hq_name": "Manggala Agni Daops Banjar",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Selatan",
            "kabupaten": "Banjar / Banjarbaru",
            "lat": -3.4500, "lon": 114.8333,
            "crew_available": 30, "crew_on_duty": 18,
            "fire_trucks": 4, "portable_pumps": 8, "water_tankers": 3, "drones": 2,
            "helicopter_available": True,
            "radio_channel": "VHF-143.500MHz", "phone_contact": "+62-511-4772345"
        },
        {
            "hq_id": "HQ-MA-KS-02",
            "hq_name": "Manggala Agni Daops Tanah Laut",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Selatan",
            "kabupaten": "Tanah Laut",
            "lat": -3.8000, "lon": 114.7833,
            "crew_available": 20, "crew_on_duty": 12,
            "fire_trucks": 2, "portable_pumps": 5, "water_tankers": 1, "drones": 1,
            "helicopter_available": False,
            "radio_channel": "VHF-143.600MHz", "phone_contact": "+62-512-21888"
        },
        # Kalimantan Timur
        {
            "hq_id": "HQ-MA-KI-01",
            "hq_name": "Manggala Agni Daops Samarinda",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Timur",
            "kabupaten": "Samarinda",
            "lat": -0.5014, "lon": 117.1536,
            "crew_available": 25, "crew_on_duty": 15,
            "fire_trucks": 3, "portable_pumps": 6, "water_tankers": 2, "drones": 1,
            "helicopter_available": False,
            "radio_channel": "VHF-144.100MHz", "phone_contact": "+62-541-741234"
        },
        {
            "hq_id": "HQ-MA-KI-02",
            "hq_name": "Manggala Agni Daops Paser",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Timur",
            "kabupaten": "Paser",
            "lat": -1.8667, "lon": 116.1500,
            "crew_available": 20, "crew_on_duty": 10,
            "fire_trucks": 2, "portable_pumps": 4, "water_tankers": 1, "drones": 1,
            "helicopter_available": False,
            "radio_channel": "VHF-144.200MHz", "phone_contact": "+62-543-21999"
        },
        # Kalimantan Utara
        {
            "hq_id": "HQ-MA-KU-01",
            "hq_name": "Manggala Agni Daops Bulungan / Tarakan",
            "agency": "MANGGALA_AGNI",
            "province": "Kalimantan Utara",
            "kabupaten": "Bulungan",
            "lat": 2.8400, "lon": 117.3700,
            "crew_available": 20, "crew_on_duty": 12,
            "fire_trucks": 2, "portable_pumps": 5, "water_tankers": 1, "drones": 1,
            "helicopter_available": False,
            "radio_channel": "VHF-144.500MHz", "phone_contact": "+62-552-21333"
        }
    ]
    df = pd.DataFrame(hqs)
    df["nearest_grid_id"] = df.apply(lambda r: assign_grid_id(r["lat"], r["lon"]), axis=1)
    
    cols = [c[0] for c in conn.execute("DESCRIBE dim_responder_hq").fetchall()]
    cols_str = ", ".join(cols)
    conn.execute("DELETE FROM dim_responder_hq")
    conn.register("stage_hq", df[cols])
    conn.execute(f"INSERT INTO dim_responder_hq ({cols_str}) SELECT {cols_str} FROM stage_hq")
    conn.unregister("stage_hq")
    logger.info(f"Seeded {len(df)} stations into dim_responder_hq.")

def seed_water_sources(conn):
    logger.info("Seeding dim_water_sources...")
    sources = [
        # Major Arterial Rivers
        {"source_id": "WTR-RIV-01", "source_name": "Sungai Kapuas (Hulu)", "water_type": "RIVER", "province": "Kalimantan Barat", "kabupaten": "Sintang", "lat": 0.050, "lon": 111.490, "capacity_m3": 500000.0, "surface_area_m2": 250000.0, "historical_permanence_score": 1.0, "pump_accessible": True, "terrain_difficulty": "EASY"},
        {"source_id": "WTR-RIV-02", "source_name": "Sungai Kapuas (Hilir)", "water_type": "RIVER", "province": "Kalimantan Barat", "kabupaten": "Kubu Raya", "lat": -0.060, "lon": 109.320, "capacity_m3": 800000.0, "surface_area_m2": 400000.0, "historical_permanence_score": 1.0, "pump_accessible": True, "terrain_difficulty": "EASY"},
        {"source_id": "WTR-RIV-03", "source_name": "Sungai Kahayan", "water_type": "RIVER", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.215, "lon": 113.925, "capacity_m3": 450000.0, "surface_area_m2": 200000.0, "historical_permanence_score": 0.98, "pump_accessible": True, "terrain_difficulty": "EASY"},
        {"source_id": "WTR-RIV-04", "source_name": "Sungai Barito (Marabahan)", "water_type": "RIVER", "province": "Kalimantan Selatan", "kabupaten": "Barito Kuala", "lat": -2.990, "lon": 114.770, "capacity_m3": 950000.0, "surface_area_m2": 600000.0, "historical_permanence_score": 1.0, "pump_accessible": True, "terrain_difficulty": "EASY"},
        {"source_id": "WTR-RIV-05", "source_name": "Sungai Mahakam", "water_type": "RIVER", "province": "Kalimantan Timur", "kabupaten": "Kutai Kartanegara", "lat": -0.450, "lon": 117.020, "capacity_m3": 900000.0, "surface_area_m2": 550000.0, "historical_permanence_score": 1.0, "pump_accessible": True, "terrain_difficulty": "EASY"},
        {"source_id": "WTR-RIV-06", "source_name": "Sungai Martapura", "water_type": "RIVER", "province": "Kalimantan Selatan", "kabupaten": "Banjar", "lat": -3.320, "lon": 114.610, "capacity_m3": 350000.0, "surface_area_m2": 150000.0, "historical_permanence_score": 0.95, "pump_accessible": True, "terrain_difficulty": "EASY"},
        {"source_id": "WTR-RIV-07", "source_name": "Sungai Kayan", "water_type": "RIVER", "province": "Kalimantan Utara", "kabupaten": "Bulungan", "lat": 2.850, "lon": 117.360, "capacity_m3": 600000.0, "surface_area_m2": 300000.0, "historical_permanence_score": 1.0, "pump_accessible": True, "terrain_difficulty": "EASY"},
        {"source_id": "WTR-RIV-08", "source_name": "Sungai Mentaya", "water_type": "RIVER", "province": "Kalimantan Tengah", "kabupaten": "Kotawaringin Timur", "lat": -2.530, "lon": 112.950, "capacity_m3": 400000.0, "surface_area_m2": 180000.0, "historical_permanence_score": 0.95, "pump_accessible": True, "terrain_difficulty": "EASY"},
        
        # Strategic Peatland Water Embung & Canals
        {"source_id": "WTR-EMB-01", "source_name": "Embung Gambut Sebangau 01", "water_type": "EMBUNG", "province": "Kalimantan Tengah", "kabupaten": "Pulang Pisau", "lat": -2.450, "lon": 114.050, "capacity_m3": 15000.0, "surface_area_m2": 8000.0, "historical_permanence_score": 0.88, "pump_accessible": True, "terrain_difficulty": "MODERATE"},
        {"source_id": "WTR-EMB-02", "source_name": "Embung Gambut Sebangau 02", "water_type": "EMBUNG", "province": "Kalimantan Tengah", "kabupaten": "Pulang Pisau", "lat": -2.580, "lon": 114.120, "capacity_m3": 12000.0, "surface_area_m2": 6500.0, "historical_permanence_score": 0.82, "pump_accessible": True, "terrain_difficulty": "MODERATE"},
        {"source_id": "WTR-EMB-03", "source_name": "Embung Gambut Liang Anggang", "water_type": "EMBUNG", "province": "Kalimantan Selatan", "kabupaten": "Banjarbaru", "lat": -3.460, "lon": 114.730, "capacity_m3": 18000.0, "surface_area_m2": 9500.0, "historical_permanence_score": 0.90, "pump_accessible": True, "terrain_difficulty": "EASY"},
        {"source_id": "WTR-EMB-04", "source_name": "Embung Gambut Rasau Jaya", "water_type": "EMBUNG", "province": "Kalimantan Barat", "kabupaten": "Kubu Raya", "lat": -0.180, "lon": 109.390, "capacity_m3": 20000.0, "surface_area_m2": 10000.0, "historical_permanence_score": 0.89, "pump_accessible": True, "terrain_difficulty": "EASY"},
        {"source_id": "WTR-CAN-01", "source_name": "Saluran Primer Induk Eks-PLG Blok A", "water_type": "CANAL", "province": "Kalimantan Tengah", "kabupaten": "Kapuas", "lat": -2.850, "lon": 114.450, "capacity_m3": 85000.0, "surface_area_m2": 45000.0, "historical_permanence_score": 0.85, "pump_accessible": True, "terrain_difficulty": "MODERATE"},
        {"source_id": "WTR-CAN-02", "source_name": "Kanal Peatland Kalampangan", "water_type": "CANAL", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.310, "lon": 113.980, "capacity_m3": 35000.0, "surface_area_m2": 18000.0, "historical_permanence_score": 0.80, "pump_accessible": True, "terrain_difficulty": "EASY"},
        
        # Lakes
        {"source_id": "WTR-LAK-01", "source_name": "Danau Sentarum", "water_type": "LAKE", "province": "Kalimantan Barat", "kabupaten": "Kapuas Hulu", "lat": 0.850, "lon": 112.080, "capacity_m3": 1200000.0, "surface_area_m2": 800000.0, "historical_permanence_score": 0.95, "pump_accessible": True, "terrain_difficulty": "MODERATE"},
        {"source_id": "WTR-LAK-02", "source_name": "Danau Jempang", "water_type": "LAKE", "province": "Kalimantan Timur", "kabupaten": "Kutai Barat", "lat": -0.420, "lon": 116.180, "capacity_m3": 750000.0, "surface_area_m2": 500000.0, "historical_permanence_score": 0.92, "pump_accessible": True, "terrain_difficulty": "MODERATE"},
        {"source_id": "WTR-LAK-03", "source_name": "Danau Sembuluh", "water_type": "LAKE", "province": "Kalimantan Tengah", "kabupaten": "Seruyan", "lat": -2.580, "lon": 112.550, "capacity_m3": 900000.0, "surface_area_m2": 600000.0, "historical_permanence_score": 0.97, "pump_accessible": True, "terrain_difficulty": "EASY"}
    ]
    df = pd.DataFrame(sources)
    df["nearest_grid_id"] = df.apply(lambda r: assign_grid_id(r["lat"], r["lon"]), axis=1)
    
    cols = [c[0] for c in conn.execute("DESCRIBE dim_water_sources").fetchall()]
    cols_str = ", ".join(cols)
    conn.execute("DELETE FROM dim_water_sources")
    conn.register("stage_water", df[cols])
    conn.execute(f"INSERT INTO dim_water_sources ({cols_str}) SELECT {cols_str} FROM stage_water")
    conn.unregister("stage_water")
    logger.info(f"Seeded {len(df)} water sources into dim_water_sources.")

def seed_vulnerable_assets(conn):
    logger.info("Seeding dim_vulnerable_assets...")
    assets = [
        # Major Hospitals & Medical Centers
        {"asset_id": "AST-HSP-01", "asset_name": "RSUD Doris Sylvanus Palangka Raya", "asset_type": "HOSPITAL", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.215, "lon": 113.918, "estimated_population": 4500, "is_peatland": True, "is_protected_area": False},
        {"asset_id": "AST-HSP-02", "asset_name": "RSUD Dr. Soedarso Pontianak", "asset_type": "HOSPITAL", "province": "Kalimantan Barat", "kabupaten": "Kota Pontianak", "lat": -0.045, "lon": 109.345, "estimated_population": 5200, "is_peatland": False, "is_protected_area": False},
        {"asset_id": "AST-HSP-03", "asset_name": "RSUD Ulin Banjarmasin", "asset_type": "HOSPITAL", "province": "Kalimantan Selatan", "kabupaten": "Kota Banjarmasin", "lat": -3.325, "lon": 114.595, "estimated_population": 6000, "is_peatland": False, "is_protected_area": False},
        {"asset_id": "AST-HSP-04", "asset_name": "RSUD Abdul Wahab Sjahranie Samarinda", "asset_type": "HOSPITAL", "province": "Kalimantan Timur", "kabupaten": "Kota Samarinda", "lat": -0.485, "lon": 117.142, "estimated_population": 5800, "is_peatland": False, "is_protected_area": False},
        {"asset_id": "AST-HSP-05", "asset_name": "RSUD Dr. H. Soemarno Sosroatmodjo Bulungan", "asset_type": "HOSPITAL", "province": "Kalimantan Utara", "kabupaten": "Bulungan", "lat": 2.835, "lon": 117.365, "estimated_population": 2100, "is_peatland": False, "is_protected_area": False},
        {"asset_id": "AST-HSP-06", "asset_name": "RSUD Pulang Pisau", "asset_type": "HOSPITAL", "province": "Kalimantan Tengah", "kabupaten": "Pulang Pisau", "lat": -2.750, "lon": 114.250, "estimated_population": 1800, "is_peatland": True, "is_protected_area": False},

        # Key High-Risk Settlements Near Peatlands
        {"asset_id": "AST-SET-01", "asset_name": "Pemukiman Sebangau Permai", "asset_type": "SETTLEMENT", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.270, "lon": 113.880, "estimated_population": 14200, "is_peatland": True, "is_protected_area": False},
        {"asset_id": "AST-SET-02", "asset_name": "Desa Taruna Jaya Pulang Pisau", "asset_type": "SETTLEMENT", "province": "Kalimantan Tengah", "kabupaten": "Pulang Pisau", "lat": -2.490, "lon": 114.070, "estimated_population": 6800, "is_peatland": True, "is_protected_area": False},
        {"asset_id": "AST-SET-03", "asset_name": "Kawasan Pemukiman Liang Anggang", "asset_type": "SETTLEMENT", "province": "Kalimantan Selatan", "kabupaten": "Banjarbaru", "lat": -3.445, "lon": 114.710, "estimated_population": 22500, "is_peatland": True, "is_protected_area": False},
        {"asset_id": "AST-SET-04", "asset_name": "Desa Rasau Jaya Tiga", "asset_type": "SETTLEMENT", "province": "Kalimantan Barat", "kabupaten": "Kubu Raya", "lat": -0.210, "lon": 109.420, "estimated_population": 8900, "is_peatland": True, "is_protected_area": False},
        {"asset_id": "AST-SET-05", "asset_name": "Kawasan Syamsudin Noor", "asset_type": "SETTLEMENT", "province": "Kalimantan Selatan", "kabupaten": "Banjarbaru", "lat": -3.440, "lon": 114.750, "estimated_population": 19500, "is_peatland": True, "is_protected_area": False},
        
        # Educational Facilities
        {"asset_id": "AST-SCH-01", "asset_name": "Kompleks Pendidikan Palangka Raya Barat", "asset_type": "SCHOOL", "province": "Kalimantan Tengah", "kabupaten": "Kota Palangka Raya", "lat": -2.230, "lon": 113.895, "estimated_population": 3200, "is_peatland": True, "is_protected_area": False},
        {"asset_id": "AST-SCH-02", "asset_name": "Kampus Terpadu UNLAM Banjarbaru", "asset_type": "SCHOOL", "province": "Kalimantan Selatan", "kabupaten": "Banjarbaru", "lat": -3.442, "lon": 114.845, "estimated_population": 8500, "is_peatland": False, "is_protected_area": False},

        # Critical National Parks & Peatland Forest Reserves
        {"asset_id": "AST-PRT-01", "asset_name": "Taman Nasional Sebangau (Kubah Gambut)", "asset_type": "PROTECTED_FOREST", "province": "Kalimantan Tengah", "kabupaten": "Katingan / Pulang Pisau", "lat": -2.550, "lon": 113.750, "estimated_population": 450, "is_peatland": True, "is_protected_area": True},
        {"asset_id": "AST-PRT-02", "asset_name": "Taman Nasional Tanjung Puting", "asset_type": "PROTECTED_FOREST", "province": "Kalimantan Tengah", "kabupaten": "Kotawaringin Barat", "lat": -3.050, "lon": 111.950, "estimated_population": 250, "is_peatland": True, "is_protected_area": True},
        {"asset_id": "AST-PRT-03", "asset_name": "Taman Nasional Betung Kerihun", "asset_type": "PROTECTED_FOREST", "province": "Kalimantan Barat", "kabupaten": "Kapuas Hulu", "lat": 1.150, "lon": 113.200, "estimated_population": 120, "is_peatland": False, "is_protected_area": True},
        {"asset_id": "AST-PRT-04", "asset_name": "Taman Nasional Kutai", "asset_type": "PROTECTED_FOREST", "province": "Kalimantan Timur", "kabupaten": "Kutai Timur", "lat": 0.450, "lon": 117.250, "estimated_population": 300, "is_peatland": False, "is_protected_area": True}
    ]
    df = pd.DataFrame(assets)
    df["nearest_grid_id"] = df.apply(lambda r: assign_grid_id(r["lat"], r["lon"]), axis=1)
    
    cols = [c[0] for c in conn.execute("DESCRIBE dim_vulnerable_assets").fetchall()]
    cols_str = ", ".join(cols)
    conn.execute("DELETE FROM dim_vulnerable_assets")
    conn.register("stage_assets", df[cols])
    conn.execute(f"INSERT INTO dim_vulnerable_assets ({cols_str}) SELECT {cols_str} FROM stage_assets")
    conn.unregister("stage_assets")
    logger.info(f"Seeded {len(df)} assets into dim_vulnerable_assets.")

def main():
    conn = get_connection()
    seed_responder_hq(conn)
    seed_water_sources(conn)
    seed_vulnerable_assets(conn)
    
    # Export to Parquet
    logger.info("Exporting response dimensions to Parquet...")
    export_to_parquet("dim_responder_hq")
    export_to_parquet("dim_water_sources")
    export_to_parquet("dim_vulnerable_assets")
    logger.info("Seeding and Parquet export completed successfully!")

if __name__ == "__main__":
    main()
