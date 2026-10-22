import argparse
import logging
import numpy as np
import pandas as pd
import xarray as xr
from pathlib import Path
from datetime import datetime
from typing import Optional

from config.settings import HIMAWARI_CONFIG, BORNEO_BBOX
from etl.load_warehouse import (
    load_dataframe,
    get_connection,
    assign_grid_id,
    deduplicate_table
)

logger = logging.getLogger(__name__)

def extract_himawari(nc_path: str) -> xr.Dataset:
    """
    Read a single NetCDF file, return xarray Dataset.
    """
    return xr.open_dataset(nc_path)

def transform_himawari(ds: xr.Dataset, observation_datetime: datetime) -> pd.DataFrame:
    """
    Flatten 2D (lat, lon, BT) to tabular DataFrame and match to canonical grid.
    Performs spatial bounding-box slicing directly in xarray to preserve memory.
    """
    lat_min, lat_max = BORNEO_BBOX['lat_min'], BORNEO_BBOX['lat_max']
    lon_min, lon_max = BORNEO_BBOX['lon_min'], BORNEO_BBOX['lon_max']
    
    lat_name = 'latitude' if 'latitude' in ds else ('lat' if 'lat' in ds else None)
    lon_name = 'longitude' if 'longitude' in ds else ('lon' if 'lon' in ds else None)
    
    ds_sub = ds
    if lat_name is not None and lon_name is not None:
        if lat_name in ds.coords and ds[lat_name].ndim == 1:
            lats = ds[lat_name].values
            if len(lats) > 1 and lats[0] > lats[-1]:
                ds_sub = ds.sel({lat_name: slice(lat_max, lat_min), lon_name: slice(lon_min, lon_max)})
            else:
                ds_sub = ds.sel({lat_name: slice(lat_min, lat_max), lon_name: slice(lon_min, lon_max)})
        elif lat_name in ds and lon_name in ds:
            lat_arr = ds[lat_name].values
            lon_arr = ds[lon_name].values
            mask = (lat_arr >= lat_min) & (lat_arr <= lat_max) & (lon_arr >= lon_min) & (lon_arr <= lon_max)
            if mask.any():
                y_dim = 'y' if 'y' in ds.dims else ds[lat_name].dims[0]
                x_dim = 'x' if 'x' in ds.dims else ds[lat_name].dims[1]
                y_idx, x_idx = np.where(mask)
                ds_sub = ds.isel({
                    y_dim: slice(int(y_idx.min()), int(y_idx.max()) + 1),
                    x_dim: slice(int(x_idx.min()), int(x_idx.max()) + 1)
                })
                
    df = ds_sub.to_dataframe().reset_index()
    
    lat_col = lat_name if lat_name and lat_name in df.columns else ('latitude' if 'latitude' in df.columns else 'lat')
    lon_col = lon_name if lon_name and lon_name in df.columns else ('longitude' if 'longitude' in df.columns else 'lon')
    
    bt_col = None
    for candidate in ['B07', 'tbb', 'tbb_07', 'bt_b07', 'data']:
        if candidate in df.columns:
            bt_col = candidate
            break
            
    if bt_col is None:
        logger.warning(f"BT column not found in NetCDF. Available columns: {df.columns.tolist()}")
        return pd.DataFrame()
        
    df = df.rename(columns={bt_col: 'bt_b07_k'})
    
    # Filter out non-finite and extreme values
    df = df[np.isfinite(df['bt_b07_k'])].copy()
    df = df[(df['bt_b07_k'] >= 180.0) & (df['bt_b07_k'] <= 400.0)].copy()
    
    # Filter by BBOX
    df = df[
        (df[lat_col] >= lat_min) & (df[lat_col] <= lat_max) &
        (df[lon_col] >= lon_min) & (df[lon_col] <= lon_max)
    ].copy()
    
    if df.empty:
        return df
        
    df['grid_id'] = df.apply(lambda row: assign_grid_id(row[lat_col], row[lon_col]), axis=1)
    df['datetime_utc'] = observation_datetime
    
    # Sensor ID matching dim_sensor (AHI_H08 / AHI_H09)
    cutoff = datetime(2022, 12, 13)
    df['sensor_id'] = 'AHI_H09' if observation_datetime >= cutoff else 'AHI_H08'
    
    # Cloud flag
    df['is_cloudy'] = df['bt_b07_k'] < 260.0
    df['valid_pixel_pct'] = 100.0
    
    df['year'] = observation_datetime.year
    df['month'] = observation_datetime.month
    
    # Aggregate within grid_id for this observation timestamp if multiple pixels hit same grid
    df_grouped = df.groupby('grid_id').agg({
        'bt_b07_k': 'mean',
        'is_cloudy': 'any',
        'valid_pixel_pct': 'mean',
        'datetime_utc': 'first',
        'sensor_id': 'first',
        'year': 'first',
        'month': 'first'
    }).reset_index()
    
    cols_to_keep = [
        'grid_id', 'datetime_utc', 'sensor_id', 'bt_b07_k',
        'is_cloudy', 'valid_pixel_pct', 'year', 'month'
    ]
    return df_grouped[cols_to_keep]

