"""
Test sample extraction for Kalimantan study area across key environmental variables
corresponding to the datasets available in GEE (ERA5-Land reanalysis, CHIRPS rainfall).
"""

import json
import os
import requests
import pandas as pd
from pathlib import Path

LOCATIONS = [
    {"province": "Kalimantan Barat", "city": "Pontianak", "lat": -0.02, "lon": 109.34},
    {"province": "Kalimantan Tengah", "city": "Palangka Raya", "lat": -2.21, "lon": 113.92},
    {"province": "Kalimantan Selatan", "city": "Banjarmasin", "lat": -3.32, "lon": 114.59},
    {"province": "Kalimantan Timur", "city": "Samarinda", "lat": -0.50, "lon": 117.15},
    {"province": "Kalimantan Utara", "city": "Tanjung Selor", "lat": 2.84, "lon": 117.37},
]

def test_era5_land_extraction():
    """Query ERA5-Land hourly/daily reanalysis data (available in GEE as ECMWF/ERA5_LAND/DAILY_AGGR)."""
    print("Testing ERA5-Land extraction for Kalimantan study area (Peak Fire Season Sample: 2023-09-01)...")
    results = []
    
    for loc in LOCATIONS:
        # Open-Meteo Archive API serves open ECMWF ERA5 / ERA5-Land reanalysis data
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": loc["lat"],
            "longitude": loc["lon"],
            "start_date": "2023-09-01",
            "end_date": "2023-09-01",
            "hourly": "temperature_2m,dew_point_2m,relative_humidity_2m,precipitation,surface_pressure,wind_speed_10m,wind_direction_10m,soil_moisture_0_to_7cm",
            "timezone": "UTC"
        }
        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    break
            except Exception:
                if attempt == 2:
                    raise
        try:
            if resp.status_code == 200:
                data = resp.json()
                hourly = data.get("hourly", {})
                # Get daily mean/aggregate
                temps = hourly.get("temperature_2m", [])
                dew_points = hourly.get("dew_point_2m", [])
                rhs = hourly.get("relative_humidity_2m", [])
                precips = hourly.get("precipitation", [])
                wind_speeds = hourly.get("wind_speed_10m", [])
                soil_m = hourly.get("soil_moisture_0_to_7cm", [])
                
                results.append({
                    "province": loc["province"],
                    "city": loc["city"],
                    "lat": loc["lat"],
                    "lon": loc["lon"],
                    "date": "2023-09-01",
                    "t2m_mean_c": round(sum(temps)/len(temps), 2) if temps else None,
                    "t2m_max_c": max(temps) if temps else None,
                    "dewpoint_mean_c": round(sum(dew_points)/len(dew_points), 2) if dew_points else None,
                    "relative_humidity_mean_pct": round(sum(rhs)/len(rhs), 1) if rhs else None,
                    "total_precip_mm": round(sum(precips), 2) if precips else None,
                    "wind_speed_10m_mean_kmh": round(sum(wind_speeds)/len(wind_speeds), 2) if wind_speeds else None,
                    "soil_moisture_0_7cm_m3m3": round(sum(soil_m)/len(soil_m), 3) if soil_m else None,
                    "status": "SUCCESS"
                })
                print(f"  [OK] {loc['province']} ({loc['city']}): T2M={results[-1]['t2m_mean_c']}C, RH={results[-1]['relative_humidity_mean_pct']}%, SoilMoist={results[-1]['soil_moisture_0_7cm_m3m3']} m3/m3")
            else:
                print(f"  [FAIL] {loc['province']}: HTTP {resp.status_code}")
                results.append({"province": loc["province"], "status": f"HTTP {resp.status_code}"})
        except Exception as e:
            print(f"  [ERROR] {loc['province']}: {e}")
            results.append({"province": loc["province"], "status": str(e)})

    # Save to validation output
    out_file = Path("outputs/validation/kalimantan_era5land_sample.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved sample extraction results to {out_file}")

    # Save to standard data directory as JSON and CSV
    data_json = Path("data/gee/processed/kalimantan_era5land_sample.json")
    data_json.parent.mkdir(parents=True, exist_ok=True)
    with open(data_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    df = pd.DataFrame(results)
    data_csv = Path("data/gee/processed/kalimantan_era5land_sample.csv")
    df.to_csv(data_csv, index=False)
    print(f"Saved sample extraction results to {data_json} and {data_csv}")
    return results

if __name__ == "__main__":
    test_era5_land_extraction()
