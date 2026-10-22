"""
explore_himawari.py
===================
One-shot exploration script for Himawari-9 AHI HSD data.
Covers Steps 1-7 from the pipeline plan:
  1. Load B07
  2. Inspect metadata
  3. Compute statistics (NaN-safe)
  4. Visualize full segment
  5. Geolocation: lat/lon, bounding box
  6. Check S0510 coverage over Kalimantan
  7. Subset to Kalimantan, save PNG + NetCDF
  8. Brightness temperature / calibration check

Outputs written to: outputs/
"""

import os
import sys
import warnings
import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=UserWarning)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
HSD_FILE = "data/HS_H09_20260920_0000_B07_FLDK_R20_S0510.DAT"
BAND = "B07"
OUTPUT_DIR = "outputs"

# Kalimantan bounding box (approximate, full island incl. Sabah/Sarawak/Brunei)
BORNEO_LON_MIN = 108.0
BORNEO_LON_MAX = 119.0
BORNEO_LAT_MIN = -5.0
BORNEO_LAT_MAX =  7.0

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# STEP 1: LOAD DATASET
# ─────────────────────────────────────────────
print("=" * 60)
print("STEP 1 — LOAD DATASET")
print("=" * 60)

from satpy import Scene

print(f"File : {HSD_FILE}")
print(f"Band : {BAND}")
print()

scn = Scene(filenames=[HSD_FILE], reader="ahi_hsd")

print("Available datasets:", scn.available_dataset_names())

scn.load([BAND])
da = scn[BAND]  # xarray DataArray

print(f"\nType  : {type(da)}")
print(f"Shape : {da.shape}")
print(f"Dims  : {da.dims}")
print(f"Dtype : {da.dtype}")

# ─────────────────────────────────────────────
# STEP 1 cont: STATISTICS (NaN-safe)
# ─────────────────────────────────────────────
print("\n--- Statistics (NaN-safe) ---")

data_np = np.array(da)  # compute dask if needed
valid_mask = np.isfinite(data_np)
n_valid = valid_mask.sum()
n_total = data_np.size
n_nan   = n_total - n_valid

print(f"  Total pixels : {n_total:,}")
print(f"  Valid pixels : {n_valid:,}  ({100*n_valid/n_total:.1f}%)")
print(f"  NaN/Inf      : {n_nan:,}")

if n_valid > 0:
    valid_data = data_np[valid_mask]
    print(f"  Min          : {valid_data.min():.4f}")
    print(f"  Max          : {valid_data.max():.4f}")
    print(f"  Mean         : {valid_data.mean():.4f}")
    print(f"  Std          : {valid_data.std():.4f}")
    print(f"  Median       : {np.median(valid_data):.4f}")
else:
    print("  WARNING: No valid data found!")
    sys.exit(1)

# ─────────────────────────────────────────────
# STEP 2: METADATA INSPECTION
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2 — METADATA INSPECTION")
print("=" * 60)

attrs = da.attrs
KEY_ATTRS = [
    "platform_name", "sensor", "start_time", "end_time",
    "resolution", "calibration", "units", "wavelength",
    "standard_name", "long_name", "orbital_parameters",
    "satellite_longitude", "satellite_latitude", "satellite_altitude",
    "projection", "area",
]

print("\n--- Key Attributes ---")
for k in KEY_ATTRS:
    if k in attrs:
        print(f"  {k:<30} : {attrs[k]}")

print("\n--- All Attributes ---")
for k, v in attrs.items():
    print(f"  {k:<30} : {v}")

# Extract important values
units_val = attrs.get("units", "NOT SPECIFIED")
calibration_val = attrs.get("calibration", "NOT SPECIFIED")
platform = attrs.get("platform_name", "unknown")
sensor = attrs.get("sensor", "unknown")
start_time = attrs.get("start_time", "unknown")

print(f"\n>>> Units       : {units_val}")
print(f">>> Calibration : {calibration_val}")
print(f">>> Platform    : {platform}")
print(f">>> Sensor      : {sensor}")
print(f">>> Start time  : {start_time}")

# ─────────────────────────────────────────────
# STEP 3: VISUALIZE FULL SEGMENT
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3 — VISUALIZE FULL SEGMENT")
print("=" * 60)

