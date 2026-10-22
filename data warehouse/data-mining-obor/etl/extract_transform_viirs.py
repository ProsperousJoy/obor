import sys
import argparse
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import BORNEO_BBOX, VIIRS_CONFIG
from etl.load_warehouse import (
    load_dataframe,
    deduplicate_table,
    validate_ranges,
    assign_grid_id,
    get_connection
)

logger = logging.getLogger(__name__)

def extract_viirs(raw_dir: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
    """
    Read VIIRS CSV files from raw_dir, filter by date range.
    Fallback to data/viirs/raw if raw_dir is empty or does not exist.
    """
    p = Path(raw_dir)
    dfs = []
    
    csv_files = list(p.glob("*.csv")) if p.exists() else []
    if not csv_files:
        alt_p = Path("data/viirs/raw")
        if alt_p.exists():
            csv_files = list(alt_p.glob("*.csv"))
            logger.info(f"Using fallback directory {alt_p} ({len(csv_files)} files found)")
            
    if not csv_files:
        logger.warning(f"No CSV files found in {raw_dir} or fallback.")
        return pd.DataFrame()
        
    for file_path in csv_files:
        try:
            df = pd.read_csv(file_path, on_bad_lines='skip')
            if start_date or end_date:
                df['acq_date_dt'] = pd.to_datetime(df['acq_date'])
                if start_date:
                    df = df[df['acq_date_dt'] >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df['acq_date_dt'] <= pd.to_datetime(end_date)]
                df = df.drop(columns=['acq_date_dt'])
            dfs.append(df)
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
        
    if not dfs:
        return pd.DataFrame()
        
    return pd.concat(dfs, ignore_index=True)

def transform_viirs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter Kalimantan bbox, parse datetime, compute delta_bt, assign grid_id, 
    determine sensor_id, map column names to schema, add year/month.
    """
    if df.empty:
        return df
        
    # Standardize column names
    lat_col = 'latitude' if 'latitude' in df.columns else 'lat'
    lon_col = 'longitude' if 'longitude' in df.columns else 'lon'
    
    # Filter by BBOX
    lat_min, lat_max = BORNEO_BBOX['lat_min'], BORNEO_BBOX['lat_max']
    lon_min, lon_max = BORNEO_BBOX['lon_min'], BORNEO_BBOX['lon_max']
    
    df = df[
        (df[lat_col] >= lat_min) & (df[lat_col] <= lat_max) &
        (df[lon_col] >= lon_min) & (df[lon_col] <= lon_max)
    ].copy()
    
    if df.empty:
        return df
        
    # Parse datetime_utc
    # Format acq_time: e.g. 548 -> "0548" -> 05:48
    if 'acq_time' in df.columns:
        df['acq_time_str'] = df['acq_time'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(4)
        df['datetime_utc'] = pd.to_datetime(
            df['acq_date'].astype(str) + ' ' + 
            df['acq_time_str'].str[:2] + ':' + df['acq_time_str'].str[2:4],
            utc=True
        )
    elif 'datetime_utc' in df.columns:
        df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
    else:
        df['datetime_utc'] = pd.to_datetime(df['acq_date'], utc=True)
        
    # Map alternate column names from FIRMS archive (brightness -> bright_ti4, bright_t31 -> bright_ti5)
    if 'brightness' in df.columns and 'bright_ti4' not in df.columns:
        df['bright_ti4'] = df['brightness']
    if 'bright_t31' in df.columns and 'bright_ti5' not in df.columns:
        df['bright_ti5'] = df['bright_t31']

    # Delta BT (difference between bright_ti4 and bright_ti5)
    if 'bright_ti4' in df.columns and 'bright_ti5' in df.columns:
        df['delta_bt_k'] = df['bright_ti4'] - df['bright_ti5']
    elif 'bright_ti4_k' in df.columns and 'bright_ti5_k' in df.columns:
        df['delta_bt_k'] = df['bright_ti4_k'] - df['bright_ti5_k']
    else:
        df['delta_bt_k'] = None
        
    # Assign Grid ID
    df['grid_id'] = df.apply(lambda row: assign_grid_id(row[lat_col], row[lon_col]), axis=1)
    
    # Map Sensor ID to dim_sensor (VIIRS_N20 / VIIRS_N21 / VIIRS_SNPP)
    sensor_map = {
        'N20': 'VIIRS_N20',
        'N21': 'VIIRS_N21',
        'N': 'VIIRS_N20',
        'NOAA-20': 'VIIRS_N20',
        'NOAA-21': 'VIIRS_N21',
        'SNPP': 'VIIRS_SNPP',
        'S-NPP': 'VIIRS_SNPP',
        'SUOMI': 'VIIRS_SNPP',
        'Suomi-NPP': 'VIIRS_SNPP'
    }
    if 'satellite' in df.columns:
        df['sensor_id'] = df['satellite'].astype(str).str.strip().map(sensor_map).fillna('VIIRS_N20')
    elif 'instrument' in df.columns:
        df['sensor_id'] = df['instrument'].astype(str).str.strip().map(sensor_map).fillna('VIIRS_N20')
    else:
        df['sensor_id'] = 'VIIRS_N20'
        
    # Rename columns to schema definitions
    col_mapping = {
        lat_col: 'lat',
        lon_col: 'lon',
        'bright_ti4': 'bright_ti4_k',
        'bright_ti5': 'bright_ti5_k',
        'frp': 'frp_mw',
    }
    df = df.rename(columns=col_mapping)
    
    # Add year/month partitions
    df['year'] = df['datetime_utc'].dt.year
    df['month'] = df['datetime_utc'].dt.month
    
    target_cols = [
        'grid_id', 'datetime_utc', 'lat', 'lon',
        'bright_ti4_k', 'bright_ti5_k', 'delta_bt_k', 'frp_mw',
        'confidence', 'daynight', 'sensor_id', 'year', 'month'
    ]
    for c in target_cols:
        if c not in df.columns:
            df[c] = None
            
    return df[target_cols]

def generate_agg_fire_history(conn) -> None:
    """
    Generate lagged fire activity metrics for agg_fire_history across active 7-day windows:
    hotspot_count_prev_24h, hotspot_count_prev_7d, max_frp_prev_7d, sum_frp_prev_7d, has_recent_fire_7d
    Ensures zero-fire days retain preceding fire indicators strictly before T.
    """
    logger.info("Computing agg_fire_history table...")
    query = """
    CREATE OR REPLACE TABLE agg_fire_history AS
    WITH daily_fires AS (
        SELECT 
            grid_id, 
            CAST(datetime_utc AS DATE) AS fire_date, 
            COUNT(*)::INTEGER AS cnt, 
            MAX(frp_mw)::DOUBLE AS max_frp, 
            SUM(frp_mw)::DOUBLE AS sum_frp
        FROM fact_fire_hotspots
        GROUP BY grid_id, CAST(datetime_utc AS DATE)
    ),
    active_history_frames AS (
        SELECT DISTINCT 
            grid_id, 
            (fire_date + i::INTEGER)::DATE AS date_utc
        FROM daily_fires
        CROSS JOIN (SELECT UNNEST(generate_series(1, 7)) AS i)
    )
    SELECT 
        h.grid_id,
        h.date_utc,
        COALESCE(d1.cnt, 0)::INTEGER AS hotspot_count_prev_24h,
        SUM(COALESCE(df.cnt, 0))::INTEGER AS hotspot_count_prev_7d,
        MAX(COALESCE(df.max_frp, 0.0))::DOUBLE AS max_frp_prev_7d,
        SUM(COALESCE(df.sum_frp, 0.0))::DOUBLE AS sum_frp_prev_7d,
        (SUM(COALESCE(df.cnt, 0)) > 0)::BOOLEAN AS has_recent_fire_7d,
        EXTRACT(YEAR FROM h.date_utc)::INTEGER AS year,
        EXTRACT(MONTH FROM h.date_utc)::INTEGER AS month
    FROM active_history_frames h
    LEFT JOIN daily_fires d1 
        ON h.grid_id = d1.grid_id 
        AND h.date_utc = (d1.fire_date + 1::INTEGER)::DATE
    LEFT JOIN daily_fires df 
        ON h.grid_id = df.grid_id 
        AND df.fire_date >= (h.date_utc - 7::INTEGER)::DATE 
        AND df.fire_date < h.date_utc
    GROUP BY h.grid_id, h.date_utc, d1.cnt;
    """
    conn.execute(query)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_fire_hist_pk ON agg_fire_history (grid_id, date_utc)")
    logger.info("Generated agg_fire_history successfully.")

def load_viirs(df: pd.DataFrame) -> None:
    """
    Load into fact_fire_hotspots, deduplicate, and compute agg_fire_history.
    """
    if df.empty:
        logger.info("No VIIRS data to load.")
        return
        
    validations = {
        'bright_ti4_k': (180.0, 500.0),
        'frp_mw': (0.0, 2000.0)
    }
    validate_ranges(df, validations)
    
    table_name = 'fact_fire_hotspots'
    load_dataframe(df, table_name, mode='append')
    deduplicate_table(table_name, ['datetime_utc', 'lat', 'lon'])
    
    conn = get_connection()
    generate_agg_fire_history(conn)

def run(raw_dir: str = None, start_date: str = None, end_date: str = None) -> None:
    """
    Orchestrate extract -> transform -> load.
    """
    logger.info("Starting VIIRS ETL process...")
    if raw_dir is None:
        raw_dir = "data/raw/viirs"
        
    df_raw = extract_viirs(raw_dir, start_date, end_date)
    logger.info(f"Extracted {len(df_raw)} raw VIIRS records.")
    
    df_transformed = transform_viirs(df_raw)
    logger.info(f"Transformed to {len(df_transformed)} VIIRS records.")
    
    load_viirs(df_transformed)
    logger.info("VIIRS ETL complete.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="VIIRS ETL Pipeline")
    parser.add_argument("--raw_dir", type=str, default="data/raw/viirs", help="Directory of raw CSV files")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD")
    
    args = parser.parse_args()
    run(raw_dir=args.raw_dir, start_date=args.start, end_date=args.end)