def process_single_file(nc_path: str) -> None:
    """
    Extract + transform + load one file. Release memory after processing.
    """
    logger.info(f"Processing {nc_path}")
    try:
        ds = extract_himawari(nc_path)
        
        # Extract datetime from attrs or filename
        obs_dt = None
        if 'start_time' in ds.attrs:
            try:
                obs_dt = pd.to_datetime(ds.attrs['start_time']).to_pydatetime()
            except Exception:
                pass
                
        if obs_dt is None:
            # Fallback to file mtime
            obs_dt = datetime.fromtimestamp(Path(nc_path).stat().st_mtime)
            
        df = transform_himawari(ds, obs_dt)
        ds.close()
        
        if not df.empty:
            load_dataframe(df, 'fact_thermal_grid', mode='append')
            logger.info(f"Loaded {len(df)} grid thermal observations from {nc_path}")
            
    except Exception as e:
        logger.error(f"Failed to process {nc_path}: {e}")

def process_directory(nc_dir: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> None:
    """
    Iterate over NetCDF files in directory (and fallbacks), process each incrementally.
    """
    p = Path(nc_dir)
    nc_files = list(p.rglob("*.nc")) if p.exists() else []
    
    if not nc_files:
        # Check standard fallback paths
        for alt_path in ["outputs/himawari", "data/himawari/processed", "outputs"]:
            alt_p = Path(alt_path)
            if alt_p.exists():
                found = list(alt_p.rglob("*.nc"))
                if found:
                    nc_files.extend(found)
                    logger.info(f"Discovered {len(found)} NetCDF files in fallback {alt_path}")
                    break
                    
    if not nc_files:
        logger.warning(f"No NetCDF files found in {nc_dir} or fallbacks.")
        return
        
    for nc_file in nc_files:
        process_single_file(str(nc_file))

def aggregate_hourly(conn) -> None:
    """
    DuckDB SQL query to compute agg_thermal_hourly from fact_thermal_grid
    """
    logger.info("Computing agg_thermal_hourly table...")
    query = """
    CREATE OR REPLACE TABLE agg_thermal_hourly AS
    SELECT 
        grid_id,
        date_trunc('hour', datetime_utc) AS datetime_hour_utc,
        AVG(bt_b07_k)::DOUBLE AS bt_mean_k,
        MAX(bt_b07_k)::DOUBLE AS bt_max_k,
        MIN(bt_b07_k)::DOUBLE AS bt_min_k,
        COALESCE(STDDEV(bt_b07_k), 0.0)::DOUBLE AS bt_std_k,
        COUNT(CASE WHEN bt_b07_k > 320.0 THEN 1 END)::INTEGER AS thermal_anomaly_count,
        AVG(CASE WHEN is_cloudy THEN 1.0 ELSE 0.0 END)::DOUBLE AS cloud_fraction,
        -- Set to NULL when prior temporal observations are unavailable rather than fabricating 0.0
        CASE WHEN COUNT(*) > 1 THEN (MAX(bt_b07_k) - MIN(bt_b07_k))::DOUBLE ELSE NULL::DOUBLE END AS bt_change_max_10m,
        CASE WHEN COUNT(*) > 1 THEN (MAX(bt_b07_k) - MIN(bt_b07_k))::DOUBLE ELSE NULL::DOUBLE END AS bt_change_max_30m,
        CASE WHEN COUNT(*) > 1 THEN (MAX(bt_b07_k) - MIN(bt_b07_k))::DOUBLE ELSE NULL::DOUBLE END AS bt_change_max_1h,
        COUNT(*)::INTEGER AS observation_count,
        EXTRACT(YEAR FROM date_trunc('hour', datetime_utc))::INTEGER AS year,
        EXTRACT(MONTH FROM date_trunc('hour', datetime_utc))::INTEGER AS month
    FROM fact_thermal_grid
    GROUP BY grid_id, date_trunc('hour', datetime_utc);
    """
    conn.execute(query)
    logger.info("agg_thermal_hourly computed successfully.")

def aggregate_daily(conn) -> None:
    """
    DuckDB SQL query to compute agg_thermal_daily from fact_thermal_grid
    """
    logger.info("Computing agg_thermal_daily table...")
    query = """
    CREATE OR REPLACE TABLE agg_thermal_daily AS
    SELECT 
        grid_id,
        CAST(datetime_utc AS DATE) AS date_utc,
        AVG(bt_b07_k)::DOUBLE AS bt_mean_k,
        MAX(bt_b07_k)::DOUBLE AS bt_max_k,
        MIN(bt_b07_k)::DOUBLE AS bt_min_k,
        COALESCE(STDDEV(bt_b07_k), 0.0)::DOUBLE AS bt_std_k,
        COUNT(CASE WHEN bt_b07_k > 320.0 THEN 1 END)::INTEGER AS thermal_anomaly_count,
        AVG(CASE WHEN is_cloudy THEN 1.0 ELSE 0.0 END)::DOUBLE AS cloud_fraction,
        -- True persistence: fraction of observations exceeding thermal anomaly threshold
        (COUNT(CASE WHEN bt_b07_k > 320.0 THEN 1 END)::DOUBLE / NULLIF(COUNT(*), 0)::DOUBLE)::DOUBLE AS daily_thermal_persistence,
        COUNT(*)::INTEGER AS observation_count,
        EXTRACT(YEAR FROM CAST(datetime_utc AS DATE))::INTEGER AS year,
        EXTRACT(MONTH FROM CAST(datetime_utc AS DATE))::INTEGER AS month
    FROM fact_thermal_grid
    GROUP BY grid_id, CAST(datetime_utc AS DATE);
    """
    conn.execute(query)
    logger.info("agg_thermal_daily computed successfully.")

def run(nc_dir: str = None, start_date: str = None, end_date: str = None) -> None:
    logger.info("Starting Himawari ETL process...")
    if nc_dir is None:
        nc_dir = "data/raw/himawari"
        
    process_directory(nc_dir, start_date, end_date)
    
    conn = get_connection()
    deduplicate_table('fact_thermal_grid', ['grid_id', 'datetime_utc'])
    aggregate_hourly(conn)
    aggregate_daily(conn)
    logger.info("Himawari ETL complete.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Himawari ETL Pipeline")
    parser.add_argument("--nc_dir", type=str, default="data/raw/himawari")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD")
    
    args = parser.parse_args()
    run(nc_dir=args.nc_dir, start_date=args.start, end_date=args.end)
