"""
ETL Pipeline: Precompute 24-Hour Fire Targets
---------------------------------------------
Precomputes leak-free fact_fire_targets_24h for all samples in fact_training_spine.
Target is defined as fire activity strictly in (T, T+24h]:
- fire_count_24h
- max_frp_24h
- has_fire_24h
Uses equi-join against daily hotspot aggregates for sub-second execution.
"""

import sys
import logging
from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_targets")

DB_PATH = Path("data/warehouse/wildfire.duckdb")

def build_targets():
    conn = duckdb.connect(str(DB_PATH), read_only=False)
    
    logger.info("Computing pre-aggregated daily hotspots...")
    query = """
    CREATE OR REPLACE TABLE fact_fire_targets_24h AS
    WITH daily_hotspots AS (
        SELECT 
            grid_id,
            date_trunc('day', datetime_utc) AS fire_day,
            COUNT(*)::INTEGER AS fire_count,
            MAX(frp_mw)::DOUBLE AS max_frp
        FROM fact_fire_hotspots
        WHERE year BETWEEN 2021 AND 2025
        GROUP BY grid_id, date_trunc('day', datetime_utc)
    )
    SELECT 
        sp.grid_id,
        sp.target_datetime,
        COALESCE(dh.fire_count, 0)::INTEGER AS fire_count_24h,
        COALESCE(dh.max_frp, 0.0)::DOUBLE AS max_frp_24h,
        (COALESCE(dh.fire_count, 0) > 0)::BOOLEAN AS has_fire_24h
    FROM fact_training_spine sp
    LEFT JOIN daily_hotspots dh 
        ON sp.grid_id = dh.grid_id 
        AND sp.target_datetime = dh.fire_day;
    """
    
    logger.info("Materializing fact_fire_targets_24h table in DuckDB...")
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(query)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_targets_pk ON fact_fire_targets_24h (grid_id, target_datetime)")
        conn.execute("COMMIT")
        logger.info("fact_fire_targets_24h materialized successfully.")
    except Exception as e:
        conn.execute("ROLLBACK")
        logger.error(f"Failed to create targets: {e}")
        raise e
        
    stats = conn.execute("""
        SELECT 
            COUNT(*) as total_rows,
            SUM(CASE WHEN has_fire_24h THEN 1 ELSE 0 END) as positive_targets,
            SUM(CASE WHEN NOT has_fire_24h THEN 1 ELSE 0 END) as negative_targets,
            MAX(fire_count_24h) as max_fires_in_cell,
            MAX(max_frp_24h) as max_frp_val
        FROM fact_fire_targets_24h
    """).df()
    print("\n=== FACT_FIRE_TARGETS_24H STATS ===")
    print(stats)
    conn.close()

if __name__ == "__main__":
    build_targets()
