"""
ETL Pipeline: Fuel Condition & Vegetation Indices
-------------------------------------------------
Extracts vegetation indices (NDVI, EVI, NDMI) from processed archives,
maps to canonical 0.02° spatial grid, validates physical boundaries,
and loads into fact_fuel_condition in DuckDB.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import BORNEO_BBOX
from etl.load_warehouse import (
    load_dataframe,
    get_connection,
    assign_grid_id,
    deduplicate_table,
    validate_ranges
)

logger = logging.getLogger(__name__)


def extract_fuel(raw_dir: str = "data/fuel/processed", start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
    """
    Read processed fuel condition CSVs from raw_dir and fallbacks.
    """
    p = Path(raw_dir)
    dfs = []
    
    csv_files = list(p.glob("*.csv")) if p.exists() else []
    if not csv_files:
        alt_paths = ["data/fuel/raw", "data/samples"]
        for alt_path in alt_paths:
            alt_p = Path(alt_path)
            if alt_p.exists():
                found = list(alt_p.glob("*fuel*.csv"))
                if found:
                    csv_files.extend(found)
                    logger.info(f"Using fallback fuel directory {alt_path} ({len(found)} files)")
                    break

    if not csv_files:
        logger.warning(f"No fuel CSV files found in {raw_dir} or fallbacks.")
        return pd.DataFrame()

    for file_path in csv_files:
        try:
            df = pd.read_csv(file_path)
            if "date_utc" in df.columns:
                if start_date or end_date:
                    df["date_dt"] = pd.to_datetime(df["date_utc"])
                    if start_date:
                        df = df[df["date_dt"] >= pd.to_datetime(start_date)]
                    if end_date:
                        df = df[df["date_dt"] <= pd.to_datetime(end_date)]
                    df = df.drop(columns=["date_dt"])
            dfs.append(df)
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")

    if not dfs:
        return pd.DataFrame()

    return pd.concat(dfs, ignore_index=True)


def transform_fuel(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform and validate fuel condition observations:
    - Spatial filter for Kalimantan BBOX
    - Map to canonical grid_id
    - Filter physical ranges
    - Structure columns
    """
    if df.empty:
        return pd.DataFrame()

    # Ensure required columns
    required_cols = ["lat", "lon", "date_utc", "ndvi", "evi", "ndmi"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in fuel DataFrame: {missing}")

    # Spatial filter Kalimantan BBOX
    lat_min, lat_max = BORNEO_BBOX["lat_min"], BORNEO_BBOX["lat_max"]
    lon_min, lon_max = BORNEO_BBOX["lon_min"], BORNEO_BBOX["lon_max"]
    df = df[
        (df["lat"] >= lat_min) & (df["lat"] <= lat_max) &
        (df["lon"] >= lon_min) & (df["lon"] <= lon_max)
    ].copy()

    if df.empty:
        logger.warning("No fuel records within Kalimantan bounding box.")
        return pd.DataFrame()

    # Assign nearest canonical grid_id
    df["grid_id"] = df.apply(lambda r: assign_grid_id(float(r["lat"]), float(r["lon"])), axis=1)

    # Parse date components
    df["date_utc"] = pd.to_datetime(df["date_utc"]).dt.date
    df["year"] = pd.to_datetime(df["date_utc"]).dt.year
    df["month"] = pd.to_datetime(df["date_utc"]).dt.month

    # Physical range validations:
    # NDVI: [-0.2, 1.0]
    # EVI: [-0.2, 1.0]
    # NDMI: [-1.0, 1.0]
    validations = {
        "ndvi": (-0.2, 1.0),
        "evi": (-0.2, 1.0),
        "ndmi": (-1.0, 1.0)
    }
    validate_ranges(df, validations)

    # Filter out extreme outliers
    valid_mask = (
        (df["ndvi"] >= -0.2) & (df["ndvi"] <= 1.0) &
        (df["evi"] >= -0.2) & (df["evi"] <= 1.0) &
        (df["ndmi"] >= -1.0) & (df["ndmi"] <= 1.0)
    )
    df = df[valid_mask].copy()

    # Column alignment for fact_fuel_condition
    target_cols = ["grid_id", "date_utc", "ndvi", "evi", "ndmi", "year", "month"]
    return df[target_cols].drop_duplicates(subset=["grid_id", "date_utc"])


def run(
    raw_dir: str = "data/fuel/processed",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute full Fuel ETL pipeline.
    """
    logger.info("Starting Fuel Condition ETL...")
    raw_df = extract_fuel(raw_dir, start_date=start_date, end_date=end_date)
    if raw_df.empty:
        logger.warning("No raw fuel condition data extracted.")
        return {"rows_extracted": 0, "rows_loaded": 0}

    logger.info(f"Extracted {len(raw_df)} raw fuel records.")
    transformed_df = transform_fuel(raw_df)
    if transformed_df.empty:
        logger.warning("No fuel records after transformation.")
        return {"rows_extracted": len(raw_df), "rows_loaded": 0}

    rows_loaded = len(transformed_df)
    logger.info(f"Loading {rows_loaded} records into fact_fuel_condition...")
    load_dataframe(transformed_df, "fact_fuel_condition")
    deduplicate_table("fact_fuel_condition", ["grid_id", "date_utc"])

    logger.info(f"Fuel ETL completed successfully: {rows_loaded} rows loaded.")
    return {
        "rows_extracted": len(raw_df),
        "rows_loaded": rows_loaded
    }


def main():
    parser = argparse.ArgumentParser(description="ETL for Vegetation & Fuel Condition Indices")
    parser.add_argument("--raw-dir", default="data/fuel/processed", help="Path to processed fuel CSVs")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run(args.raw_dir, args.start_date, args.end_date)


if __name__ == "__main__":
    main()
