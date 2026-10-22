import argparse
import logging
import json
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, Any, List

from config.settings import BMKG_CONFIG
from etl.load_warehouse import (
    load_dataframe,
    get_connection,
    assign_grid_id,
    deduplicate_table
)

logger = logging.getLogger(__name__)

def extract_bmkg_json(raw_dir: str) -> List[Dict[str, Any]]:
    """
    Read BMKG JSON files from raw_dir and fallbacks.
    """
    p = Path(raw_dir)
    json_files = list(p.glob("*.json")) if p.exists() else []
    
    if not json_files:
        alt_p = Path("data/bmkg/raw")
        if alt_p.exists():
            json_files = list(alt_p.glob("*.json"))
            if json_files:
                logger.info(f"Using fallback BMKG raw directory {alt_p} ({len(json_files)} files)")
                
    data_list = []
    for fpath in json_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data_list.append(data)
        except Exception as e:
            logger.error(f"Error reading {fpath}: {e}")
            
    return data_list

def transform_bmkg_data(data_list: List[Dict[str, Any]]) -> (pd.DataFrame, pd.DataFrame):
    """
    Transform BMKG JSON data into:
    1. df_adm4: metadata for dim_adm4
    2. df_forecast: forecast time series for fact_forecast_3h
    """
    adm4_rows = []
    forecast_rows = []
    
    for doc in data_list:
        lokasi = doc.get("lokasi", {})
        adm4_code = lokasi.get("adm4")
        if not adm4_code and "data" in doc and doc["data"]:
            lokasi = doc["data"][0].get("lokasi", {})
            adm4_code = lokasi.get("adm4")
            
        if not adm4_code:
            continue
            
        lat = lokasi.get("lat")
        lon = lokasi.get("lon")
        
        # Build dim_adm4 row
        nearest_grid = assign_grid_id(float(lat), float(lon)) if (lat is not None and lon is not None) else None
        adm4_rows.append({
            "adm4_code": str(adm4_code),
            "provinsi": lokasi.get("provinsi"),
            "kabupaten_kota": lokasi.get("kotkab"),
            "kecamatan": lokasi.get("kecamatan"),
            "desa_kelurahan": lokasi.get("desa"),
            "lat": float(lat) if lat is not None else None,
            "lon": float(lon) if lon is not None else None,
            "nearest_grid_id": nearest_grid,
        })
        
        # Build fact_forecast_3h rows
        data_blocks = doc.get("data", [])
        for block in data_blocks:
            cuaca_days = block.get("cuaca", [])
            for day_steps in cuaca_days:
                if not isinstance(day_steps, list):
                    day_steps = [day_steps]
                for step in day_steps:
                    dt_str = step.get("datetime")
                    if not dt_str:
                        continue
                    dt_utc = pd.to_datetime(dt_str, utc=True)
                    analysis_dt = step.get("analysis_date", dt_str)
                    
                    forecast_rows.append({
                        "adm4_code": str(adm4_code),
                        "forecast_datetime_utc": dt_utc,
                        "analysis_datetime_utc": pd.to_datetime(analysis_dt, utc=True),
                        "temp_c": float(step.get("t", 0.0)) if step.get("t") is not None else None,
                        "humidity_pct": float(step.get("hu", 0.0)) if step.get("hu") is not None else None,
                        "precip_mm": float(step.get("tp", 0.0)) if step.get("tp") is not None else None,
                        "wind_speed_kmh": float(step.get("ws", 0.0)) if step.get("ws") is not None else None,
                        "cloud_cover_pct": float(step.get("tcc", 0.0)) if step.get("tcc") is not None else None,
                        "weather_code": int(step.get("weather", 0)) if step.get("weather") is not None else None,
                        "year": dt_utc.year,
                        "month": dt_utc.month,
                    })
                    
    df_adm4 = pd.DataFrame(adm4_rows).drop_duplicates(subset=["adm4_code"]) if adm4_rows else pd.DataFrame()
    df_forecast = pd.DataFrame(forecast_rows).drop_duplicates(subset=["adm4_code", "forecast_datetime_utc"]) if forecast_rows else pd.DataFrame()
    
    return df_adm4, df_forecast

