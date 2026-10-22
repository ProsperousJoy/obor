"""
Centralized Configuration & Constants for Kalimantan Wildfire Risk Prediction
Data Mining & Acquisition Pipeline + Data Warehouse
"""

from pathlib import Path

# ─────────────────────────────────────────────────────────────────────
# Base Paths
# ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DOCS_DIR = PROJECT_ROOT / "docs"

# ─────────────────────────────────────────────────────────────────────
# Study Area: Kalimantan / Borneo Indonesia
# ─────────────────────────────────────────────────────────────────────
BORNEO_BBOX = {
    "lon_min": 108.0,
    "lon_max": 119.0,
    "lat_min": -5.0,
    "lat_max": 7.0,
}

# Provincial Capital Coordinates for Kalimantan
PROVINCIAL_CAPITALS = {
    "Kalimantan Barat": {"city": "Pontianak", "lat": -0.02, "lon": 109.34},
    "Kalimantan Tengah": {"city": "Palangka Raya", "lat": -2.21, "lon": 113.92},
    "Kalimantan Selatan": {"city": "Banjarmasin", "lat": -3.32, "lon": 114.59},
    "Kalimantan Timur": {"city": "Samarinda", "lat": -0.50, "lon": 117.15},
    "Kalimantan Utara": {"city": "Tanjung Selor", "lat": 2.84, "lon": 117.37},
}

# ─────────────────────────────────────────────────────────────────────
# Historical Training & Temporal Split Configuration
# ─────────────────────────────────────────────────────────────────────
HISTORICAL_PERIOD = {
    "start": "2021-01-01",
    "end": "2025-12-31",

    "train": ("2021-01-01", "2023-12-31"),    # 3 years
    "val": ("2024-01-01", "2024-12-31"),       # 1 year
    "test": ("2025-01-01", "2025-12-31"),      # 1 year
    "inference": "2026-01-01",                  # onward
}

# ─────────────────────────────────────────────────────────────────────
# Data Source Configurations
# ─────────────────────────────────────────────────────────────────────

# Himawari-8/9 AHI Configuration
HIMAWARI_CONFIG = {
    # S3 source
    "s3_bucket_h08": "noaa-himawari8",
    "s3_bucket_h09": "noaa-himawari9",
    "dataset_prefix": "AHI-L1b-FLDK",
    "target_band": "B07",

    # Satellite transition
    "transition_date": "2022-12-13",  # H8 → H9 operational handover
    "satellites": {
        "before_transition": "AHI_H08",
        "after_transition": "AHI_H09",
    },

    # Segments for full Kalimantan coverage
    "segments": ["S0510", "S0610"],

    # Temporal
    "temporal_resolution_minutes": 10,
    "storage_mode": "full",  # Retain all 10-minute observations
    "chunk_processing": True,

    # Directories (legacy acquisition paths)
    "raw_dir": DATA_DIR / "himawari" / "raw",
    "processed_dir": DATA_DIR / "himawari" / "processed",
    "output_dir": OUTPUTS_DIR / "himawari",
}

# NASA VIIRS 375m Active Fire Configuration
VIIRS_CONFIG = {
    "firms_base_url": "https://firms.modaps.eosdis.nasa.gov",
    # Legacy acquisition paths
    "raw_dir": DATA_DIR / "viirs" / "raw",
    "processed_dir": DATA_DIR / "viirs" / "processed",
}

# BMKG Open Data API Configuration
BMKG_CONFIG = {
    "api_base_url": "https://api.bmkg.go.id",
    # Legacy acquisition paths
    "raw_dir": DATA_DIR / "bmkg" / "raw",
    "processed_dir": DATA_DIR / "bmkg" / "processed",
}

# Google Earth Engine / ERA5-Land Configuration
GEE_CONFIG = {
    "stac_catalog_url": "https://storage.googleapis.com/earthengine-stac/catalog",
    "sample_dir": OUTPUTS_DIR / "validation",
}

# ─────────────────────────────────────────────────────────────────────
# Data Warehouse Configuration
# ─────────────────────────────────────────────────────────────────────
WAREHOUSE_CONFIG = {
    "db_path": DATA_DIR / "warehouse" / "wildfire.duckdb",
    "parquet_dir": DATA_DIR / "warehouse" / "parquet",
    "raw_dir": DATA_DIR / "raw",
    "staging_dir": DATA_DIR / "staging",

    # Canonical spatial grid
    "canonical_grid_resolution_deg": 0.02,  # ~2 km

    # Partition strategy
    "partition_columns": ["year", "month"],
}

# ─────────────────────────────────────────────────────────────────────
# Fire Prediction Configuration
# ─────────────────────────────────────────────────────────────────────
PREDICTION_CONFIG = {
    "horizon_hours": 24,
    "prediction_frequency_hours": 3,

    "fire_history_lookback_hours": [24, 168],  # 24h, 7d
    "weather_rolling_windows_days": [7, 30],

    "primary_target": "has_fire_24h",
    "secondary_target": "fire_intensity_24h",
}

# ─────────────────────────────────────────────────────────────────────
# ETL Processing Configuration
# ─────────────────────────────────────────────────────────────────────
ETL_CONFIG = {
    "chunk_size": 100_000,       # Starting point, tune from benchmark
    "enable_benchmark": True,
    "deduplicate": True,
    "validate_before_load": True,
}
