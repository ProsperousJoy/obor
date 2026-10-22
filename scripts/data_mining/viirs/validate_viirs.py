"""
scripts/validate_viirs.py
=========================
Comprehensive validation script for NASA FIRMS VIIRS Active Fire Data.
Covers:
  1. Data loading & schema inspection (13 standard FIRMS fields)
  2. Data quality checks (missing, duplicates, physical range bounds)
  3. Geolocation validation (Kalimantan bbox, coordinate validity, sanity check cities)
  4. Timestamp validation & canonical UTC conversion
  5. Fire detection semantics (I-4 vs I-5, FRP, confidence levels, day/night)
  6. Prototype spatiotemporal join with Himawari-9 B07 NetCDF
  7. Export processed sample to data/viirs/processed/
  8. Visualizations saved to outputs/validation/

Usage:
    python scripts/validate_viirs.py
    python scripts/validate_viirs.py --input data/viirs/raw/J1_VIIRS_C2_SouthEast_Asia_24h.csv
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy.spatial import cKDTree
import xarray as xr

# ─────────────────────────────────────────────────────────────
# CONFIGURATION & CONSTANTS
# ─────────────────────────────────────────────────────────────
DEFAULT_RAW_FILE = "data/viirs/raw/J1_VIIRS_C2_SouthEast_Asia_24h.csv"
HIMAWARI_NC_FILE = "outputs/himawari_b07_s0510_borneo.nc"
COASTLINE_GEOJSON = "outputs/validation/ne_110m_coastline.geojson"

PROCESSED_DIR = Path("data/viirs/processed")
VALIDATION_DIR = Path("outputs/validation")
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

EXPECTED_SCHEMA = {
    "latitude":   ("float64", "Latitude of fire pixel centroid", "degree", "Essential"),
    "longitude":  ("float64", "Longitude of fire pixel centroid", "degree", "Essential"),
    "bright_ti4": ("float64", "VIIRS I-4 thermal brightness temp (3.75-4.05 um)", "Kelvin", "Essential"),
    "scan":       ("float64", "Along-scan pixel dimension", "km", "Quality"),
    "track":      ("float64", "Along-track pixel dimension", "km", "Quality"),
    "acq_date":   ("string",  "Acquisition date (YYYY-MM-DD)", "date", "Essential"),
    "acq_time":   ("string",  "Acquisition time in UTC (HHMM)", "time", "Essential"),
    "satellite":  ("string",  "Satellite platform (N20=NOAA-20, N=Suomi-NPP, N21=NOAA-21)", "category", "Provenance"),
    "confidence": ("string",  "Detection confidence level (low, nominal, high)", "category", "Quality"),
    "version":    ("string",  "Collection and data processing source version", "string", "Provenance"),
    "bright_ti5": ("float64", "VIIRS I-5 thermal brightness temp (10.5-12.4 um)", "Kelvin", "Contextual"),
    "frp":        ("float64", "Fire Radiative Power", "MW", "High"),
    "daynight":   ("string",  "Solar illumination flag (D=Day, N=Night)", "flag", "High"),
}


def load_raw_viirs(filepath: str) -> pd.DataFrame:
    """Load raw VIIRS CSV data handling missing or partial lines gracefully."""
    print(f"Loading raw VIIRS CSV: {filepath}")
    df = pd.read_csv(filepath, on_bad_lines="skip")
    print(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")
    return df


def validate_schema(df: pd.DataFrame) -> dict:
    """Validate presence and types of expected columns."""
    print("\n" + "=" * 60)
    print("STEP 2: SCHEMA VALIDATION")
    print("=" * 60)
    
    schema_results = {}
    missing_cols = []
    
    for col, (exp_type, meaning, unit, imp) in EXPECTED_SCHEMA.items():
        present = col in df.columns
        dtype = str(df[col].dtype) if present else "MISSING"
        schema_results[col] = {
            "present": present,
            "dtype": dtype,
            "expected_type": exp_type,
            "meaning": meaning,
            "unit": unit,
            "importance": imp
        }
        status = "OK" if present else "MISSING"
        print(f"  {col:<12} | {status:<7} | type: {dtype:<10} | unit: {unit:<8} | {meaning}")
        if not present:
            missing_cols.append(col)
            
    is_valid = len(missing_cols) == 0
    print(f"\nSchema Valid: {'PASS' if is_valid else 'FAIL (missing ' + str(missing_cols) + ')'}")
    return schema_results


def inspect_data_quality(df: pd.DataFrame) -> dict:
    """Check missing values, duplicates, and physical range sanity."""
    print("\n" + "=" * 60)
    print("STEP 4: DATA QUALITY & STATISTICAL INSPECTION")
    print("=" * 60)
    
    quality = {}
    quality["total_rows"] = len(df)
    quality["duplicate_rows"] = int(df.duplicated().sum())
    quality["missing_values"] = df.isnull().sum().to_dict()
    
    print(f"  Total records: {quality['total_rows']:,}")
    print(f"  Duplicates   : {quality['duplicate_rows']}")
    print(f"  Missing values by field:")
    for col, n_miss in quality["missing_values"].items():
        if n_miss > 0:
            print(f"    - {col}: {n_miss} ({100*n_miss/len(df):.2f}%)")
    if all(v == 0 for v in quality["missing_values"].values()):
        print("    None (0 missing values across all columns)")
        
    # Numeric summary
    num_cols = ["bright_ti4", "bright_ti5", "frp", "scan", "track", "latitude", "longitude"]
    num_summary = {}
    print("\n  Physical Range Inspection:")
    for col in num_cols:
        if col in df.columns:
            s = df[col].dropna()
            num_summary[col] = {
                "min": float(s.min()),
                "max": float(s.max()),
                "mean": float(s.mean()),
                "median": float(s.median()),
                "std": float(s.std()),
                "p01": float(np.percentile(s, 1)),
                "p99": float(np.percentile(s, 99)),
            }
            print(f"    {col:<12}: min={s.min():.2f}, max={s.max():.2f}, mean={s.mean():.2f}, median={s.median():.2f}")
    quality["numeric_summary"] = num_summary
    
    # Categorical distributions
    cat_summary = {}
    for col in ["confidence", "daynight", "satellite"]:
        if col in df.columns:
            vc = df[col].value_counts().to_dict()
            cat_summary[col] = vc
            print(f"\n  Distribution of {col}:")
            for k, count in vc.items():
                print(f"    - {k}: {count:,} ({100*count/len(df):.1f}%)")
    quality["categorical_summary"] = cat_summary
    
    # Range bound checks
    valid_coords = (
        (df["latitude"] >= -90) & (df["latitude"] <= 90) &
        (df["longitude"] >= -180) & (df["longitude"] <= 180)
    ).all()
    quality["valid_coordinates_range"] = bool(valid_coords)
    print(f"\n  Coordinates strictly inside [-90..90] lat, [-180..180] lon: {'PASS' if valid_coords else 'FAIL'}")
    
    return quality


def subset_and_process_kalimantan(df: pd.DataFrame) -> pd.DataFrame:
    """Subset to Kalimantan bounding box and format canonical UTC timestamp."""
    print("\n" + "=" * 60)
    print("STEP 5 & 6: KALIMANTAN SUBSETTING & TIMESTAMP VALIDATION")
    print("=" * 60)
    
    # Spatial filter
    mask = (
        (df["longitude"] >= BORNEO_BBOX["lon_min"]) &
        (df["longitude"] <= BORNEO_BBOX["lon_max"]) &
        (df["latitude"] >= BORNEO_BBOX["lat_min"]) &
        (df["latitude"] <= BORNEO_BBOX["lat_max"])
    )
    df_borneo = df[mask].copy()
    print(f"  Kalimantan bbox filter : Lon [{BORNEO_BBOX['lon_min']}, {BORNEO_BBOX['lon_max']}], "
          f"Lat [{BORNEO_BBOX['lat_min']}, {BORNEO_BBOX['lat_max']}]")
    print(f"  Detections in Kalimantan: {len(df_borneo):,} / {len(df):,} ({100*len(df_borneo)/len(df):.1f}%)")
    
    # Canonical timestamp creation
    # acq_time in FIRMS is HHMM (often float or int or zero-padded string)
    def parse_time_str(val):
        s = str(int(float(val))) if pd.notnull(val) else "0000"
        return s.zfill(4)
    
    df_borneo["raw_acq_date"] = df_borneo["acq_date"].astype(str)
    df_borneo["raw_acq_time"] = df_borneo["acq_time"].apply(parse_time_str)
    
    time_strings = df_borneo["raw_acq_date"] + " " + df_borneo["raw_acq_time"]
    df_borneo["datetime_utc"] = pd.to_datetime(time_strings, format="%Y-%m-%d %H%M", utc=True)
    
    print(f"\n  Timestamp Validation:")
    print(f"    Date range (UTC)    : {df_borneo['datetime_utc'].min()} to {df_borneo['datetime_utc'].max()}")
    print(f"    Raw dates present   : {df_borneo['raw_acq_date'].unique().tolist()}")
    print(f"    Overpass times (UTC): {sorted(df_borneo['raw_acq_time'].unique().tolist())}")
    
    # Save processed sample
    out_csv = PROCESSED_DIR / "viirs_noaa20_kalimantan_sample.csv"
    df_borneo.to_csv(out_csv, index=False)
    print(f"\n  Saved processed Kalimantan sample: {out_csv} ({len(df_borneo):,} rows)")
    
    return df_borneo


def validate_fire_semantics(df_borneo: pd.DataFrame) -> dict:
    """Analyze fire detection semantics: I-4 vs I-5 difference, FRP, confidence, day/night."""
    print("\n" + "=" * 60)
    print("STEP 7: FIRE DETECTION SEMANTICS ANALYSIS")
    print("=" * 60)
    
    semantics = {}
    
    # Difference dBT = bright_ti4 - bright_ti5
    dBT = df_borneo["bright_ti4"] - df_borneo["bright_ti5"]
    df_borneo["dBT_i4_i5"] = dBT
    
    semantics["dBT_mean"] = float(dBT.mean())
    semantics["dBT_min"] = float(dBT.min())
    semantics["dBT_max"] = float(dBT.max())
    semantics["dBT_median"] = float(dBT.median())
    
    print("  Brightness Temperature Difference (I-4 minus I-5):")
    print(f"    dBT Mean   : {semantics['dBT_mean']:.2f} K")
    print(f"    dBT Median : {semantics['dBT_median']:.2f} K")
    print(f"    dBT Min    : {semantics['dBT_min']:.2f} K")
    print(f"    dBT Max    : {semantics['dBT_max']:.2f} K")
    print("    Interpretation: Sub-pixel high-temperature fires radiate much more strongly at 3.9 um (I-4)")
    print("    than at 11 um (I-5). A positive dBT confirms an active thermal anomaly.")
    
    # FRP analysis
    frp = df_borneo["frp"]
    semantics["frp_mean"] = float(frp.mean())
    semantics["frp_median"] = float(frp.median())
    semantics["frp_max"] = float(frp.max())
    semantics["frp_p90"] = float(np.percentile(frp, 90))
    
    print("\n  Fire Radiative Power (FRP) Analysis:")
    print(f"    FRP Mean   : {semantics['frp_mean']:.2f} MW")
    print(f"    FRP Median : {semantics['frp_median']:.2f} MW")
    print(f"    FRP P90    : {semantics['frp_p90']:.2f} MW")
    print(f"    FRP Max    : {semantics['frp_max']:.2f} MW")
    print("    Interpretation: FRP directly quantifies the instantaneous rate of heat energy released (MW).")
    
    # Confidence breakdown
    conf_breakdown = df_borneo.groupby("confidence").agg(
        count=("frp", "count"),
        mean_frp=("frp", "mean"),
        mean_ti4=("bright_ti4", "mean"),
        mean_dbt=("dBT_i4_i5", "mean")
    ).to_dict(orient="index")
    semantics["confidence_breakdown"] = conf_breakdown
    
    print("\n  Confidence Breakdown:")
    for conf, stats in conf_breakdown.items():
        print(f"    [{conf:<7}] Count: {stats['count']:,} | Mean FRP: {stats['mean_frp']:.2f} MW | Mean I-4: {stats['mean_ti4']:.1f} K | Mean dBT: {stats['mean_dbt']:.1f} K")
        
    return semantics


def prototype_himawari_join(df_borneo: pd.DataFrame, nc_path: str = HIMAWARI_NC_FILE) -> pd.DataFrame:
    """Demonstrate spatiotemporal match between VIIRS hotspot points and Himawari-9 B07 grid."""
    print("\n" + "=" * 60)
    print("STEP 8: PROTOTYPE SPATIOTEMPORAL JOIN WITH HIMAWARI-9 B07")
    print("=" * 60)
    
    if not os.path.exists(nc_path):
        print(f"  WARNING: Himawari NetCDF not found at {nc_path}. Skipping join prototype.")
        return df_borneo
        
    ds = xr.open_dataset(nc_path)
    print(f"  Loaded Himawari NetCDF: {nc_path}")
    print(f"  Himawari start time attr: {ds.attrs.get('start_time', 'N/A')}")
    
    # Extract lat/lon grid and B07 data
    hlon = ds["longitude"].values
    hlat = ds["latitude"].values
    hb07 = ds["B07"].values
    
    # Mask valid coordinates
    valid_mask = np.isfinite(hlon) & np.isfinite(hlat) & np.isfinite(hb07)
    valid_lons = hlon[valid_mask]
    valid_lats = hlat[valid_mask]
    valid_b07 = hb07[valid_mask]
    
    print(f"  Valid Himawari grid cells: {len(valid_b07):,}")
    
    # Build KDTree for spatial lookup
    grid_coords = np.column_stack([valid_lats, valid_lons])
    tree = cKDTree(grid_coords)
    
    # Query nearest Himawari pixel for each VIIRS detection
    viirs_coords = np.column_stack([df_borneo["latitude"].values, df_borneo["longitude"].values])
    distances_deg, indices = tree.query(viirs_coords, k=1)
    
    df_borneo["himawari_b07_bt"] = valid_b07[indices]
    df_borneo["himawari_grid_lat"] = valid_lats[indices]
    df_borneo["himawari_grid_lon"] = valid_lons[indices]
    df_borneo["dist_to_himawari_pixel_deg"] = distances_deg
    df_borneo["dist_to_himawari_pixel_km"] = distances_deg * 111.0  # approximate km
    
    # Himawari nominal time
    himawari_nominal_time = pd.to_datetime("2026-09-20 00:00:00", utc=True)
    df_borneo["time_diff_to_himawari_hours"] = (
        (df_borneo["datetime_utc"] - himawari_nominal_time).dt.total_seconds() / 3600.0
    )
    
    print("\n  Join Results Summary:")
    print(f"    Matched VIIRS points        : {len(df_borneo):,}")
    print(f"    Mean spatial distance to grid: {df_borneo['dist_to_himawari_pixel_km'].mean():.2f} km (max: {df_borneo['dist_to_himawari_pixel_km'].max():.2f} km)")
    print(f"    Himawari B07 at VIIRS points : min={df_borneo['himawari_b07_bt'].min():.2f} K, max={df_borneo['himawari_b07_bt'].max():.2f} K, mean={df_borneo['himawari_b07_bt'].mean():.2f} K")
    print(f"    Time delta range to Himawari : min={df_borneo['time_diff_to_himawari_hours'].min():.1f} h, max={df_borneo['time_diff_to_himawari_hours'].max():.1f} h")
    
    print("\n  Sample Joined Records (first 5):")
    sample_cols = ["latitude", "longitude", "acq_date", "acq_time", "bright_ti4", "frp", "himawari_b07_bt", "dist_to_himawari_pixel_km", "time_diff_to_himawari_hours"]
    print(df_borneo[sample_cols].head(5).to_string(index=False))
    
    # Save joined sample
    out_joined = PROCESSED_DIR / "viirs_himawari_joined_prototype.csv"
    df_borneo.to_csv(out_joined, index=False)
    print(f"\n  Saved prototype joined dataset: {out_joined}")
    
    return df_borneo


def generate_visualizations(df_borneo: pd.DataFrame, nc_path: str = HIMAWARI_NC_FILE):
    """Generate required visualization plots: map, distributions, and Himawari overlay."""
    print("\n" + "=" * 60)
    print("STEP 10 (Part 3): GENERATING VALIDATION VISUALIZATIONS")
    print("=" * 60)
    
    # Load coastlines if available
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

    # ── PLOT 1: VIIRS Kalimantan Detection Map ────────────────
    fig1, ax1 = plt.subplots(figsize=(11, 9), facecolor="#1e1e1e")
    ax1.set_facecolor("#121212")
    
    draw_coastlines(ax1)
    
    # Scatter VIIRS points colored by FRP (log scale or capped)
    frp_vals = np.clip(df_borneo["frp"].values, 0, 50)
    sc = ax1.scatter(
        df_borneo["longitude"], df_borneo["latitude"],
        c=frp_vals, cmap="YlOrRd", s=10, alpha=0.7, edgecolors="none"
    )
    cb1 = plt.colorbar(sc, ax=ax1, fraction=0.035, pad=0.03)
    cb1.set_label("Fire Radiative Power (MW, capped at 50)", color="white", fontsize=9)
    cb1.ax.tick_params(colors="white")
    
    # Add Bounding Box
    bbox_rect = mpatches.Rectangle(
        (BORNEO_BBOX["lon_min"], BORNEO_BBOX["lat_min"]),
        BORNEO_BBOX["lon_max"] - BORNEO_BBOX["lon_min"],
        BORNEO_BBOX["lat_max"] - BORNEO_BBOX["lat_min"],
        linewidth=1.5, edgecolor="cyan", facecolor="none", linestyle="--",
        label="Kalimantan Study Bbox"
    )
    ax1.add_patch(bbox_rect)
    
    # Add City markers
    for city, clat, clon in KALIMANTAN_CITIES:
        ax1.scatter(clon, clat, s=50, color="deepskyblue", edgecolors="white", linewidths=0.8, zorder=6)
        ax1.annotate(city, (clon, clat + 0.18), color="white", fontsize=8, fontweight="bold",
                     ha="center", bbox=dict(boxstyle="round,pad=0.15", fc="black", alpha=0.6))
        
    ax1.set_xlim(BORNEO_BBOX["lon_min"] - 0.5, BORNEO_BBOX["lon_max"] + 0.5)
    ax1.set_ylim(BORNEO_BBOX["lat_min"] - 0.5, BORNEO_BBOX["lat_max"] + 0.5)
    ax1.grid(True, color="#333333", linestyle=":", linewidth=0.6)
    ax1.tick_params(colors="white")
    ax1.set_xlabel("Longitude (deg E)", color="white", fontsize=10)
    ax1.set_ylabel("Latitude (deg)", color="white", fontsize=10)
    ax1.set_title(
        f"VIIRS Active Fire Detections — Kalimantan / Borneo\n"
        f"NOAA-20 VIIRS 375m (Collection 2 NRT) | Total Detections: {len(df_borneo):,}",
        color="white", fontsize=11
    )
    ax1.legend(loc="lower right", facecolor="#222222", edgecolor="gray", labelcolor="white", fontsize=8)
    
    out_map = VALIDATION_DIR / "viirs_kalimantan_map.png"
    fig1.savefig(out_map, dpi=150, bbox_inches="tight")
    plt.close(fig1)
    print(f"  Saved Plot 1 (Map): {out_map}")

    # ── PLOT 2: Statistical Distributions ────────────────────
    fig2, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor="#1e1e1e")
    for ax in axes.flat:
        ax.set_facecolor("#121212")
        ax.tick_params(colors="white")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.title.set_color("white")
        for s in ax.spines.values():
            s.set_color("gray")
            
    # Subplot A: Brightness Temperature I-4
    axes[0, 0].hist(df_borneo["bright_ti4"], bins=60, color="crimson", alpha=0.85, edgecolor="black")
    axes[0, 0].axvline(df_borneo["bright_ti4"].median(), color="yellow", linestyle="--", label=f"Median: {df_borneo['bright_ti4'].median():.1f} K")
    axes[0, 0].set_title("Brightness Temperature I-4 (3.9 um) [K]", fontsize=10)
    axes[0, 0].set_xlabel("Kelvin")
    axes[0, 0].set_ylabel("Detection Count")
    axes[0, 0].legend(facecolor="#222", labelcolor="white", fontsize=8)
    
    # Subplot B: Fire Radiative Power (Log scale)
    frp_clean = df_borneo["frp"][df_borneo["frp"] > 0]
    axes[0, 1].hist(frp_clean, bins=np.logspace(np.log10(0.1), np.log10(max(frp_clean.max(), 100)), 50),
                    color="darkorange", alpha=0.85, edgecolor="black")
    axes[0, 1].set_xscale("log")
    axes[0, 1].axvline(frp_clean.median(), color="cyan", linestyle="--", label=f"Median: {frp_clean.median():.2f} MW")
    axes[0, 1].set_title("Fire Radiative Power (FRP) Distribution [MW]", fontsize=10)
    axes[0, 1].set_xlabel("FRP (MW, log scale)")
    axes[0, 1].set_ylabel("Detection Count")
    axes[0, 1].legend(facecolor="#222", labelcolor="white", fontsize=8)
    
    # Subplot C: Confidence Distribution
    conf_counts = df_borneo["confidence"].value_counts()
    axes[1, 0].bar(conf_counts.index, conf_counts.values, color=["gold", "salmon", "lightgray"][:len(conf_counts)], edgecolor="black")
    for i, (k, v) in enumerate(conf_counts.items()):
        axes[1, 0].text(i, v + len(df_borneo)*0.01, f"{v:,}\n({100*v/len(df_borneo):.1f}%)",
                        ha="center", color="white", fontsize=8)
    axes[1, 0].set_title("Detection Confidence Distribution", fontsize=10)
    axes[1, 0].set_ylabel("Detection Count")
    
    # Subplot D: Day / Night Distribution & dBT
    daynight_counts = df_borneo["daynight"].value_counts()
    axes[1, 1].bar(daynight_counts.index.map({"D": "Day (D)", "N": "Night (N)"}), daynight_counts.values,
                   color=["orange", "navy"][:len(daynight_counts)], edgecolor="black")
    for i, (k, v) in enumerate(daynight_counts.items()):
        axes[1, 1].text(i, v + len(df_borneo)*0.01, f"{v:,}\n({100*v/len(df_borneo):.1f}%)",
                        ha="center", color="white", fontsize=8)
    axes[1, 1].set_title("Day vs Night Detections", fontsize=10)
    axes[1, 1].set_ylabel("Detection Count")
    
    fig2.suptitle("VIIRS Active Fire — Statistical & Attribute Distributions", color="white", fontsize=12)
    out_dist = VALIDATION_DIR / "viirs_distributions.png"
    fig2.savefig(out_dist, dpi=150, bbox_inches="tight")
    plt.close(fig2)
    print(f"  Saved Plot 2 (Distributions): {out_dist}")

    # ── PLOT 3: Overlay VIIRS on Himawari B07 Grid ────────────
    if os.path.exists(nc_path):
        ds = xr.open_dataset(nc_path)
        hlon = ds["longitude"].values
        hlat = ds["latitude"].values
        hb07 = ds["B07"].values
        
        fig3, ax3 = plt.subplots(figsize=(11, 9), facecolor="#1e1e1e")
        ax3.set_facecolor("#121212")
        
        valid_b07 = np.isfinite(hb07)
        vmin, vmax = np.nanpercentile(hb07[valid_b07], [5, 95]) if valid_b07.any() else (270, 310)
        
        # Background: Himawari B07 BT
        pm = ax3.pcolormesh(hlon, hlat, hb07, cmap="gray", vmin=vmin, vmax=vmax, shading="auto")
        cb3 = plt.colorbar(pm, ax=ax3, fraction=0.035, pad=0.03)
        cb3.set_label("Himawari-9 B07 Brightness Temp (K)", color="white", fontsize=9)
        cb3.ax.tick_params(colors="white")
        
        draw_coastlines(ax3)
        
        # Foreground: VIIRS Hotspots
        ax3.scatter(
            df_borneo["longitude"], df_borneo["latitude"],
            c="red", s=12, alpha=0.8, marker="^", label=f"VIIRS 375m Hotspots (N={len(df_borneo):,})"
        )
        
        ax3.set_xlim(BORNEO_BBOX["lon_min"] - 0.5, BORNEO_BBOX["lon_max"] + 0.5)
        ax3.set_ylim(BORNEO_BBOX["lat_min"] - 0.5, BORNEO_BBOX["lat_max"] + 0.5)
        ax3.grid(True, color="#444444", linestyle=":", linewidth=0.6)
        ax3.tick_params(colors="white")
        ax3.set_xlabel("Longitude (deg E)", color="white", fontsize=10)
        ax3.set_ylabel("Latitude (deg)", color="white", fontsize=10)
        ax3.set_title(
            "Himawari-9 B07 Thermal Grid + VIIRS 375m Active Fire Overlay\n"
            "Spatial Resolution Comparison: 2 km Geostationary vs ~375 m Polar Orbiting",
            color="white", fontsize=11
        )
        ax3.legend(loc="lower right", facecolor="#222222", edgecolor="gray", labelcolor="white", fontsize=8)
        
        out_overlay = VALIDATION_DIR / "viirs_himawari_overlay.png"
        fig3.savefig(out_overlay, dpi=150, bbox_inches="tight")
        plt.close(fig3)
        print(f"  Saved Plot 3 (Himawari Overlay): {out_overlay}")


def main():
    parser = argparse.ArgumentParser(description="Validate VIIRS Active Fire Data for Kalimantan")
    parser.add_argument("--input", default=DEFAULT_RAW_FILE, help="Path to raw VIIRS CSV")
    parser.add_argument("--himawari_nc", default=HIMAWARI_NC_FILE, help="Path to Himawari NetCDF")
    args = parser.parse_args()
    
    print("=" * 60)
    print("VIIRS ACTIVE FIRE DATA VALIDATION SUITE")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    if not os.path.exists(args.input):
        print(f"ERROR: Raw input file not found at {args.input}")
        sys.exit(1)
        
    df_raw = load_raw_viirs(args.input)
    schema_results = validate_schema(df_raw)
    quality_results = inspect_data_quality(df_raw)
    df_borneo = subset_and_process_kalimantan(df_raw)
    semantics_results = validate_fire_semantics(df_borneo)
    df_joined = prototype_himawari_join(df_borneo, args.himawari_nc)
    generate_visualizations(df_joined, args.himawari_nc)
    
    # Save overall validation summary JSON
    summary = {
        "timestamp_validated": datetime.now().isoformat(),
        "raw_file": args.input,
        "total_raw_records": len(df_raw),
        "kalimantan_records": len(df_borneo),
        "schema_valid": all(v["present"] for v in schema_results.values()),
        "quality": quality_results,
        "semantics": semantics_results,
    }
    with open(VALIDATION_DIR / "viirs_validation_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nSaved validation metrics JSON: {VALIDATION_DIR / 'viirs_validation_summary.json'}")
    print("\nVIIRS Validation Script Complete!")


if __name__ == "__main__":
    main()
