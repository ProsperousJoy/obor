import sys
import argparse
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import BORNEO_BBOX
from etl.load_warehouse import (
    load_dataframe,
    get_connection,
    assign_grid_id,
    deduplicate_table
)

logger = logging.getLogger(__name__)

def extract_era5(raw_dir: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
    """
    Read ERA5 CSV/JSON files from raw_dir and fallbacks.
    """
    p = Path(raw_dir)
    dfs = []
    
    csv_files = list(p.glob("*.csv")) if p.exists() else []
    if not csv_files:
        for alt_path in ["data/gee/processed", "data/gee/raw"]:
            alt_p = Path(alt_path)
            if alt_p.exists():
                found = list(alt_p.glob("*.csv"))
                if found:
                    csv_files.extend(found)
                    logger.info(f"Using fallback ERA5 directory {alt_path} ({len(found)} files)")
                    break
                    
    if not csv_files:
        logger.warning(f"No ERA5 CSV files found in {raw_dir} or fallbacks.")
        return pd.DataFrame()
        
    for file_path in csv_files:
        try:
            df = pd.read_csv(file_path)
            if 'date' in df.columns:
                if start_date or end_date:
                    df['date_dt'] = pd.to_datetime(df['date'])
                    if start_date:
                        df = df[df['date_dt'] >= pd.to_datetime(start_date)]
                    if end_date:
                        df = df[df['date_dt'] <= pd.to_datetime(end_date)]
                    df = df.drop(columns=['date_dt'])
            dfs.append(df)
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            
    if not dfs:
        return pd.DataFrame()
        
    return pd.concat(dfs, ignore_index=True)

def transform_era5(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive RH, wind_speed, wind_dir. Map to canonical grid. Add year/month.
    """
    if df.empty:
        return df
        
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
        
    # Derive Relative Humidity (Magnus equation) if not present
    if 'relative_humidity_mean_pct' not in df.columns and 'rh' not in df.columns:
        if 't2m' in df.columns and 'd2m' in df.columns:
            T = df['t2m'] - 273.15 if df['t2m'].max() > 100 else df['t2m']
            Td = df['d2m'] - 273.15 if df['d2m'].max() > 100 else df['d2m']
            num = np.exp((17.625 * Td) / (243.04 + Td))
            den = np.exp((17.625 * T) / (243.04 + T))
            df['rh_mean_pct'] = 100.0 * (num / den)
    elif 'relative_humidity_mean_pct' in df.columns:
        df['rh_mean_pct'] = df['relative_humidity_mean_pct']
    elif 'rh' in df.columns:
        df['rh_mean_pct'] = df['rh']

    if 'relative_humidity_min_pct' in df.columns:
        df['rh_min_pct'] = df['relative_humidity_min_pct']
        
    # Map temperature
    if 't2m_mean_c' in df.columns:
        pass
    elif 't2m' in df.columns:
        df['t2m_mean_c'] = df['t2m'] - 273.15 if df['t2m'].max() > 100 else df['t2m']
        
    if 't2m_max_c' not in df.columns:
        df['t2m_max_c'] = df.get('t2m_mean_c')
    if 't2m_min_c' not in df.columns:
        df['t2m_min_c'] = df.get('t2m_mean_c')
        
    # Dewpoint
    if 'dewpoint_mean_c' in df.columns:
        df['dewpoint_c'] = df['dewpoint_mean_c']
    elif 'd2m' in df.columns:
        df['dewpoint_c'] = df['d2m'] - 273.15 if df['d2m'].max() > 100 else df['d2m']
        
    # Precipitation
    if 'total_precip_mm' in df.columns:
        df['precip_mm'] = df['total_precip_mm']
    elif 'tp' in df.columns:
        df['precip_mm'] = df['tp'] * 1000.0 if df['tp'].max() < 1.0 else df['tp']
        
    # Wind speed & direction
    if 'wind_speed_10m_mean_kmh' in df.columns:
        df['wind_speed_kmh'] = df['wind_speed_10m_mean_kmh']
    elif 'u10' in df.columns and 'v10' in df.columns:
        u = df['u10']
        v = df['v10']
        df['wind_speed_kmh'] = np.sqrt(u**2 + v**2) * 3.6  # m/s to km/h
        df['wind_dir_deg'] = (270.0 - np.arctan2(v, u) * (180.0 / np.pi)) % 360.0
        
    if 'wind_direction_10m_deg' in df.columns:
        df['wind_dir_deg'] = df['wind_direction_10m_deg']

    if 'soil_moisture_0_7cm_m3m3' in df.columns:
        df['soil_moisture_0_7cm'] = df['soil_moisture_0_7cm_m3m3']
        
    # Map to canonical grid
    df['grid_id'] = df.apply(lambda row: assign_grid_id(row[lat_col], row[lon_col]), axis=1)
    
    # Ensure UTC date
    df['date_utc'] = pd.to_datetime(df['date']).dt.date
    df['year'] = pd.to_datetime(df['date']).dt.year
    df['month'] = pd.to_datetime(df['date']).dt.month
    
    schema_cols = [
        'grid_id', 'date_utc', 't2m_mean_c', 't2m_max_c', 't2m_min_c',
        'dewpoint_c', 'rh_mean_pct', 'rh_min_pct', 'precip_mm',
        'wind_speed_kmh', 'wind_dir_deg', 'surface_pressure_hpa',
        'soil_moisture_0_7cm', 'soil_moisture_rootzone', 'year', 'month'
    ]
    for c in schema_cols:
        if c not in df.columns:
            df[c] = None
            
    df = df.drop_duplicates(subset=['grid_id', 'date_utc'])
    return df[schema_cols]

def compute_rolling_features(conn) -> None:
    """
    SQL-based rolling window computation for rain_accum_7d_mm, rain_accum_30d_mm, 
    consecutive_dry_days, t2m_anomaly_vs_30d_mean.
    """
    logger.info("Computing agg_weather_rolling table...")
    query = """
    CREATE OR REPLACE TABLE agg_weather_rolling AS
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
    conn.execute(query)
    logger.info("agg_weather_rolling computed successfully.")

def load_era5(df: pd.DataFrame) -> None:
    """
    Load into fact_weather_daily and compute agg_weather_rolling.
    """
    if df.empty:
        logger.info("No ERA5 data to load.")
        return
        
    table_name = 'fact_weather_daily'
    conn = get_connection()
    conn.register('era5_stage', df)
    conn.execute(f"""
        DELETE FROM {table_name} 
        WHERE (grid_id, date_utc) IN (SELECT grid_id, date_utc FROM era5_stage)
    """)
    table_cols = conn.execute(f"DESCRIBE {table_name}").df()['column_name'].tolist()
    common_cols = [c for c in table_cols if c in df.columns]
    cols_str = ", ".join(common_cols)
    conn.execute(f"INSERT INTO {table_name} ({cols_str}) SELECT {cols_str} FROM era5_stage")
    conn.unregister('era5_stage')
    logger.info(f"Loaded {len(df)} records into {table_name}.")
    
    compute_rolling_features(conn)

def run(raw_dir: str = None, start_date: str = None, end_date: str = None) -> None:
    logger.info("Starting ERA5 ETL process...")
    if raw_dir is None:
        raw_dir = "data/raw/era5"
        
    df_raw = extract_era5(raw_dir, start_date, end_date)
    logger.info(f"Extracted {len(df_raw)} raw ERA5 records.")
    
    df_transformed = transform_era5(df_raw)
    logger.info(f"Transformed to {len(df_transformed)} ERA5 records.")
    
    load_era5(df_transformed)
    logger.info("ERA5 ETL complete.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="ERA5 ETL Pipeline")
    parser.add_argument("--raw_dir", type=str, default="data/raw/era5")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD")
    
    args = parser.parse_args()
    run(raw_dir=args.raw_dir, start_date=args.start, end_date=args.end)
