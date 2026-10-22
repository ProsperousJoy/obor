"""
scripts/explore_bmkg.py
=======================
Exploratory Data Acquisition and Validation Script for BMKG Weather Data.
Covers:
  1. Automated retrieval of real BMKG Open Data (JSON API) across 5 Kalimantan provinces
  2. Raw data archival in data/bmkg/raw/
  3. Schema & variable identification (Temperature, Humidity, Rain, Wind, Clouds, Weather)
  4. Data quality & physical reasonableness inspection
  5. Spatial coordinate validation & Kalimantan coverage mapping
  6. Temporal resolution & timezone validation (UTC vs WIB/WITA)
  7. Export processed tabular dataset to data/bmkg/processed/
  8. Visualizations saved to outputs/validation/

Usage:
    python scripts/explore_bmkg.py
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ─────────────────────────────────────────────────────────────
# DIRECTORIES & CONFIGURATION
# ─────────────────────────────────────────────────────────────
RAW_DIR = Path("data/bmkg/raw")
PROCESSED_DIR = Path("data/bmkg/processed")
VALIDATION_DIR = Path("outputs/validation")
COASTLINE_GEOJSON = "outputs/validation/ne_110m_coastline.geojson"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

BORNEO_BBOX = {
    "lon_min": 108.0,
    "lon_max": 119.0,
    "lat_min": -5.0,
    "lat_max": 7.0,
}

KALIMANTAN_CITIES = [
    ("Pontianak",    0.021,  109.332),
    ("Palangkaraya", -2.208, 113.913),
    ("Banjarmasin",  -3.318, 114.593),
    ("Samarinda",    -0.502, 117.153),
    ("Balikpapan",   -1.267, 116.829),
]

# Representative sampling of adm4 administrative codes across 5 Kalimantan provinces
KALIMANTAN_SAMPLE_LOCATIONS = [
    # Kalimantan Barat (61)
    {"prov": "Kalbar",  "adm4": "61.01.01.2001", "name": "Sambas (Dalam Kaum)",      "kab": "Sambas"},
    {"prov": "Kalbar",  "adm4": "61.04.01.2001", "name": "Kendawangan (Pangkalan Batu)", "kab": "Ketapang"},
    {"prov": "Kalbar",  "adm4": "61.05.01.2001", "name": "Sintang (Mekar Jaya)",    "kab": "Sintang"},
    # Kalimantan Tengah (62)
    {"prov": "Kalteng", "adm4": "62.01.01.1011", "name": "Kumai (Candi)",           "kab": "Kotawaringin Barat"},
    {"prov": "Kalteng", "adm4": "62.02.01.2001", "name": "Sampit / Mentawa Baru",    "kab": "Kotawaringin Timur"},
    {"prov": "Kalteng", "adm4": "62.03.01.2001", "name": "Kuala Kapuas",            "kab": "Kapuas"},
    # Kalimantan Selatan (63)
    {"prov": "Kalsel",  "adm4": "63.01.01.2001", "name": "Takisung (Benua Lawas)",   "kab": "Tanah Laut"},
    {"prov": "Kalsel",  "adm4": "63.02.01.2001", "name": "Pulau Laut / Kotabaru",    "kab": "Kotabaru"},
    {"prov": "Kalsel",  "adm4": "63.04.01.2001", "name": "Barito Kuala (Alalak)",    "kab": "Barito Kuala"},
    # Kalimantan Timur (64)
    {"prov": "Kaltim",  "adm4": "64.01.01.2009", "name": "Batu Sopang (Samurangau)", "kab": "Paser"},
    {"prov": "Kaltim",  "adm4": "64.02.01.2001", "name": "Kutai Barat (Barong Tongkok)", "kab": "Kutai Barat"},
    {"prov": "Kaltim",  "adm4": "64.03.01.2001", "name": "Kutai Kartanegara (Tenggarong)", "kab": "Kutai Kartanegara"},
    # Kalimantan Utara (65)
    {"prov": "Kaltara", "adm4": "65.01.01.1001", "name": "Tanjung Palas Hulu",      "kab": "Bulungan"},
    {"prov": "Kaltara", "adm4": "65.02.01.2001", "name": "Malinau Kota",            "kab": "Malinau"},
    {"prov": "Kaltara", "adm4": "65.03.01.2001", "name": "Nunukan Barat",           "kab": "Nunukan"},
]

BMKG_VARIABLE_SPECS = {
    "t":            ("Temperature", "Suhu Udara", "degC", "Celsius", True, "Essential fire weather metric"),
    "hu":           ("Relative Humidity", "Kelembapan Udara Relatif", "%", "Percent", True, "Essential fuel dryness proxy"),
    "tp":           ("Precipitation", "Curah Hujan / Presipitasi", "mm", "Millimeter", True, "Essential fire suppression indicator"),
    "ws":           ("Wind Speed", "Kecepatan Angin", "km/h", "Kilometer per jam", True, "Fire spread acceleration driver"),
    "wd_deg":       ("Wind Direction", "Arah Angin (Derajat)", "deg", "0-360 Degrees", True, "Fire propagation vector"),
    "wd":           ("Wind Direction (Cardinal)", "Arah Angin Mata Angin", "cardinal", "Text (SE, NW, etc.)", True, "Compass direction"),
    "tcc":          ("Total Cloud Cover", "Tutupan Awan Total", "%", "Percent", True, "Solar insulation & satellite visibility"),
    "weather":      ("Weather Code", "Kode Cuaca BMKG", "code", "Integer code (1=Cerah, 10=Haze, 61=Hujan, etc.)", True, "Atmospheric condition"),
    "weather_desc": ("Weather Description (ID)", "Deskripsi Cuaca (ID)", "text", "Bahasa Indonesia", True, "Human readable weather status"),
    "weather_desc_en": ("Weather Description (EN)", "Deskripsi Cuaca (EN)", "text", "English text", True, "Human readable weather status"),
    "vs":           ("Visibility", "Jarak Pandang Mendatar", "km", "Kilometer", False, "Often null in public forecast feeds"),
    "pressure":     ("Atmospheric Pressure", "Tekanan Udara Permukaan", "hPa", "Hektopascal", False, "Not in public village forecast feed"),
    "solar_rad":    ("Solar Radiation", "Radiasi Matahari Global", "W/m2", "Watt per m2", False, "Not in public village forecast feed"),
}


def fetch_raw_bmkg_data(locations: list) -> list:
    """Download real JSON data from BMKG Open Data API for the given locations."""
    print("\n" + "=" * 70)
    print("STEP 1 & 3: FETCHING REAL BMKG OPEN DATA SAMPLES")
    print("=" * 70)
    
    fetched_data = []
    
    for loc in locations:
        adm4 = loc["adm4"]
        name = loc["name"]
        prov = loc["prov"]
        
        url = f"https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={adm4}"
        raw_filename = RAW_DIR / f"bmkg_prakiraan_{adm4}.json"
        
        print(f"Fetching {prov} - {name} ({adm4}) ...")
        cmd = ["curl.exe", "-s", "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", url]
        res = subprocess.run(cmd, capture_output=True, text=True)
        
        try:
            data = json.loads(res.stdout)
            if "lokasi" in data and "data" in data:
                # Save raw JSON
                with open(raw_filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                lok = data["lokasi"]
                print(f"  [OK] Saved to {raw_filename.name} | Lat: {lok.get('lat')}, Lon: {lok.get('lon')} | TZ: {lok.get('timezone')}")
                fetched_data.append({"meta": loc, "raw_file": str(raw_filename), "payload": data})
            else:
                print(f"  [FAIL] Error payload for {adm4}: {data.get('message', 'Unknown response')}")
        except Exception as e:
            print(f"  [ERR] Failed parsing response for {adm4}: {e}")
            
    print(f"\nSuccessfully downloaded and verified {len(fetched_data)} of {len(locations)} location feeds.")
    return fetched_data


def parse_and_tabulate_bmkg(fetched_records: list) -> pd.DataFrame:
    """Parse nested BMKG JSON data into a clean, flat pandas DataFrame."""
    print("\n" + "=" * 70)
    print("STEP 4: PARSING & TABULATING BMKG DATA")
    print("=" * 70)
    
    flat_rows = []
    
    for item in fetched_records:
        meta = item["meta"]
        payload = item["payload"]
        
        lok = payload.get("lokasi", {})
        data_blocks = payload.get("data", [])
        
        lat = float(lok.get("lat")) if lok.get("lat") is not None else None
        lon = float(lok.get("lon")) if lok.get("lon") is not None else None
        prov = lok.get("provinsi", meta["prov"])
        kotkab = lok.get("kotkab", meta.get("kab", ""))
        kec = lok.get("kecamatan", "")
        desa = lok.get("desa", meta["name"])
        tz = lok.get("timezone", "")
        
        for blk in data_blocks:
            cuaca_days = blk.get("cuaca", [])
            for day_slots in cuaca_days:
                for slot in day_slots:
                    row = {
                        "provinsi": prov,
                        "kabupaten_kota": kotkab,
                        "kecamatan": kec,
                        "desa_kelurahan": desa,
                        "adm4": meta["adm4"],
                        "latitude": lat,
                        "longitude": lon,
                        "timezone": tz,
                        "raw_datetime": slot.get("datetime"),
                        "raw_utc_datetime": slot.get("utc_datetime"),
                        "raw_local_datetime": slot.get("local_datetime"),
                        "analysis_date": slot.get("analysis_date"),
                        # Meteorological Variables
                        "temperature_c": slot.get("t"),
                        "humidity_pct": slot.get("hu"),
                        "precipitation_mm": slot.get("tp"),
                        "cloud_cover_pct": slot.get("tcc"),
                        "wind_speed_kmh": slot.get("ws"),
                        "wind_dir_deg": slot.get("wd_deg"),
                        "wind_dir_cardinal": slot.get("wd"),
                        "weather_code": slot.get("weather"),
                        "weather_desc_id": slot.get("weather_desc"),
                        "weather_desc_en": slot.get("weather_desc_en"),
                        "visibility_km": slot.get("vs"),
                    }
                    flat_rows.append(row)
                    
    df = pd.DataFrame(flat_rows)
    
    # Generate canonical datetime_utc
    df["datetime_utc"] = pd.to_datetime(df["raw_datetime"], utc=True)
    
    # Save processed CSV
    out_csv = PROCESSED_DIR / "bmkg_kalimantan_weather_sample.csv"
    df.to_csv(out_csv, index=False)
    print(f"Tabulated {len(df):,} records from {df['adm4'].nunique()} locations across Kalimantan.")
    print(f"Saved processed dataset to: {out_csv}")
    
    return df


def inspect_bmkg_data_quality(df: pd.DataFrame) -> dict:
    """Analyze missing values, duplicates, physical ranges, and variable schema."""
    print("\n" + "=" * 70)
    print("STEP 2, 6, & 7: SCHEMA, TEMPORAL & DATA QUALITY ASSESSMENT")
    print("=" * 70)
    
    summary = {}
    
    # 1. Variable Table Summary
    print("\n--- Available BMKG Variables Table ---")
    print(f"{'Variable':<22} | {'Field':<18} | {'Unit':<8} | {'Found?':<6} | {'Description'}")
    print("-" * 80)
    
    field_to_col = {
        "t": "temperature_c",
        "hu": "humidity_pct",
        "tp": "precipitation_mm",
        "ws": "wind_speed_kmh",
        "wd_deg": "wind_dir_deg",
        "wd": "wind_dir_cardinal",
        "tcc": "cloud_cover_pct",
        "weather": "weather_code",
        "weather_desc": "weather_desc_id",
        "weather_desc_en": "weather_desc_en",
        "vs": "visibility_km",
    }
    
    var_table = []
    for field, (var_en, var_id, unit, unit_desc, avail, desc) in BMKG_VARIABLE_SPECS.items():
        mapped_col = field_to_col.get(field, field)
        found = "Yes" if mapped_col in df.columns else "No"
        print(f"{var_en:<22} | {field:<18} | {unit:<8} | {found:<6} | {desc}")
        var_table.append({
            "variable": var_en,
            "original_field": field,
            "dataframe_column": mapped_col if found == "Yes" else None,
            "unit": unit,
            "unit_desc": unit_desc,
            "available": found,
            "description": desc
        })
    summary["variable_table"] = var_table
    
    # 2. Quality Counts
    summary["total_records"] = len(df)
    summary["total_locations"] = int(df["adm4"].nunique())
    summary["duplicate_records"] = int(df.duplicated(subset=["adm4", "datetime_utc"]).sum())
    summary["missing_values"] = df.isnull().sum().to_dict()
    
    print(f"\n--- Quality Metrics ---")
    print(f"  Total records    : {summary['total_records']:,}")
    print(f"  Total locations  : {summary['total_locations']}")
    print(f"  Duplicates       : {summary['duplicate_records']}")
    print(f"  Missing values by column:")
    for col, n_miss in summary["missing_values"].items():
        if n_miss > 0:
            print(f"    - {col}: {n_miss} missing ({100*n_miss/len(df):.1f}%)")
            
    # 3. Numeric Physical Range Check
    print("\n--- Physical Range Inspection ---")
    num_metrics = ["temperature_c", "humidity_pct", "precipitation_mm", "cloud_cover_pct", "wind_speed_kmh", "wind_dir_deg"]
    phys_summary = {}
    for col in num_metrics:
        s = df[col].dropna()
        phys_summary[col] = {
            "min": float(s.min()),
            "max": float(s.max()),
            "mean": float(s.mean()),
            "median": float(s.median()),
            "std": float(s.std())
        }
        print(f"  {col:<20}: min={s.min():.2f}, max={s.max():.2f}, mean={s.mean():.2f}, median={s.median():.2f}")
    summary["physical_ranges"] = phys_summary
    
    # 4. Temporal Characteristics
    summary["temporal"] = {
        "start_utc": str(df["datetime_utc"].min()),
        "end_utc": str(df["datetime_utc"].max()),
        "time_step_hours": 3,
        "total_timesteps_per_loc": int(len(df) / df["adm4"].nunique()),
        "timezones_found": df["timezone"].unique().tolist(),
    }
    print("\n--- Temporal Characteristics ---")
    print(f"  Temporal span (UTC)     : {summary['temporal']['start_utc']} to {summary['temporal']['end_utc']}")
    print(f"  Cadence / Interval       : Per {summary['temporal']['time_step_hours']} jam")
    print(f"  Timesteps per location   : {summary['temporal']['total_timesteps_per_loc']} steps (3 days forecast)")
    print(f"  Timezones in Kalimantan  : {summary['temporal']['timezones_found']} (Asia/Pontianak = UTC+7, Asia/Makassar = UTC+8)")
    
    return summary


def validate_kalimantan_coverage(df: pd.DataFrame) -> dict:
    """Validate spatial coordinates and Kalimantan geographic distribution."""
    print("\n" + "=" * 70)
    print("STEP 5 & 8: SPATIAL VALIDATION & KALIMANTAN COVERAGE")
    print("=" * 70)
    
    spatial = {}
    
    # Unique locations
    locs = df[["adm4", "provinsi", "kabupaten_kota", "desa_kelurahan", "latitude", "longitude", "timezone"]].drop_duplicates()
    
    spatial["total_sampled_stations"] = len(locs)
    spatial["lat_min"] = float(locs["latitude"].min())
    spatial["lat_max"] = float(locs["latitude"].max())
    spatial["lon_min"] = float(locs["longitude"].min())
    spatial["lon_max"] = float(locs["longitude"].max())
    
    print(f"  Locations evaluated: {len(locs)}")
    print(f"  Latitude range     : [{spatial['lat_min']:.4f}, {spatial['lat_max']:.4f}] deg")
    print(f"  Longitude range    : [{spatial['lon_min']:.4f}, {spatial['lon_max']:.4f}] deg")
    
    inside_bbox = (
        (locs["longitude"] >= BORNEO_BBOX["lon_min"]) &
        (locs["longitude"] <= BORNEO_BBOX["lon_max"]) &
        (locs["latitude"] >= BORNEO_BBOX["lat_min"]) &
        (locs["latitude"] <= BORNEO_BBOX["lat_max"])
    ).all()
    spatial["all_inside_borneo_bbox"] = bool(inside_bbox)
    print(f"  Strictly within Kalimantan Study Bbox: {'PASS' if inside_bbox else 'FAIL'}")
    
    prov_dist = locs["provinsi"].value_counts().to_dict()
    spatial["provincial_distribution"] = prov_dist
    print("\n  Provincial Breakdown:")
    for prov, count in prov_dist.items():
        print(f"    - {prov}: {count} locations")
        
    print("\n  Sample Station Coordinates:")
    for _, r in locs.iterrows():
        print(f"    [{r['provinsi'][:7]}] {r['kabupaten_kota']} ({r['desa_kelurahan']}): Lat {r['latitude']:.4f}, Lon {r['longitude']:.4f} ({r['timezone']})")
        
    return spatial


def generate_bmkg_visualizations(df: pd.DataFrame):
    """Generate map and distribution plots for BMKG data."""
    print("\n" + "=" * 70)
    print("GENERATING BMKG VALIDATION VISUALIZATIONS")
    print("=" * 70)
    
    # Load coastlines
    coastlines = []
    if os.path.exists(COASTLINE_GEOJSON):
        with open(COASTLINE_GEOJSON) as f:
            gj = json.load(f)
        for feat in gj.get("features", []):
            geom = feat.get("geometry", {})
            if geom.get("type") == "LineString":
                coastlines.append(np.array(geom["coordinates"]))
            elif geom.get("type") == "MultiLineString":
                for line in geom["coordinates"]:
                    coastlines.append(np.array(line))
                    
    def draw_coastlines(ax):
        for line in coastlines:
            mask = (
                (line[:, 0] >= BORNEO_BBOX["lon_min"] - 1) &
                (line[:, 0] <= BORNEO_BBOX["lon_max"] + 1) &
                (line[:, 1] >= BORNEO_BBOX["lat_min"] - 1) &
                (line[:, 1] <= BORNEO_BBOX["lat_max"] + 1)
            )
            if mask.any():
                ax.plot(line[:, 0], line[:, 1], color="white", linewidth=0.75, alpha=0.9)

    # ── PLOT 1: Kalimantan Coverage Map ──────────────────────
    fig1, ax1 = plt.subplots(figsize=(11, 9), facecolor="#1e1e1e")
    ax1.set_facecolor("#121212")
    draw_coastlines(ax1)
    
    locs = df[["adm4", "provinsi", "kabupaten_kota", "desa_kelurahan", "latitude", "longitude"]].drop_duplicates()
    
    # Plot BMKG observation points
    scatter = ax1.scatter(
        locs["longitude"], locs["latitude"],
        c="gold", s=80, marker="o", edgecolors="black", linewidths=1.2, zorder=6,
        label=f"BMKG Sampled Locations (N={len(locs)})"
    )
    
    # Label each BMKG station
    for _, r in locs.iterrows():
        ax1.annotate(
            r["kabupaten_kota"], (r["longitude"], r["latitude"] - 0.20),
            color="yellow", fontsize=7.5, ha="center",
            bbox=dict(boxstyle="round,pad=0.15", fc="#222", alpha=0.7)
        )
        
    # Plot reference cities
    for city, clat, clon in KALIMANTAN_CITIES:
        ax1.scatter(clon, clat, s=60, color="deepskyblue", edgecolors="white", linewidths=0.8, zorder=7)
        ax1.annotate(city, (clon, clat + 0.18), color="white", fontsize=8, fontweight="bold",
                     ha="center", bbox=dict(boxstyle="round,pad=0.15", fc="black", alpha=0.6))
        
    # Bbox outline
    bbox_rect = mpatches.Rectangle(
        (BORNEO_BBOX["lon_min"], BORNEO_BBOX["lat_min"]),
        BORNEO_BBOX["lon_max"] - BORNEO_BBOX["lon_min"],
        BORNEO_BBOX["lat_max"] - BORNEO_BBOX["lat_min"],
        linewidth=1.5, edgecolor="cyan", facecolor="none", linestyle="--",
        label="Kalimantan Study Bbox"
    )
    ax1.add_patch(bbox_rect)
    
    ax1.set_xlim(BORNEO_BBOX["lon_min"] - 0.5, BORNEO_BBOX["lon_max"] + 0.5)
    ax1.set_ylim(BORNEO_BBOX["lat_min"] - 0.5, BORNEO_BBOX["lat_max"] + 0.5)
    ax1.grid(True, color="#333333", linestyle=":", linewidth=0.6)
    ax1.tick_params(colors="white")
    ax1.set_xlabel("Longitude (deg E)", color="white", fontsize=10)
    ax1.set_ylabel("Latitude (deg)", color="white", fontsize=10)
    ax1.set_title(
        "BMKG Weather Observation Network — Kalimantan Coverage Exploration\n"
        "5 Provinces Sampled (Kalbar, Kalteng, Kalsel, Kaltim, Kaltara)",
        color="white", fontsize=11
    )
    ax1.legend(loc="lower right", facecolor="#222222", edgecolor="gray", labelcolor="white", fontsize=8)
    
    out_map = VALIDATION_DIR / "bmkg_kalimantan_coverage.png"
    fig1.savefig(out_map, dpi=150, bbox_inches="tight")
    plt.close(fig1)
    print(f"  Saved Plot 1 (Coverage Map): {out_map}")

    # ── PLOT 2: Weather Variable Distributions ────────────────
    fig2, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor="#1e1e1e")
    for ax in axes.flat:
        ax.set_facecolor("#121212")
        ax.tick_params(colors="white")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.title.set_color("white")
        for s in ax.spines.values():
            s.set_color("gray")
            
    # Subplot A: Temperature
    t_clean = df["temperature_c"].dropna()
    axes[0, 0].hist(t_clean, bins=25, color="tomato", alpha=0.85, edgecolor="black")
    axes[0, 0].axvline(t_clean.median(), color="yellow", linestyle="--", label=f"Median: {t_clean.median():.1f} C")
    axes[0, 0].set_title("Temperature Distribution [Celsius]", fontsize=10)
    axes[0, 0].set_xlabel("Celsius")
    axes[0, 0].set_ylabel("Forecast Steps")
    axes[0, 0].legend(facecolor="#222", labelcolor="white", fontsize=8)
    
    # Subplot B: Relative Humidity
    hu_clean = df["humidity_pct"].dropna()
    axes[0, 1].hist(hu_clean, bins=25, color="deepskyblue", alpha=0.85, edgecolor="black")
    axes[0, 1].axvline(hu_clean.median(), color="yellow", linestyle="--", label=f"Median: {hu_clean.median():.1f} %")
    axes[0, 1].set_title("Relative Humidity Distribution [%]", fontsize=10)
    axes[0, 1].set_xlabel("Percent")
    axes[0, 1].set_ylabel("Forecast Steps")
    axes[0, 1].legend(facecolor="#222", labelcolor="white", fontsize=8)
    
    # Subplot C: Precipitation (Rainfall)
    tp_clean = df["precipitation_mm"].dropna()
    axes[1, 0].hist(tp_clean, bins=25, color="mediumseagreen", alpha=0.85, edgecolor="black")
    axes[1, 0].axvline(tp_clean.median(), color="yellow", linestyle="--", label=f"Median: {tp_clean.median():.1f} mm")
    axes[1, 0].set_title("Precipitation Distribution [mm / 3h]", fontsize=10)
    axes[1, 0].set_xlabel("Millimeters")
    axes[1, 0].set_ylabel("Forecast Steps")
    axes[1, 0].legend(facecolor="#222", labelcolor="white", fontsize=8)
    
    # Subplot D: Wind Speed
    ws_clean = df["wind_speed_kmh"].dropna()
    axes[1, 1].hist(ws_clean, bins=25, color="orchid", alpha=0.85, edgecolor="black")
    axes[1, 1].axvline(ws_clean.median(), color="yellow", linestyle="--", label=f"Median: {ws_clean.median():.1f} km/h")
    axes[1, 1].set_title("Wind Speed Distribution [km/h]", fontsize=10)
    axes[1, 1].set_xlabel("km/h")
    axes[1, 1].set_ylabel("Forecast Steps")
    axes[1, 1].legend(facecolor="#222", labelcolor="white", fontsize=8)
    
    fig2.suptitle("BMKG Weather Variables — Statistical Distributions (Kalimantan)", color="white", fontsize=12)
    out_dist = VALIDATION_DIR / "bmkg_weather_distributions.png"
    fig2.savefig(out_dist, dpi=150, bbox_inches="tight")
    plt.close(fig2)
    print(f"  Saved Plot 2 (Distributions): {out_dist}")


def main():
    parser = argparse.ArgumentParser(description="BMKG Exploratory Data Acquisition & Validation")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetching, use local raw JSONs")
    args = parser.parse_args()
    
    print("=" * 70)
    print("BMKG DATA EXPLORATION SUITE (KALIMANTAN WILDFIRE RISK)")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    if args.skip_fetch:
        raw_files = list(RAW_DIR.glob("bmkg_prakiraan_*.json"))
        fetched_records = []
        for rf in raw_files:
            with open(rf, "r", encoding="utf-8") as f:
                data = json.load(f)
                adm4 = rf.stem.replace("bmkg_prakiraan_", "")
                fetched_records.append({
                    "meta": {"adm4": adm4, "prov": "", "name": adm4},
                    "raw_file": str(rf),
                    "payload": data
                })
    else:
        fetched_records = fetch_raw_bmkg_data(KALIMANTAN_SAMPLE_LOCATIONS)
        
    if not fetched_records:
        print("ERROR: No BMKG data available to process.")
        sys.exit(1)
        
    df = parse_and_tabulate_bmkg(fetched_records)
    quality_summary = inspect_bmkg_data_quality(df)
    spatial_summary = validate_kalimantan_coverage(df)
    generate_bmkg_visualizations(df)
    
    # Save overall summary JSON
    overall_summary = {
        "timestamp_explored": datetime.now().isoformat(),
        "source": "BMKG Data Terbuka / api.bmkg.go.id",
        "total_records": len(df),
        "total_locations": int(df["adm4"].nunique()),
        "quality": quality_summary,
        "spatial": spatial_summary,
    }
    summary_json_path = VALIDATION_DIR / "bmkg_validation_summary.json"
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(overall_summary, f, indent=2, default=str)
    print(f"\nSaved exploration summary JSON: {summary_json_path}")
    print("\nBMKG Data Exploration Complete!")


if __name__ == "__main__":
    main()
