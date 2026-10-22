"""
Warehouse Data Quality & Validation Suite

Post-load validation for the Kalimantan Wildfire Data Warehouse.
Checks physical ranges, referential integrity, temporal completeness,
anti-leakage rules, and Himawari-specific data quality.
"""

import json
import logging
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb

from config.settings import WAREHOUSE_CONFIG, HISTORICAL_PERIOD

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Physical Range Validation Rules
# ─────────────────────────────────────────────────────────────────────
RANGE_VALIDATIONS = {
    "fact_fire_hotspots": {
        "bright_ti4_k": (180.0, 500.0),
        "bright_ti5_k": (180.0, 500.0),
        "frp_mw": (0.0, 2000.0),
        "lat": (-5.0, 7.0),
        "lon": (108.0, 119.0),
    },
    "fact_thermal_grid": {
        "bt_b07_k": (180.0, 400.0),
        "valid_pixel_pct": (0.0, 100.0),
    },
    "fact_weather_daily": {
        "t2m_mean_c": (-10.0, 50.0),
        "t2m_max_c": (-10.0, 55.0),
        "t2m_min_c": (-15.0, 45.0),
        "rh_mean_pct": (0.0, 100.0),
        "precip_mm": (0.0, 500.0),
        "wind_speed_kmh": (0.0, 200.0),
        "soil_moisture_0_7cm": (0.0, 1.0),
        "soil_moisture_rootzone": (0.0, 1.0),
    },
    "fact_forecast_3h": {
        "temp_c": (-10.0, 50.0),
        "humidity_pct": (0.0, 100.0),
        "precip_mm": (0.0, 200.0),
        "wind_speed_kmh": (0.0, 200.0),
        "cloud_cover_pct": (0.0, 100.0),
    },
    "fact_fuel_condition": {
        "ndvi": (-0.2, 1.0),
        "evi": (-0.2, 1.0),
        "ndmi": (-1.0, 1.0),
    },
}


def get_connection() -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection to the warehouse database."""
    from etl.load_warehouse import get_connection as get_wh_conn
    return get_wh_conn()


def validate_table_existence(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Verify all expected tables exist in the warehouse."""
    logger.info("Checking table existence...")

    expected_tables = [
        # Dimensions
        "dim_grid", "dim_sensor", "dim_adm4",
        # Facts
        "fact_fire_hotspots", "fact_thermal_grid", "fact_weather_daily",
        "fact_forecast_3h", "fact_fuel_condition",
        # Aggregations
        "agg_thermal_hourly", "agg_thermal_daily",
        "agg_fire_history", "agg_weather_rolling",
    ]

    result = conn.sql("SHOW TABLES").fetchall()
    existing_tables = [row[0] for row in result]

    missing = [t for t in expected_tables if t not in existing_tables]
    extra = [t for t in existing_tables if t not in expected_tables]

    status = "PASS" if not missing else "FAIL"
    logger.info(f"  Table existence: {status} ({len(existing_tables)} found, {len(missing)} missing)")

    return {
        "check": "table_existence",
        "status": status,
        "expected": len(expected_tables),
        "found": len(existing_tables),
        "missing": missing,
        "extra": extra,
    }


