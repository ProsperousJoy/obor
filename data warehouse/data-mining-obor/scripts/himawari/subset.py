"""
scripts/subset_himawari.py
===========================
Subset Himawari-9 AHI data to a geographic bounding box (e.g., Kalimantan)
and save the result as a NetCDF file with embedded lat/lon coordinates.

Usage (as module):
    from scripts.subset_himawari import subset_to_bbox, save_as_netcdf

Usage (CLI):
    python scripts/subset_himawari.py \\
        --file data/HS_H09_20260920_0000_B07_FLDK_R20_S0510.DAT \\
        --band B07 \\
        --output outputs/himawari_b07_s0510_borneo.nc
"""

import argparse
import warnings
from pathlib import Path
from typing import Optional, Tuple, Dict

import numpy as np
import xarray as xr

warnings.filterwarnings("ignore", category=UserWarning)

# Default Kalimantan bounding box
BORNEO_BBOX = {
    "lon_min": 108.0,
    "lon_max": 119.0,
    "lat_min": -5.0,
    "lat_max":  7.0,
}


def subset_to_bbox(da, lons: np.ndarray, lats: np.ndarray,
                   bbox: dict) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """
    Subset a DataArray to rows/cols within a geographic bounding box.

    Args:
        da   : xarray.DataArray from Satpy
        lons : lon grid (rows x cols)
        lats : lat grid (rows x cols)
        bbox : dict with lon_min/lon_max/lat_min/lat_max

    Returns:
        data_sub (np.ndarray) : subset data values
        lons_sub (np.ndarray) : subset longitude grid
        lats_sub (np.ndarray) : subset latitude grid
        slice_info (dict)     : row/col slice ranges used

    Raises:
        ValueError : If no pixels fall within the bounding box
    """
    data_np = np.array(da)

    # Pixel mask: inside bbox AND geo coords valid
    FILL_THRESHOLD = 1e10
    geo_valid = (
        (np.abs(lons) < FILL_THRESHOLD) & (np.abs(lats) < FILL_THRESHOLD) &
        np.isfinite(lons) & np.isfinite(lats)
    )
    pixel_mask = (
        (lons >= bbox["lon_min"]) & (lons <= bbox["lon_max"]) &
        (lats >= bbox["lat_min"]) & (lats <= bbox["lat_max"]) &
        geo_valid
    )

    if not pixel_mask.any():
        raise ValueError(
            f"No pixels found in bounding box: "
            f"Lon [{bbox['lon_min']}, {bbox['lon_max']}], "
            f"Lat [{bbox['lat_min']}, {bbox['lat_max']}]"
        )

    rows_b, cols_b = np.where(pixel_mask)
    row_min, row_max = int(rows_b.min()), int(rows_b.max())
    col_min, col_max = int(cols_b.min()), int(cols_b.max())

    data_sub = data_np[row_min:row_max+1, col_min:col_max+1]
    lons_sub  = lons[row_min:row_max+1, col_min:col_max+1]
    lats_sub  = lats[row_min:row_max+1, col_min:col_max+1]

    slice_info = {
        "row_min": row_min, "row_max": row_max,
        "col_min": col_min, "col_max": col_max,
        "n_bbox_pixels": int(pixel_mask.sum()),
    }

    return data_sub, lons_sub, lats_sub, slice_info