fig, ax = plt.subplots(figsize=(10, 8))

# Use percentile clipping for better contrast
p2, p98 = np.nanpercentile(data_np[valid_mask], [2, 98])
im = ax.imshow(data_np, cmap="inferno", vmin=p2, vmax=p98, origin="upper")

cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
cb.set_label(f"Value [{units_val}]")

ax.set_title(
    f"Himawari-9 AHI {BAND} — Full Segment S0510\n"
    f"{start_time}  |  Calibration: {calibration_val}",
    fontsize=11
)
ax.set_xlabel("Column (pixel)")
ax.set_ylabel("Row (pixel)")

out_full = os.path.join(OUTPUT_DIR, "himawari_b07_s0510_fullseg.png")
fig.savefig(out_full, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {out_full}")

# ─────────────────────────────────────────────
# STEP 4: GEOLOCATION
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 4 — GEOLOCATION")
print("=" * 60)

area = da.attrs.get("area", None)
if area is None:
    print("ERROR: No 'area' attribute found in dataset. Cannot geolocate.")
    sys.exit(1)

print(f"\n  Area name        : {area.area_id}")
print(f"  Description      : {area.description}")
print(f"  Shape (rows,cols): {area.shape}")
print(f"  Projection       : {area.proj_dict}")
print(f"  Area extent      : {area.area_extent}")
print(f"    (x_min, y_min, x_max, y_max) in projection units")

# Compute lat/lon grid
print("\n  Computing lat/lon grid (this may take a moment)...")
lons, lats = area.get_lonlats()

# Mask fill values (outside Earth disk → very large values)
FILL_THRESHOLD = 1e10
lon_valid_mask = (np.abs(lons) < FILL_THRESHOLD) & (np.abs(lats) < FILL_THRESHOLD)
lon_valid_mask &= np.isfinite(lons) & np.isfinite(lats)

# Also mask pixels with no actual data (NaN in the data array)
# This gives us the TRUE geographic extent of segment S0510
data_valid_mask = np.isfinite(data_np)
seg_data_geo_mask = lon_valid_mask & data_valid_mask

lons_valid = lons[lon_valid_mask]
lats_valid = lats[lon_valid_mask]

# True segment bounding box (where actual data exists)
lons_seg = lons[seg_data_geo_mask]
lats_seg = lats[seg_data_geo_mask]

print(f"\n  Valid geo pixels (full disk) : {lon_valid_mask.sum():,}")
print(f"  Valid data pixels (S0510)   : {seg_data_geo_mask.sum():,}")
print(f"\n  Bounding box of S0510 (actual data extent):")
if seg_data_geo_mask.any():
    print(f"    Lat min : {lats_seg.min():.3f} deg")
    print(f"    Lat max : {lats_seg.max():.3f} deg")
    print(f"    Lon min : {lons_seg.min():.3f} deg")
    print(f"    Lon max : {lons_seg.max():.3f} deg")
    seg_lat_min = float(lats_seg.min())
    seg_lat_max = float(lats_seg.max())
    seg_lon_min = float(lons_seg.min())
    seg_lon_max = float(lons_seg.max())
else:
    print("    WARNING: No valid data+geo pixels found!")
    sys.exit(1)

# ─────────────────────────────────────────────
# STEP 5: CEK KALIMANTAN COVERAGE
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 5 — KALIMANTAN COVERAGE CHECK")
print("=" * 60)

print(f"\n  Segment S0510 bbox  : Lat [{seg_lat_min:.2f} deg, {seg_lat_max:.2f} deg]  "
      f"Lon [{seg_lon_min:.2f} deg, {seg_lon_max:.2f} deg]")
print(f"  Kalimantan bbox     : Lat [{BORNEO_LAT_MIN} deg, {BORNEO_LAT_MAX} deg]  "
      f"Lon [{BORNEO_LON_MIN} deg, {BORNEO_LON_MAX} deg]")

# Check overlap
lat_overlap = not (seg_lat_max < BORNEO_LAT_MIN or seg_lat_min > BORNEO_LAT_MAX)
lon_overlap = not (seg_lon_max < BORNEO_LON_MIN or seg_lon_min > BORNEO_LON_MAX)
has_overlap = lat_overlap and lon_overlap

print(f"\n  Lat overlap : {lat_overlap}")
print(f"  Lon overlap : {lon_overlap}")
print(f"  OVERLAP     : {'YES' if has_overlap else 'NO'}")

# Count pixels inside Kalimantan bbox
borneo_pixel_mask = (
    (lons >= BORNEO_LON_MIN) & (lons <= BORNEO_LON_MAX) &
    (lats >= BORNEO_LAT_MIN) & (lats <= BORNEO_LAT_MAX) &
    lon_valid_mask
)
n_borneo_pixels = borneo_pixel_mask.sum()
print(f"\n  Pixels inside Kalimantan bbox : {n_borneo_pixels:,}")

if n_borneo_pixels == 0:
    print("\n  WARNING: Segment S0510 does not cover Kalimantan.")
    print("  Consider downloading adjacent segments.")
    SUBSET_POSSIBLE = False
else:
    coverage_pct = 100 * n_borneo_pixels / lon_valid_mask.sum()
    print(f"  Coverage                      : {coverage_pct:.1f}% of valid pixels")
    SUBSET_POSSIBLE = True

# ─────────────────────────────────────────────
# STEP 6: SUBSET KALIMANTAN
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 6 — SUBSET KALIMANTAN")
print("=" * 60)

if not SUBSET_POSSIBLE:
    print("  Skipping subset: segment does not cover Kalimantan.")
else:
    # Find row/col indices where Kalimantan pixels are
    rows_b, cols_b = np.where(borneo_pixel_mask)
    row_min, row_max = rows_b.min(), rows_b.max()
    col_min, col_max = cols_b.min(), cols_b.max()

    print(f"  Row range : [{row_min}, {row_max}]  (height: {row_max-row_min+1} px)")
    print(f"  Col range : [{col_min}, {col_max}]  (width:  {col_max-col_min+1} px)")

    # Slice the data array
    data_borneo = data_np[row_min:row_max+1, col_min:col_max+1]
    lons_borneo = lons[row_min:row_max+1, col_min:col_max+1]
    lats_borneo = lats[row_min:row_max+1, col_min:col_max+1]

    print(f"  Subset shape : {data_borneo.shape}")

    valid_b = np.isfinite(data_borneo)
    if valid_b.any():
        print(f"  Subset min   : {data_borneo[valid_b].min():.4f}")
        print(f"  Subset max   : {data_borneo[valid_b].max():.4f}")
        print(f"  Subset mean  : {data_borneo[valid_b].mean():.4f}")

    # --- Visualize subset ---
    fig2, ax2 = plt.subplots(figsize=(10, 8))
    p2b, p98b = np.nanpercentile(data_borneo[valid_b], [2, 98]) if valid_b.any() else (0, 1)
    im2 = ax2.imshow(data_borneo, cmap="inferno", vmin=p2b, vmax=p98b, origin="upper")
    cb2 = fig2.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)
    cb2.set_label(f"Value [{units_val}]")
    ax2.set_title(
        f"Himawari-9 AHI {BAND} -- Kalimantan Subset\n"
        f"{start_time}  |  Calibration: {calibration_val}\n"
        f"Lon [{BORNEO_LON_MIN} - {BORNEO_LON_MAX} deg E]  Lat [{BORNEO_LAT_MIN} - {BORNEO_LAT_MAX} deg]",
        fontsize=10
    )
    ax2.set_xlabel("Column (pixel)")
    ax2.set_ylabel("Row (pixel)")

    out_borneo_png = os.path.join(OUTPUT_DIR, "himawari_b07_s0510_borneo.png")
    fig2.savefig(out_borneo_png, dpi=150, bbox_inches="tight")
    plt.close(fig2)
    print(f"\n  Saved: {out_borneo_png}")

    # --- Save NetCDF ---
    import xarray as xr
    import pandas as pd

    start_str = str(start_time).replace(" ", "T") if start_time != "unknown" else "unknown"

    ds = xr.Dataset(
        {
            BAND: xr.DataArray(
                data_borneo,
                dims=["y", "x"],
                attrs={
                    "units"       : units_val,
                    "calibration" : calibration_val,
                    "platform"    : platform,
                    "sensor"      : sensor,
                    "band"        : BAND,
                    "description" : f"Himawari-9 AHI {BAND} Kalimantan subset",
                }
            ),
            "longitude": xr.DataArray(
                lons_borneo,
                dims=["y", "x"],
                attrs={"units": "degrees_east", "long_name": "longitude"}
            ),
            "latitude": xr.DataArray(
                lats_borneo,
                dims=["y", "x"],
                attrs={"units": "degrees_north", "long_name": "latitude"}
            ),
        },
        attrs={
            "title"          : "Himawari-9 AHI B07 Kalimantan Subset",
            "source"         : "NOAA Himawari-9 AHI HSD via AWS S3 noaa-himawari9",
            "start_time"     : start_str,
            "band"           : BAND,
            "segment"        : "S0510",
            "borneo_lon_min" : BORNEO_LON_MIN,
            "borneo_lon_max" : BORNEO_LON_MAX,
            "borneo_lat_min" : BORNEO_LAT_MIN,
            "borneo_lat_max" : BORNEO_LAT_MAX,
            "row_slice"      : f"{row_min}:{row_max+1}",
            "col_slice"      : f"{col_min}:{col_max+1}",
        }
    )

    out_borneo_nc = os.path.join(OUTPUT_DIR, "himawari_b07_s0510_borneo.nc")
    ds.to_netcdf(out_borneo_nc)
    print(f"  Saved: {out_borneo_nc}")

