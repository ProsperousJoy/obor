import argparse
import logging
import time
import tracemalloc
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import individual ETL run functions
from etl import extract_transform_viirs
from etl import extract_transform_himawari
from etl import extract_transform_era5
from etl import extract_transform_bmkg
from etl import extract_transform_fuel
from etl.load_warehouse import export_to_parquet, get_table_stats, get_connection

logger = logging.getLogger(__name__)

def run_all(start_date: str = None, end_date: str = None):
    logger.info("Running all ETL pipelines...")
    extract_transform_viirs.run(start_date=start_date, end_date=end_date)
    extract_transform_himawari.run(start_date=start_date, end_date=end_date)
    extract_transform_era5.run(start_date=start_date, end_date=end_date)
    extract_transform_bmkg.run()
    extract_transform_fuel.run(start_date=start_date, end_date=end_date)

def export_all():
    tables = [
        'fact_fire_hotspots',
        'fact_thermal_grid',
        'agg_thermal_hourly',
        'agg_thermal_daily',
        'agg_fire_history',
        'fact_weather_daily',
        'agg_weather_rolling',
        'fact_forecast_3h',
        'fact_fuel_condition',
        'fact_training_spine',
        'fact_fire_targets_24h'
    ]
    logger.info("Exporting all fact/agg tables to Parquet...")
    conn = get_connection()
    existing_tables = set(conn.execute("SHOW TABLES").df()['name'].tolist())
    
    for table in tables:
        if table in existing_tables:
            try:
                row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if row_count > 0:
                    export_to_parquet(table)
                else:
                    logger.info(f"Skipping export for empty table {table}")
            except Exception as e:
                logger.error(f"Failed to export table {table}: {e}")
        else:
            logger.warning(f"Table {table} does not exist in warehouse.")

def main():
    parser = argparse.ArgumentParser(description="Master ETL Orchestrator")
    parser.add_argument("--source", choices=['viirs', 'himawari', 'era5', 'bmkg', 'fuel', 'spine', 'targets', 'all'], required=False, default=None, help="Data source to process")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD")
    parser.add_argument("--export", choices=['parquet'], help="Export format")
    parser.add_argument("--validate", action="store_true", help="Run warehouse validation suite")
    parser.add_argument("--benchmark", action="store_true", help="Measure runtime and memory")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if args.benchmark:
        tracemalloc.start()
        start_time = time.time()
        
    if args.source == 'viirs':
        extract_transform_viirs.run(start_date=args.start, end_date=args.end)
    elif args.source == 'himawari':
        extract_transform_himawari.run(start_date=args.start, end_date=args.end)
    elif args.source == 'era5':
        extract_transform_era5.run(start_date=args.start, end_date=args.end)
    elif args.source == 'bmkg':
        extract_transform_bmkg.run()
    elif args.source == 'fuel':
        extract_transform_fuel.run(start_date=args.start, end_date=args.end)
    elif args.source == 'spine':
        from etl.build_training_spine import build_spine
        build_spine()
    elif args.source == 'targets':
        from etl.build_targets import build_targets
        build_targets()
    elif args.source == 'all':
        run_all(args.start, args.end)
        
    if args.export == 'parquet':
        export_all()
        
    if args.validate:
        from etl.validate_warehouse import run_full_validation, save_report
        logger.info("Executing comprehensive warehouse validation suite...")
        report = run_full_validation()
        out_path = save_report(report)
        print(f"\nValidation Report saved to: {out_path}")
        print(f"Overall Status: {report.get('overall_status', 'UNKNOWN')}")
        
    if args.benchmark:
        end_time = time.time()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        runtime = end_time - start_time
        peak_mb = peak / 10**6
        logger.info(f"--- Benchmark Summary ---")
        logger.info(f"Runtime: {runtime:.2f} seconds")
        logger.info(f"Peak Memory: {peak_mb:.2f} MB")
        
    logger.info("Master ETL orchestration complete.")

if __name__ == "__main__":
    main()
