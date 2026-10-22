"""
scripts/geolocate_himawari.py
==============================
Extract geolocation information from a Satpy-loaded Himawari-9 DataArray.
Provides:
  - lat/lon grid computation
  - bounding box of actual data pixels (not full disk)
  - geographic overlap check with a target bounding box

Usage (as module):
    from scripts.geolocate_himawari import get_lonlat_grid, get_segment_bbox, check_overlap

Usage (CLI):
    python scripts/geolocate_himawari.py --file data/HS_H09_...DAT --band B07
"""

import argparse
import warnings

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)

# Kalimantan bounding box (full island incl. Sabah, Sarawak, Brunei)
BORNEO_BBOX = {
    "lon_min": 108.0,
    "lon_max": 119.0,
    "lat_min": -5.0,
    "lat_max":  7.0,
}


def get_lonlat_grid(da):
    """
    Compute the lat/lon grid for a Satpy DataArray.

    Args:
        da : xarray.DataArray loaded by Satpy (must have 'area' in attrs)

    Returns:
        lons (np.ndarray) : longitude grid, shape (rows, cols)
        lats (np.ndarray) : latitude grid, shape (rows, cols)
        valid_mask (np.ndarray bool) : True where geo coords are finite

    Notes:
        Pixels outside the Earth disk (geostationary geometry) will have
        large fill values. These are masked out by valid_mask.
    """
    area = da.attrs.get("area")
    if area is None:
        raise ValueError("DataArray has no 'area' attribute. Cannot geolocate.")

    lons, lats = area.get_lonlats()

    FILL_THRESHOLD = 1e10
    valid_mask = (
        (np.abs(lons) < FILL_THRESHOLD) &
        (np.abs(lats) < FILL_THRESHOLD) &
        np.isfinite(lons) &
        np.isfinite(lats)
    )

    return lons, lats, valid_mask


def get_segment_bbox(da, lons=None, lats=None, valid_mask=None):
    """
    Compute the geographic bounding box of pixels that actually contain data
    (i.e., not NaN and within the Earth disk).

    Args:
        da         : xarray.DataArray loaded by Satpy
        lons, lats : optional pre-computed grids from get_lonlat_grid()
        valid_mask : optional pre-computed geo mask

    Returns:
        dict with keys: lon_min, lon_max, lat_min, lat_max, n_valid_pixels
    """
    if lons is None or lats is None or valid_mask is None:
        lons, lats, valid_mask = get_lonlat_grid(da)

    data_np = np.array(da)
    data_valid = np.isfinite(data_np)
    combined   = valid_mask & data_valid

    if not combined.any():
        return {"lon_min": None, "lon_max": None,
                "lat_min": None, "lat_max": None,
                "n_valid_pixels": 0}

    return {
        "lon_min"       : float(lons[combined].min()),
        "lon_max"       : float(lons[combined].max()),
        "lat_min"       : float(lats[combined].min()),
        "lat_max"       : float(lats[combined].max()),
        "n_valid_pixels": int(combined.sum()),
    }


def check_overlap(segment_bbox: dict, target_bbox: dict) -> dict:
    """
    Check whether two geographic bounding boxes overlap.

    Args:
        segment_bbox : dict with lon_min/lon_max/lat_min/lat_max (segment)
        target_bbox  : dict with lon_min/lon_max/lat_min/lat_max (target area)

    Returns:
        dict with keys: lat_overlap (bool), lon_overlap (bool), has_overlap (bool)
    """
    lat_overlap = not (
        segment_bbox["lat_max"] < target_bbox["lat_min"] or
        segment_bbox["lat_min"] > target_bbox["lat_max"]
    )
    lon_overlap = not (
        segment_bbox["lon_max"] < target_bbox["lon_min"] or
        segment_bbox["lon_min"] > target_bbox["lon_max"]
    )
    return {
        "lat_overlap": lat_overlap,
        "lon_overlap": lon_overlap,
        "has_overlap": lat_overlap and lon_overlap,
    }


def count_pixels_in_bbox(lons, lats, valid_mask, bbox: dict) -> int:
    """
    Count pixels whose coordinates fall within a given bounding box.

    Args:
        lons, lats   : lat/lon grids
        valid_mask   : boolean mask for valid geo coords
        bbox         : dict with lon_min/lon_max/lat_min/lat_max

    Returns:
        Number of pixels within bbox
    """
    pixel_mask = (
        (lons >= bbox["lon_min"]) & (lons <= bbox["lon_max"]) &
        (lats >= bbox["lat_min"]) & (lats <= bbox["lat_max"]) &
        valid_mask
    )
    return int(pixel_mask.sum()), pixel_mask


def get_projection_info(da) -> dict:
    """
    Extract projection and orbital parameters from a Satpy DataArray.

    Returns:
        dict with projection details
    """
    area  = da.attrs.get("area")
    attrs = da.attrs
    orbital = attrs.get("orbital_parameters", {})

    info = {
        "area_id"           : area.area_id if area else None,
        "projection"        : area.proj_dict if area else None,
        "area_extent_m"     : area.area_extent if area else None,
        "shape_rc"          : area.shape if area else None,
        "satellite_lon"     : orbital.get("projection_longitude"),
        "satellite_lat"     : orbital.get("projection_latitude"),
        "satellite_alt_m"   : orbital.get("projection_altitude"),
        "nadir_lon"         : orbital.get("nadir_longitude"),
        "nadir_lat"         : orbital.get("nadir_latitude"),
    }
    return info


def main():
    parser = argparse.ArgumentParser(
        description="Print geolocation info for a Himawari-9 HSD file"
    )
    parser.add_argument("--file", required=True, help="Path to .DAT file")
    parser.add_argument("--band", default="B07", help="Band name (default: B07)")
    args = parser.parse_args()

    import sys
    sys.path.insert(0, ".")
    from scripts.read_himawari import read_himawari_band

    print(f"Reading: {args.file}")
    da = read_himawari_band(args.file, args.band)

    print("\n--- Projection Info ---")
    proj_info = get_projection_info(da)
    for k, v in proj_info.items():
        print(f"  {k:<25} : {v}")

    print("\n--- Computing lat/lon grid ---")
    lons, lats, valid_mask = get_lonlat_grid(da)
    print(f"  Full disk valid geo pixels: {valid_mask.sum():,}")

    print("\n--- Segment Data Bounding Box ---")
    bbox = get_segment_bbox(da, lons, lats, valid_mask)
    for k, v in bbox.items():
        print(f"  {k:<20} : {v}")

    print("\n--- Kalimantan Overlap ---")
    overlap = check_overlap(bbox, BORNEO_BBOX)
    for k, v in overlap.items():
        print(f"  {k:<20} : {v}")

    n_borneo, _ = count_pixels_in_bbox(lons, lats, valid_mask, BORNEO_BBOX)
    print(f"  Pixels in Kalimantan bbox: {n_borneo:,}")


if __name__ == "__main__":
    main()