def load_bmkg(df_adm4: pd.DataFrame, df_forecast: pd.DataFrame) -> None:
    """
    Load dim_adm4 and fact_forecast_3h into DuckDB.
    """
    if not df_adm4.empty:
        load_dataframe(df_adm4, "dim_adm4", mode="append")
        deduplicate_table("dim_adm4", ["adm4_code"])
        logger.info(f"Loaded {len(df_adm4)} village records into dim_adm4.")
        
    if not df_forecast.empty:
        load_dataframe(df_forecast, "fact_forecast_3h", mode="append")
        deduplicate_table("fact_forecast_3h", ["adm4_code", "forecast_datetime_utc"])
        logger.info(f"Loaded {len(df_forecast)} forecast records into fact_forecast_3h.")

def run(raw_dir: str = None, fetch_live: bool = False) -> None:
    logger.info("Starting BMKG ETL process...")
    if raw_dir is None:
        raw_dir = "data/raw/bmkg"
        
    data_list = extract_bmkg_json(raw_dir)
    df_adm4, df_forecast = transform_bmkg_data(data_list)
    
    # Also fallback to preprocessed CSV if JSON was empty
    if df_forecast.empty:
        csv_path = Path("data/bmkg/processed/bmkg_kalimantan_weather_sample.csv")
        if csv_path.exists():
            logger.info(f"Loading from preprocessed CSV fallback: {csv_path}")
            df_csv = pd.read_csv(csv_path)
            
            # Build dim_adm4 from CSV
            adm4_df = df_csv[["adm4", "provinsi", "kabupaten_kota", "kecamatan", "desa_kelurahan", "latitude", "longitude"]].drop_duplicates().copy()
            adm4_df = adm4_df.rename(columns={"adm4": "adm4_code", "latitude": "lat", "longitude": "lon"})
            adm4_df["nearest_grid_id"] = adm4_df.apply(lambda r: assign_grid_id(r["lat"], r["lon"]), axis=1)
            
            # Build fact_forecast_3h from CSV
            df_csv["forecast_datetime_utc"] = pd.to_datetime(df_csv["datetime_utc"], utc=True)
            df_csv["analysis_datetime_utc"] = pd.to_datetime(df_csv["analysis_date"], utc=True)
            df_csv["year"] = df_csv["forecast_datetime_utc"].dt.year
            df_csv["month"] = df_csv["forecast_datetime_utc"].dt.month
            
            fc_df = df_csv.rename(columns={
                "adm4": "adm4_code",
                "temperature_c": "temp_c",
                "humidity_pct": "humidity_pct",
                "precipitation_mm": "precip_mm",
                "wind_speed_kmh": "wind_speed_kmh",
                "cloud_cover_pct": "cloud_cover_pct",
                "weather_code": "weather_code"
            })
            
            cols = [
                "adm4_code", "forecast_datetime_utc", "analysis_datetime_utc",
                "temp_c", "humidity_pct", "precip_mm", "wind_speed_kmh",
                "cloud_cover_pct", "weather_code", "year", "month"
            ]
            fc_df = fc_df[[c for c in cols if c in fc_df.columns]]
            load_bmkg(adm4_df, fc_df)
            return
            
    load_bmkg(df_adm4, df_forecast)
    logger.info("BMKG ETL complete.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="BMKG ETL Pipeline")
    parser.add_argument("--raw_dir", type=str, default="data/raw/bmkg")
    parser.add_argument("--fetch_live", action="store_true")
    
    args = parser.parse_args()
    run(raw_dir=args.raw_dir, fetch_live=args.fetch_live)