def save_as_netcdf(data_sub: np.ndarray, lons_sub: np.ndarray, lats_sub: np.ndarray,
                   da_attrs: dict, band: str, bbox: dict,
                   slice_info: dict, output_path: str) -> Path:
    """
    Save subset data as a NetCDF file with embedded lat/lon and metadata.

    Args:
        data_sub    : 2D numpy array (rows x cols)
        lons_sub    : longitude grid matching data_sub
        lats_sub    : latitude grid matching data_sub
        da_attrs    : original DataArray attrs from Satpy
        band        : band name, e.g. "B07"
        bbox        : bounding box dict used for subsetting
        slice_info  : row/col slice info from subset_to_bbox()
        output_path : path for the output .nc file

    Returns:
        Path to the saved NetCDF file
    """
    start_time = da_attrs.get("start_time", "unknown")
    start_str  = str(start_time).replace(" ", "T")

    units       = da_attrs.get("units", "unknown")
    calibration = da_attrs.get("calibration", "unknown")
    platform    = da_attrs.get("platform_name", "unknown")
    sensor      = da_attrs.get("sensor", "unknown")

    ds = xr.Dataset(
        {
            band: xr.DataArray(
                data_sub,
                dims=["y", "x"],
                attrs={
                    "units"               : units,
                    "calibration"         : calibration,
                    "standard_name"       : da_attrs.get("standard_name", ""),
                    "long_name"           : f"Himawari-9 AHI {band} Brightness Temperature",
                    "platform_name"       : platform,
                    "sensor"              : sensor,
                    "wavelength_central"  : str(da_attrs.get("wavelength", "")),
                    "resolution_m"        : da_attrs.get("resolution", ""),
                },
            ),
            "longitude": xr.DataArray(
                lons_sub,
                dims=["y", "x"],
                attrs={
                    "units"    : "degrees_east",
                    "long_name": "longitude",
                },
            ),
            "latitude": xr.DataArray(
                lats_sub,
                dims=["y", "x"],
                attrs={
                    "units"    : "degrees_north",
                    "long_name": "latitude",
                },
            ),
        },
        attrs={
            "title"           : f"Himawari-9 AHI {band} Kalimantan Subset",
            "source"          : "NOAA Himawari-9 AHI HSD via AWS S3 noaa-himawari9 (public)",
            "platform"        : platform,
            "sensor"          : sensor,
            "band"            : band,
            "start_time_utc"  : start_str,
            "bbox_lon_min"    : bbox["lon_min"],
            "bbox_lon_max"    : bbox["lon_max"],
            "bbox_lat_min"    : bbox["lat_min"],
            "bbox_lat_max"    : bbox["lat_max"],
            "row_slice"       : f"{slice_info['row_min']}:{slice_info['row_max']+1}",
            "col_slice"       : f"{slice_info['col_min']}:{slice_info['col_max']+1}",
            "n_bbox_pixels"   : slice_info["n_bbox_pixels"],
            "Conventions"     : "CF-1.8",
        },
    )

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(str(out_path))
    print(f"[OK] Saved NetCDF: {out_path}  ({out_path.stat().st_size/1e6:.2f} MB)")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Subset Himawari-9 AHI band data to a geographic bounding box"
    )
    parser.add_argument("--file",    required=True, help="Path to .DAT file")
    parser.add_argument("--band",    default="B07", help="Band name (default: B07)")
    parser.add_argument("--output",  default=None,  help="Output .nc path")
    parser.add_argument("--lon-min", type=float, default=BORNEO_BBOX["lon_min"])
    parser.add_argument("--lon-max", type=float, default=BORNEO_BBOX["lon_max"])
    parser.add_argument("--lat-min", type=float, default=BORNEO_BBOX["lat_min"])
    parser.add_argument("--lat-max", type=float, default=BORNEO_BBOX["lat_max"])
    args = parser.parse_args()

    import sys
    sys.path.insert(0, ".")
    from scripts.read_himawari    import read_himawari_band
    from scripts.geolocate_himawari import get_lonlat_grid

    bbox = {
        "lon_min": args.lon_min, "lon_max": args.lon_max,
        "lat_min": args.lat_min, "lat_max": args.lat_max,
    }

    stem = Path(args.file).stem.replace(".DAT", "")
    if args.output is None:
        args.output = f"outputs/{stem}_{args.band}_borneo.nc"

    print(f"Reading: {args.file}")
    da = read_himawari_band(args.file, args.band)

    print("Computing lat/lon grid...")
    lons, lats, _ = get_lonlat_grid(da)

    print(f"Subsetting to bbox: {bbox}")
    data_sub, lons_sub, lats_sub, slice_info = subset_to_bbox(da, lons, lats, bbox)
    print(f"  Subset shape: {data_sub.shape}")
    print(f"  Pixels in bbox: {slice_info['n_bbox_pixels']:,}")

    save_as_netcdf(
        data_sub, lons_sub, lats_sub,
        da_attrs=da.attrs, band=args.band,
        bbox=bbox, slice_info=slice_info,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