# ─────────────────────────────────────────────
# STEP 7: BRIGHTNESS TEMPERATURE / CALIBRATION
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 7 — BRIGHTNESS TEMPERATURE / CALIBRATION CHECK")
print("=" * 60)

print(f"\n  Band       : {BAND}  (~3.9 um SWIR)")
print(f"  Calibration confirmed from metadata: {calibration_val}")
print(f"  Units confirmed from metadata      : {units_val}")

# Try loading with explicit brightness_temperature calibration
print("\n  Attempting to load with calibration='brightness_temperature' ...")
try:
    scn_bt = Scene(filenames=[HSD_FILE], reader="ahi_hsd")
    scn_bt.load([BAND], calibration="brightness_temperature")
    da_bt = scn_bt[BAND]
    bt_np = np.array(da_bt)
    valid_bt = np.isfinite(bt_np)
    if valid_bt.any():
        bt_units = da_bt.attrs.get("units", "unknown")
        bt_cal   = da_bt.attrs.get("calibration", "unknown")
        print(f"  BT calibration : {bt_cal}")
        print(f"  BT units       : {bt_units}")
        print(f"  BT min         : {bt_np[valid_bt].min():.2f}")
        print(f"  BT max         : {bt_np[valid_bt].max():.2f}")
        print(f"  BT mean        : {bt_np[valid_bt].mean():.2f}")
        print(f"  BT median      : {np.median(bt_np[valid_bt]):.2f}")
        print(f"\n  NOTE: Values are in {bt_units}. "
              f"Typical Earth BT range for 3.9um: ~200-340 K.")
    else:
        print("  WARNING: No valid BT data after calibration.")
