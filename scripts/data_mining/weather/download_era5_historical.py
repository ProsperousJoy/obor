"""
Historical Weather & Soil Moisture Downloader (ERA5-Land via Open-Meteo)
------------------------------------------------------------------------
Downloads 5-year daily meteorological reanalysis (2021-01-01 to 2025-12-31)
across Kalimantan provincial stations and key coordinate clusters.
"""

import sys
import time
import json
import logging
import argparse
import urllib.request
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import PROVINCIAL_CAPITALS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("era5_downloader")

OUTPUT_DIR = Path("data/gee/processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_location_history(
    name: str,
    lat: float,
    lon: float,
    start_date: str = "2021-01-01",
    end_date: str = "2025-12-31"
) -> pd.DataFrame:
    """
    Fetch hourly historical ERA5 reanalysis and aggregate to daily summary.
    """
    logger.info(f"Fetching {name} ({lat}, {lon}) for {start_date} to {end_date}...")
    
    url = (
        f"https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lat}&longitude={lon}&start_date={start_date}&end_date={end_date}&"
        f"hourly=temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,"
        f"surface_pressure,wind_speed_10m,wind_direction_10m,soil_moisture_0_to_7cm&"
        f"timezone=UTC"
    )
    
    req = urllib.request.Request(url, headers={"User-Agent": "WildfireRiskKalimantan/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        
    hourly = data.get("hourly", {})
    if not hourly or "time" not in hourly:
        logger.warning(f"No hourly data returned for {name}")
        return pd.DataFrame()
        
    df_h = pd.DataFrame(hourly)
    df_h["datetime_utc"] = pd.to_datetime(df_h["time"])
    df_h["date_utc"] = df_h["datetime_utc"].dt.date
    
    # Aggregate hourly to daily
    grouped = df_h.groupby("date_utc")
    df_daily = pd.DataFrame({
        "province": name,
        "lat": lat,
        "lon": lon,
        "date": grouped["date_utc"].first(),
        "t2m_mean_c": grouped["temperature_2m"].mean().round(2),
        "t2m_max_c": grouped["temperature_2m"].max().round(2),
        "t2m_min_c": grouped["temperature_2m"].min().round(2),
        "dewpoint_mean_c": grouped["dew_point_2m"].mean().round(2),
        "relative_humidity_mean_pct": grouped["relative_humidity_2m"].mean().round(1),
        "relative_humidity_min_pct": grouped["relative_humidity_2m"].min().round(1),
        "total_precip_mm": grouped["precipitation"].sum().round(2),
        "wind_speed_10m_mean_kmh": grouped["wind_speed_10m"].mean().round(2),
        "wind_direction_10m_deg": grouped["wind_direction_10m"].mean().round(1),
        "surface_pressure_hpa": grouped["surface_pressure"].mean().round(1),
        "soil_moisture_0_7cm_m3m3": grouped["soil_moisture_0_to_7cm"].mean().round(3),
        "status": "SUCCESS"
    }).reset_index(drop=True)
    
    logger.info(f"  {name}: Aggregated {len(df_daily)} daily records.")
    return df_daily


def run_batch_download(
    start_date: str = "2021-01-01",
    end_date: str = "2025-12-31",
    output_file: str = "data/gee/processed/kalimantan_era5land_2021_2025.csv"
):
    """
    Download across all 5 Kalimantan provincial centers and regional clusters.
    """
    all_dfs = []
    
    # 5 Provincial Capital Centers
    for prov, info in PROVINCIAL_CAPITALS.items():
        try:
            df = fetch_location_history(
                prov,
                info["lat"],
                info["lon"],
                start_date=start_date,
                end_date=end_date
            )
            all_dfs.append(df)
            time.sleep(1.0) # Polite rate limiting
        except Exception as e:
            logger.error(f"Failed to fetch {prov}: {e}")
            
    if not all_dfs:
        logger.error("No ERA5 data downloaded.")
        return
        
    merged = pd.concat(all_dfs, ignore_index=True)
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False)
    logger.info(f"Successfully saved {len(merged)} ERA5-Land records to {out_path}")
    return merged


def main():
    parser = argparse.ArgumentParser(description="Download 5-Year Historical ERA5-Land Weather")
    parser.add_argument("--start", default="2021-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2025-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", default="data/gee/processed/kalimantan_era5land_2021_2025.csv")
    args = parser.parse_args()
    
    run_batch_download(args.start, args.end, args.output)


if __name__ == "__main__":
    main()
