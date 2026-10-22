"""
Verification script for targeted remediation.
Checks DuckDB vs Parquet parity and all criteria A-K.
"""
import duckdb
from pathlib import Path

def main():
    conn = duckdb.connect("data/warehouse/wildfire.duckdb")
    tables = [
        "fact_fire_hotspots",
        "fact_thermal_grid",
        "agg_thermal_hourly",
        "agg_thermal_daily",
        "agg_fire_history",
        "fact_weather_daily",
        "agg_weather_rolling",
        "fact_forecast_3h",
        "fact_fuel_condition",
        "fact_training_spine",
        "fact_fire_targets_24h"
    ]

    print(f"{'Table':<25} | {'DuckDB Rows':<12} | {'Parquet Rows':<12} | {'Status':<8}")
    print("-" * 65)

    all_matched = True
    for tbl in tables:
        db_cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        pq_path = Path(f"data/warehouse/parquet/{tbl}")
        if pq_path.exists():
            files = list(pq_path.rglob("*.parquet"))
            if files:
                glob_path = str(pq_path / "**" / "*.parquet").replace("\\", "/")
                try:
                    pq_cnt = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{glob_path}')").fetchone()[0]
                except Exception:
                    glob_path = str(pq_path / "data.parquet").replace("\\", "/")
                    pq_cnt = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{glob_path}')").fetchone()[0]
                status = "MATCH" if db_cnt == pq_cnt else f"DIFF ({db_cnt - pq_cnt})"
                if db_cnt != pq_cnt:
                    all_matched = False
            else:
                pq_cnt = 0
                status = "EMPTY"
                all_matched = False
        else:
            pq_cnt = 0
            status = "MISSING"
            all_matched = False
        print(f"{tbl:<25} | {db_cnt:<12,d} | {pq_cnt:<12,d} | {status:<8}")

    print("-" * 65)
    print("All Parquet Tables Matched DuckDB:", all_matched)

    # Validate training view metrics
    print("\n=== VW_TRAINING_DATASET METRICS ===")
    v_stats = conn.execute("""
        SELECT 
            COUNT(*) as total_samples,
            COUNT(CASE WHEN target_has_fire_24h THEN 1 END) as pos_targets,
            COUNT(CASE WHEN NOT target_has_fire_24h THEN 1 END) as neg_targets,
            COUNT(prev_day_rh_min_pct) as non_null_rh,
            MIN(prev_day_rh_min_pct) as min_rh,
            MAX(prev_day_rh_min_pct) as max_rh,
            AVG(prev_day_rh_min_pct) as avg_rh,
            COUNT(CASE WHEN NOT is_land THEN 1 END) as ocean_samples
        FROM vw_training_dataset
    """).fetchone()

    print(f"Total Samples:       {v_stats[0]:,d}")
    print(f"Positive Targets:    {v_stats[1]:,d} ({v_stats[1]/v_stats[0]*100:.2f}%)")
    print(f"Negative Targets:    {v_stats[2]:,d} ({v_stats[2]/v_stats[0]*100:.2f}%)")
    print(f"Non-Null RH:         {v_stats[3]:,d} (Boundary nulls: {v_stats[0]-v_stats[3]})")
    print(f"RH Min / Max / Avg:  {v_stats[4]}% / {v_stats[5]}% / {v_stats[6]:.2f}%")
    print(f"Ocean Samples:       {v_stats[7]} (Should be 0)")

    # Validate land mask
    print("\n=== DIM_GRID METRICS ===")
    g_stats = conn.execute("""
        SELECT 
            COUNT(*) as total_cells,
            COUNT(CASE WHEN is_land THEN 1 END) as land_cells,
            COUNT(CASE WHEN NOT is_land THEN 1 END) as ocean_cells
        FROM dim_grid
    """).fetchone()
    print(f"Total Cells:         {g_stats[0]:,d}")
    print(f"Land Cells:          {g_stats[1]:,d} ({g_stats[1]/g_stats[0]*100:.2f}%)")
    print(f"Ocean Cells:         {g_stats[2]:,d} ({g_stats[2]/g_stats[0]*100:.2f}%)")

if __name__ == "__main__":
    main()