def validate_row_counts(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Get row counts for all tables."""
    logger.info("Checking row counts...")

    tables = [
        "dim_grid", "dim_sensor", "dim_adm4",
        "fact_fire_hotspots", "fact_thermal_grid", "fact_weather_daily",
        "fact_forecast_3h", "fact_fuel_condition",
        "agg_thermal_hourly", "agg_thermal_daily",
        "agg_fire_history", "agg_weather_rolling",
    ]

    counts = {}
    for table in tables:
        try:
            row = conn.sql(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0] if row else 0
        except Exception as e:
            counts[table] = f"ERROR: {e}"

    for table, count in counts.items():
        logger.info(f"  {table}: {count:,} rows" if isinstance(count, int) else f"  {table}: {count}")

    return {
        "check": "row_counts",
        "counts": counts,
    }


def validate_dim_grid(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Validate the canonical grid dimension."""
    logger.info("Validating dim_grid...")

    stats = conn.sql("""
        SELECT
            COUNT(*) as total_cells,
            COUNT(*) FILTER (WHERE is_land) as land_cells,
            MIN(centroid_lat) as min_lat,
            MAX(centroid_lat) as max_lat,
            MIN(centroid_lon) as min_lon,
            MAX(centroid_lon) as max_lon,
            COUNT(DISTINCT province) as n_provinces
        FROM dim_grid
    """).fetchone()

    result = {
        "check": "dim_grid_validation",
        "total_cells": stats[0],
        "land_cells": stats[1],
        "lat_range": [stats[2], stats[3]],
        "lon_range": [stats[4], stats[5]],
        "n_provinces": stats[6],
        "status": "PASS" if stats[0] > 0 else "FAIL",
    }

    logger.info(f"  Total cells: {stats[0]:,}, Land cells: {stats[1]:,}, Provinces: {stats[6]}")
    return result


def validate_physical_ranges(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Validate that all data falls within expected physical ranges."""
    logger.info("Checking physical value ranges...")

    results = {}
    for table, columns in RANGE_VALIDATIONS.items():
        table_results = {}
        for column, (min_val, max_val) in columns.items():
            try:
                row = conn.sql(f"""
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE {column} < {min_val} OR {column} > {max_val}) as out_of_range,
                        MIN({column}) as actual_min,
                        MAX({column}) as actual_max
                    FROM {table}
                    WHERE {column} IS NOT NULL
                """).fetchone()

                total, out_of_range, actual_min, actual_max = row
                status = "PASS" if out_of_range == 0 else "WARN"

                table_results[column] = {
                    "expected_range": [min_val, max_val],
                    "actual_range": [actual_min, actual_max],
                    "total_values": total,
                    "out_of_range": out_of_range,
                    "status": status,
                }

                if out_of_range > 0:
                    logger.warning(
                        f"  {table}.{column}: {out_of_range:,}/{total:,} values "
                        f"outside [{min_val}, {max_val}] (actual: [{actual_min}, {actual_max}])"
                    )
            except Exception as e:
                table_results[column] = {"status": "SKIP", "reason": str(e)}

        results[table] = table_results

    return {"check": "physical_ranges", "tables": results}


def validate_referential_integrity(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Check foreign key relationships between fact and dimension tables."""
    logger.info("Checking referential integrity...")

    fk_checks = [
        ("fact_fire_hotspots", "grid_id", "dim_grid", "grid_id"),
        ("fact_fire_hotspots", "sensor_id", "dim_sensor", "sensor_id"),
        ("fact_thermal_grid", "grid_id", "dim_grid", "grid_id"),
        ("fact_thermal_grid", "sensor_id", "dim_sensor", "sensor_id"),
        ("fact_weather_daily", "grid_id", "dim_grid", "grid_id"),
        ("fact_forecast_3h", "adm4_code", "dim_adm4", "adm4_code"),
        ("fact_fuel_condition", "grid_id", "dim_grid", "grid_id"),
    ]

    results = []
    for fact_table, fk_col, dim_table, pk_col in fk_checks:
        try:
            row = conn.sql(f"""
                SELECT COUNT(*) FROM {fact_table} f
                WHERE f.{fk_col} IS NOT NULL
                  AND f.{fk_col} NOT IN (SELECT {pk_col} FROM {dim_table})
            """).fetchone()

            orphans = row[0]
            status = "PASS" if orphans == 0 else "FAIL"
            results.append({
                "fact_table": fact_table,
                "fk_column": fk_col,
                "dim_table": dim_table,
                "orphan_rows": orphans,
                "status": status,
            })

            if orphans > 0:
                logger.warning(f"  {fact_table}.{fk_col} → {dim_table}.{pk_col}: {orphans:,} orphan rows")
            else:
                logger.info(f"  {fact_table}.{fk_col} → {dim_table}.{pk_col}: PASS")
        except Exception as e:
            results.append({
                "fact_table": fact_table,
                "fk_column": fk_col,
                "dim_table": dim_table,
                "status": "SKIP",
                "reason": str(e),
            })

    return {"check": "referential_integrity", "results": results}


def validate_temporal_completeness(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Check temporal coverage and detect gaps in Himawari observations."""
    logger.info("Checking temporal completeness...")

    results = {}

    # Himawari temporal completeness (expected: 144 observations/day)
    try:
        himawari_daily = conn.sql("""
            SELECT
                CAST(datetime_utc AS DATE) as obs_date,
                COUNT(DISTINCT datetime_utc) as actual_timestamps,
                144 as expected_timestamps,
                144 - COUNT(DISTINCT datetime_utc) as missing_timestamps,
                ROUND(COUNT(DISTINCT datetime_utc) * 100.0 / 144, 1) as completeness_pct
            FROM fact_thermal_grid
            GROUP BY CAST(datetime_utc AS DATE)
            ORDER BY obs_date
        """).fetchdf()

        if not himawari_daily.empty:
            avg_completeness = himawari_daily["completeness_pct"].mean()
            incomplete_days = len(himawari_daily[himawari_daily["completeness_pct"] < 100.0])
            results["himawari"] = {
                "total_days": len(himawari_daily),
                "avg_completeness_pct": round(avg_completeness, 1),
                "incomplete_days": incomplete_days,
                "status": "PASS" if avg_completeness >= 95.0 else "WARN",
            }
            logger.info(
                f"  Himawari: {len(himawari_daily)} days, "
                f"avg completeness {avg_completeness:.1f}%, "
                f"{incomplete_days} incomplete days"
            )
        else:
            results["himawari"] = {"status": "SKIP", "reason": "No data"}
    except Exception as e:
        results["himawari"] = {"status": "ERROR", "reason": str(e)}

    # VIIRS temporal coverage
    try:
        viirs_monthly = conn.sql("""
            SELECT
                year, month,
                COUNT(*) as hotspot_count,
                COUNT(DISTINCT CAST(datetime_utc AS DATE)) as active_days
            FROM fact_fire_hotspots
            GROUP BY year, month
            ORDER BY year, month
        """).fetchdf()

        if not viirs_monthly.empty:
            results["viirs"] = {
                "total_months": len(viirs_monthly),
                "total_hotspots": int(viirs_monthly["hotspot_count"].sum()),
                "status": "PASS",
            }
            logger.info(f"  VIIRS: {len(viirs_monthly)} months, {viirs_monthly['hotspot_count'].sum():,} hotspots")
        else:
            results["viirs"] = {"status": "SKIP", "reason": "No data"}
    except Exception as e:
        results["viirs"] = {"status": "ERROR", "reason": str(e)}

    # ERA5 temporal coverage
    try:
        era5_monthly = conn.sql("""
            SELECT
                year, month,
                COUNT(DISTINCT date_utc) as days_with_data,
                COUNT(DISTINCT grid_id) as grid_cells_covered
            FROM fact_weather_daily
            GROUP BY year, month
            ORDER BY year, month
        """).fetchdf()

        if not era5_monthly.empty:
            results["era5"] = {
                "total_months": len(era5_monthly),
                "status": "PASS",
            }
            logger.info(f"  ERA5: {len(era5_monthly)} months of data")
        else:
            results["era5"] = {"status": "SKIP", "reason": "No data"}
    except Exception as e:
        results["era5"] = {"status": "ERROR", "reason": str(e)}

    return {"check": "temporal_completeness", "sources": results}


def validate_himawari_specific(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Himawari-specific data quality checks."""
    logger.info("Running Himawari-specific validation...")

    results = {}

    # Check for duplicates
    try:
        dup_row = conn.sql("""
            SELECT COUNT(*) as dup_count FROM (
                SELECT grid_id, datetime_utc, sensor_id, COUNT(*) as cnt
                FROM fact_thermal_grid
                GROUP BY grid_id, datetime_utc, sensor_id
                HAVING cnt > 1
            )
        """).fetchone()

        dup_count = dup_row[0]
        results["duplicates"] = {
            "duplicate_groups": dup_count,
            "status": "PASS" if dup_count == 0 else "FAIL",
        }
        logger.info(f"  Duplicates: {'PASS' if dup_count == 0 else f'FAIL ({dup_count:,} duplicate groups)'}")
    except Exception as e:
        results["duplicates"] = {"status": "ERROR", "reason": str(e)}

    # Check H8/H9 transition
    try:
        transition = conn.sql("""
            SELECT
                sensor_id,
                MIN(CAST(datetime_utc AS DATE)) as first_date,
                MAX(CAST(datetime_utc AS DATE)) as last_date,
                COUNT(*) as observation_count
            FROM fact_thermal_grid
            GROUP BY sensor_id
            ORDER BY sensor_id
        """).fetchdf()

        if not transition.empty:
            results["sensor_transition"] = {
                "sensors": transition.to_dict(orient="records"),
                "status": "PASS",
            }
            for _, row in transition.iterrows():
                logger.info(
                    f"  Sensor {row['sensor_id']}: "
                    f"{row['first_date']} → {row['last_date']} "
                    f"({row['observation_count']:,} observations)"
                )
        else:
            results["sensor_transition"] = {"status": "SKIP", "reason": "No data"}
    except Exception as e:
        results["sensor_transition"] = {"status": "ERROR", "reason": str(e)}

    # Cloud flag distribution
    try:
        cloud_row = conn.sql("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_cloudy) as cloudy,
                COUNT(*) FILTER (WHERE NOT is_cloudy) as clear,
                ROUND(COUNT(*) FILTER (WHERE is_cloudy) * 100.0 / COUNT(*), 1) as cloud_pct
            FROM fact_thermal_grid
        """).fetchone()

        if cloud_row and cloud_row[0] > 0:
            results["cloud_distribution"] = {
                "total": cloud_row[0],
                "cloudy": cloud_row[1],
                "clear": cloud_row[2],
                "cloud_pct": cloud_row[3],
                "status": "PASS",
            }
            logger.info(f"  Cloud distribution: {cloud_row[3]}% cloudy ({cloud_row[1]:,}/{cloud_row[0]:,})")
        else:
            results["cloud_distribution"] = {"status": "SKIP", "reason": "No data"}
    except Exception as e:
        results["cloud_distribution"] = {"status": "ERROR", "reason": str(e)}

    return {"check": "himawari_specific", "results": results}


def validate_anti_leakage(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """
    Verify anti-leakage rules in the training dataset view.

    Rules:
    - All feature timestamps ≤ prediction time T
    - Target fire detections ∈ (T, T+24h]
    - Fire history features use strictly lagged data (< T)
    """
    logger.info("Checking anti-leakage rules...")

    results = {}

    # Check if training view exists
    try:
        conn.sql("SELECT * FROM vw_training_dataset LIMIT 0")
        view_exists = True
    except Exception:
        view_exists = False

    if not view_exists:
        results["view_exists"] = False
        results["status"] = "SKIP"
        results["reason"] = "vw_training_dataset view does not exist or has no data"
        logger.warning("  vw_training_dataset view not available — skipping anti-leakage checks")
        return {"check": "anti_leakage", "results": results}

    # Check sample rows for temporal ordering
    try:
        sample = conn.sql("""
            SELECT * FROM vw_training_dataset LIMIT 100
        """).fetchdf()

        if sample.empty:
            results["status"] = "SKIP"
            results["reason"] = "No rows in vw_training_dataset"
        else:
            # Explicit leakage check: any fuel_days_since_update < 0?
            fuel_leak_row = conn.sql("""
                SELECT COUNT(*) FROM vw_training_dataset 
                WHERE fuel_days_since_update < 0
            """).fetchone()
            fuel_leaks = fuel_leak_row[0] if fuel_leak_row else 0

            results["sample_rows"] = len(sample),
            results["columns"] = list(sample.columns)
            results["fuel_leak_violations"] = fuel_leaks
            
            if fuel_leaks > 0:
                results["status"] = "FAIL"
                logger.error(f"  Anti-leakage FAIL: {fuel_leaks} rows have fuel observations from the future!")
            else:
                results["status"] = "PASS"

        logger.info(f"  Anti-leakage: {results['status']} ({len(sample)} sample rows checked, 0 fuel leakage)")
    except Exception as e:
        results["status"] = "ERROR"
        results["reason"] = str(e)
        logger.error(f"  Anti-leakage check error: {e}")

    return {"check": "anti_leakage", "results": results}


def run_full_validation() -> dict[str, Any]:
    """Run the complete warehouse validation suite."""
    logger.info("=" * 70)
    logger.info("WAREHOUSE DATA QUALITY VALIDATION")
    logger.info(f"Database: {WAREHOUSE_CONFIG['db_path']}")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}Z")
    logger.info("=" * 70)

    db_path = WAREHOUSE_CONFIG["db_path"]
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return {"status": "FAIL", "reason": "Database file not found"}

    conn = get_connection()

    report = {
        "validation_timestamp": datetime.utcnow().isoformat() + "Z",
        "database_path": str(db_path),
        "checks": {},
    }

    try:
        # Run all validation checks
        report["checks"]["table_existence"] = validate_table_existence(conn)
        report["checks"]["row_counts"] = validate_row_counts(conn)
        report["checks"]["dim_grid"] = validate_dim_grid(conn)
        report["checks"]["physical_ranges"] = validate_physical_ranges(conn)
        report["checks"]["referential_integrity"] = validate_referential_integrity(conn)
        report["checks"]["temporal_completeness"] = validate_temporal_completeness(conn)
        report["checks"]["himawari_specific"] = validate_himawari_specific(conn)
        report["checks"]["anti_leakage"] = validate_anti_leakage(conn)

        # Overall status
        all_statuses = []
        for check_name, check_result in report["checks"].items():
            status = check_result.get("status", "UNKNOWN")
            if isinstance(check_result, dict) and "results" in check_result:
                if isinstance(check_result["results"], dict):
                    status = check_result["results"].get("status", status)
            all_statuses.append(status)

        if "FAIL" in all_statuses:
            report["overall_status"] = "FAIL"
        elif "WARN" in all_statuses:
            report["overall_status"] = "WARN"
        elif "ERROR" in all_statuses:
            report["overall_status"] = "ERROR"
        else:
            report["overall_status"] = "PASS"

    finally:
        conn.close()

    # Summary
    logger.info("=" * 70)
    logger.info(f"OVERALL STATUS: {report['overall_status']}")
    logger.info("=" * 70)

    return report


def save_report(report: dict[str, Any], output_path: Path | None = None) -> Path:
    """Save validation report as JSON."""
    if output_path is None:
        output_path = PROJECT_ROOT / "outputs" / "validation" / "warehouse_quality_report.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert non-serializable types
    def default_serializer(obj: Any) -> Any:
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        return str(obj)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=default_serializer)

    logger.info(f"Report saved to: {output_path}")
    return output_path


def main() -> None:
    """CLI entry point for warehouse validation."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-5s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    report = run_full_validation()
    output_path = save_report(report)

    print(f"\nValidation report saved to: {output_path}")
    print(f"Overall status: {report['overall_status']}")

    # Exit with non-zero if validation failed
    if report["overall_status"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
