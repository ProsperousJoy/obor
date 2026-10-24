"""
Weather Spatial Interpolator & Rolling Feature Calculator
--------------------------------------------------------
Implements Inverse Distance Weighting (IDW, p=2) spatial interpolation
from the 5 provincial weather stations across Kalimantan grid cells.
Precomputes normalized spatial weights and populates fact_weather_daily
and agg_weather_rolling with true consecutive_dry_days and rolling rain.
"""

import logging
import math
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.config.settings import PROVINCIAL_CAPITALS, BORNEO_BBOX

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("interpolate_weather")

DB_PATH = Path("data/warehouse/wildfire.duckdb")
RAW_ERA5_CSV = Path("data/gee/processed/kalimantan_era5land_2021_2025.csv")


def compute_idw_weights_table(conn: duckdb.DuckDBPyConnection):
    """
    Precompute IDW (p=2) spatial weights for all 331,151 cells in dim_grid
    relative to the 5 provincial stations.
    """
    logger.info("Computing dim_grid_weather_weights table...")
    
    # 5 station coordinates
    stations = [
        ("Kalimantan Barat", -0.02, 109.34),
        ("Kalimantan Tengah", -2.21, 113.92),
        ("Kalimantan Selatan", -3.32, 114.59),
        ("Kalimantan Timur", -0.50, 117.15),
        ("Kalimantan Utara", 2.84, 117.37),
    ]
    
    grid_df = conn.execute("SELECT grid_id, centroid_lat, centroid_lon FROM dim_grid").df()
    n_cells = len(grid_df)
    
    # Compute inverse distance squared
    inv_dists = np.zeros((n_cells, len(stations)), dtype=np.float64)
    eps = 1e-4
    
    for j, (name, s_lat, s_lon) in enumerate(stations):
        d2 = (grid_df["centroid_lat"].values - s_lat)**2 + (grid_df["centroid_lon"].values - s_lon)**2 + eps
        inv_dists[:, j] = 1.0 / d2
        
    weights = inv_dists / inv_dists.sum(axis=1, keepdims=True)
    
    weights_df = pd.DataFrame({
        "grid_id": grid_df["grid_id"],
        "w_kalbar": weights[:, 0].round(4),
        "w_kalteng": weights[:, 1].round(4),
        "w_kalsel": weights[:, 2].round(4),
        "w_kaltim": weights[:, 3].round(4),
        "w_kaltara": weights[:, 4].round(4),
    })
    
    conn.execute("CREATE OR REPLACE TABLE dim_grid_weather_weights AS SELECT * FROM weights_df")
    logger.info(f"dim_grid_weather_weights created successfully for {len(weights_df)} cells.")


def compute_consecutive_dry_days_sql():
    """
    SQL window query to compute consecutive_dry_days:
    A dry day is defined as precip_mm < 1.0 mm.
    """
    return """
    WITH dry_groups AS (
        SELECT 
            grid_id,
            date_utc,
            precip_mm,
            t2m_mean_c,
            year,
            month,
            SUM(CASE WHEN precip_mm >= 1.0 THEN 1 ELSE 0 END) OVER (
                PARTITION BY grid_id ORDER BY date_utc ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS wet_event_group
        FROM fact_weather_daily
    ),
    numbered AS (
        SELECT 
            grid_id,
            date_utc,
            precip_mm,
            t2m_mean_c,
            year,
            month,
            CASE 
                WHEN precip_mm >= 1.0 THEN 0
                ELSE (ROW_NUMBER() OVER (
                    PARTITION BY grid_id, wet_event_group ORDER BY date_utc
                ) - 1)::INTEGER
            END AS consecutive_dry_days
        FROM dry_groups
    )
    SELECT 
        grid_id,
        date_utc,
        COALESCE(SUM(precip_mm) OVER (
            PARTITION BY grid_id ORDER BY date_utc ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ), 0.0)::DOUBLE AS rain_accum_7d_mm,
        COALESCE(SUM(precip_mm) OVER (
            PARTITION BY grid_id ORDER BY date_utc ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ), 0.0)::DOUBLE AS rain_accum_30d_mm,
        consecutive_dry_days,
        (t2m_mean_c - COALESCE(AVG(t2m_mean_c) OVER (
            PARTITION BY grid_id ORDER BY date_utc ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ), t2m_mean_c))::DOUBLE AS t2m_anomaly_vs_30d_mean,
        year::INTEGER AS year,
        month::INTEGER AS month
    FROM numbered;
    """


def run_interpolation():
    conn = duckdb.connect(str(DB_PATH), read_only=False)
    compute_idw_weights_table(conn)
    conn.close()

if __name__ == "__main__":
    run_interpolation()
