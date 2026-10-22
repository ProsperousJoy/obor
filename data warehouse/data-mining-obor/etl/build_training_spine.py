"""
ETL Pipeline: Build Spatiotemporal Training Spine
------------------------------------------------
Generates fact_training_spine table using Presence-Background (Pseudo-Absence)
stratified sampling across 2021-2025:
- Positive stratum: Grid cells with fire activity in (T, T+24h]
- Background stratum: Stratified non-fire land cells on same dates (ratio 3:1)
- Temporal Splits:
    * TRAIN: 2021-01-01 to 2023-12-31
    * VAL:   2024-01-01 to 2024-12-31
    * TEST:  2025-01-01 to 2025-12-31
"""

import sys
import logging
from pathlib import Path
import numpy as np
import pandas as pd
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import HISTORICAL_PERIOD

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_training_spine")

DB_PATH = Path("data/warehouse/wildfire.duckdb")

def build_spine(negative_ratio: int = 3, seed: int = 42):
    np.random.seed(seed)
    conn = duckdb.connect(str(DB_PATH), read_only=False)
    
    logger.info("Extracting positive presence instances from fact_fire_hotspots (2021-2025)...")
    pos_df = conn.execute("""
        SELECT 
            h.grid_id,
            date_trunc('day', h.datetime_utc) AS target_datetime,
            TRUE AS is_fire_stratum,
            EXTRACT(YEAR FROM date_trunc('day', h.datetime_utc))::INTEGER AS year,
            EXTRACT(MONTH FROM date_trunc('day', h.datetime_utc))::INTEGER AS month
        FROM fact_fire_hotspots h
        JOIN dim_grid g ON h.grid_id = g.grid_id
        WHERE h.datetime_utc >= '2021-01-01' AND h.datetime_utc < '2026-01-01'
          AND g.is_land = TRUE
        GROUP BY h.grid_id, date_trunc('day', h.datetime_utc)
    """).df()
    
    n_pos = len(pos_df)
    logger.info(f"Identified {n_pos:,d} positive grid-date presence instances.")
    
    # Get distinct active fire dates and province grid pools
    logger.info("Sampling stratified background absence instances...")
    dates_df = pos_df[["target_datetime", "year", "month"]].drop_duplicates()
    
    land_grids = conn.execute("""
        SELECT grid_id, province 
        FROM dim_grid 
        WHERE is_land = true
    """).df()
    
    all_land_ids = land_grids["grid_id"].values
    
    # For each date with fire, sample negative_ratio background non-fire cells
    # Group positive cells by date for fast set exclusion
    pos_by_date = pos_df.groupby("target_datetime")["grid_id"].apply(set).to_dict()
    
    bg_records = []
    logger.info(f"Generating background samples (ratio {negative_ratio}:1)...")
    
    for _, row in dates_df.iterrows():
        dt = row["target_datetime"]
        yr = int(row["year"])
        mo = int(row["month"])
        
        pos_set = pos_by_date.get(dt, set())
        n_needed = len(pos_set) * negative_ratio
        
        # Sample candidate grid indices without replacement
        candidates = np.random.choice(all_land_ids, size=min(n_needed * 2, len(all_land_ids)), replace=False)
        valid_candidates = [g for g in candidates if g not in pos_set][:n_needed]
        
        for g in valid_candidates:
            bg_records.append({
                "grid_id": g,
                "target_datetime": dt,
                "is_fire_stratum": False,
                "year": yr,
                "month": mo
            })
            
    bg_df = pd.DataFrame(bg_records)
    logger.info(f"Generated {len(bg_df):,d} background absence instances.")
    
    # Combine positive and background strata
    spine_df = pd.concat([pos_df, bg_df], ignore_index=True)
    spine_df = spine_df.drop_duplicates(subset=["grid_id", "target_datetime"]).reset_index(drop=True)
    
    # Assign deterministic temporal splits
    # TRAIN: 2021-2023, VAL: 2024, TEST: 2025
    conditions = [
        spine_df["year"] <= 2023,
        spine_df["year"] == 2024,
        spine_df["year"] == 2025
    ]
    choices = ["TRAIN", "VAL", "TEST"]
    spine_df["split"] = np.select(conditions, choices, default="UNKNOWN")
    
    # Sort deterministically and assign sample_id
    spine_df = spine_df.sort_values(by=["target_datetime", "grid_id"]).reset_index(drop=True)
    spine_df["sample_id"] = np.arange(1, len(spine_df) + 1, dtype=np.int64)
    
    cols = ["sample_id", "grid_id", "target_datetime", "is_fire_stratum", "split", "year", "month"]
    spine_df = spine_df[cols]
    
    logger.info("Writing fact_training_spine to DuckDB...")
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute("CREATE OR REPLACE TABLE fact_training_spine AS SELECT * FROM spine_df")
        conn.execute("COMMIT")
        logger.info(f"fact_training_spine created successfully with {len(spine_df):,d} rows.")
    except Exception as e:
        conn.execute("ROLLBACK")
        logger.error(f"Failed to create fact_training_spine: {e}")
        raise e
        
    # Print summary breakdown
    breakdown = conn.execute("""
        SELECT split, is_fire_stratum, COUNT(*) as count 
        FROM fact_training_spine 
        GROUP BY split, is_fire_stratum 
        ORDER BY split, is_fire_stratum DESC
    """).df()
    print("\n=== FACT_TRAINING_SPINE BREAKDOWN ===")
    print(breakdown)
    conn.close()

if __name__ == "__main__":
    build_spine()