except Exception as e:
    print(f"  WARNING: brightness_temperature calibration not available: {e}")
    print("  The default calibration above is already what Satpy provides.")

# ─────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"\n  File      : {HSD_FILE}")
print(f"  Platform  : {platform}")
print(f"  Sensor    : {sensor}")
print(f"  Band      : {BAND}  (~3.9 um SWIR)")
print(f"  Start time: {start_time}")
print(f"  Shape     : {da.shape}")
print(f"  Dtype     : {da.dtype}")
print(f"  Units     : {units_val}")
print(f"  Calibration: {calibration_val}")
print(f"\n  Segment S0510 bbox:")
print(f"    Lat: [{seg_lat_min:.2f} deg, {seg_lat_max:.2f} deg]")
print(f"    Lon: [{seg_lon_min:.2f} deg, {seg_lon_max:.2f} deg]")
print(f"\n  Kalimantan coverage : {'YES' if SUBSET_POSSIBLE else 'NO'}")
if SUBSET_POSSIBLE:
    print(f"    Pixels in bbox    : {n_borneo_pixels:,}")

print(f"\n  Outputs:")
print(f"    {out_full}")
if SUBSET_POSSIBLE:
    print(f"    {out_borneo_png}")
    print(f"    {out_borneo_nc}")

print("\n  Done.")
