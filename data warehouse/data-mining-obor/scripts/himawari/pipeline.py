"""
scripts/pipeline.py
===================
End-to-end Himawari-9 data pipeline:

  AWS S3
    -> download .bz2
    -> decompress to .DAT
    -> read HSD with Satpy
    -> calibrate (brightness_temperature by default)
    -> compute lat/lon grid
    -> subset to Kalimantan (or custom bbox)
    -> save NetCDF output

Usage:
    python scripts/pipeline.py --date 20260920 --time 0000 --band B07 --segment S0510

    python scripts/pipeline.py \\
        --date 20260920 --time 0000 --band B07 --segment S0510 \\
        --outdir data \\
        --outputdir outputs \\
        --lon-min 108 --lon-max 119 --lat-min -5 --lat-max 7

    # Skip download (file already exists):
    python scripts/pipeline.py \\
        --date 20260920 --time 0000 --band B07 --segment S0510 \\
        --no-download

Output files (in outputs/<date>_<time>_<band>_<segment>/):
    <stem>_fullseg.png   - visualization of full segment
    <stem>_borneo.png    - visualization of Kalimantan subset
    <stem>_borneo.nc     - NetCDF with data + lat/lon (ML-ready)
"""

import argparse
import os
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)

# Add project root to path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def visualize_and_save(data_np, units, title, output_path):
    """Visualize a 2D array and save to PNG."""
    valid = np.isfinite(data_np)
    if not valid.any():
        print(f"  [WARN] No valid data to visualize. Skipping: {output_path}")
        return

    p2, p98 = np.nanpercentile(data_np[valid], [2, 98])
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(data_np, cmap="inferno", vmin=p2, vmax=p98, origin="upper")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label(f"Value [{units}]")
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("Column (pixel)")
    ax.set_ylabel("Row (pixel)")
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] Saved PNG: {output_path}")


def run_pipeline(
    date: str, time: str, band: str, segment: str,
    outdir: str = "data",
    outputdir: str = "outputs",
    bbox: dict = None,
    calibration: str = "brightness_temperature",
    skip_download: bool = False,
    skip_decompress: bool = False,
):
    """
    Run the full Himawari-9 pipeline for one file.

    Args:
        date         : YYYYMMDD
        time         : HHMM (UTC)
        band         : e.g. "B07"
        segment      : e.g. "S0510"
        outdir       : directory to store downloaded/decompressed .DAT files
        outputdir    : directory for PNG/NetCDF outputs
        bbox         : geographic bounding box dict (lon_min/lon_max/lat_min/lat_max)
        calibration  : Satpy calibration type
        skip_download: If True, skip S3 download (assumes .bz2 already present)
        skip_decompress: If True, skip bz2 decompression (assumes .DAT already present)

    Returns:
        dict with output file paths
    """
    try:
        from scripts.himawari.download import download_file, decompress_file, build_filename
        from scripts.himawari.read import read_himawari_band, print_band_summary
        from scripts.himawari.geolocate import (get_lonlat_grid, get_segment_bbox,
                                                check_overlap, count_pixels_in_bbox)
        from scripts.himawari.subset import subset_to_bbox, save_as_netcdf
    except ImportError:
        from scripts.download_himawari import download_file, decompress_file, build_filename
        from scripts.read_himawari import read_himawari_band, print_band_summary
        from scripts.geolocate_himawari import (get_lonlat_grid, get_segment_bbox,
                                                check_overlap, count_pixels_in_bbox)
        from scripts.subset_himawari import subset_to_bbox, save_as_netcdf

    if bbox is None:
        bbox = {"lon_min": 108.0, "lon_max": 119.0, "lat_min": -5.0, "lat_max": 7.0}

    # ── Output directory ──────────────────────────────────────
    run_tag   = f"{date}_{time}_{band}_{segment}"
    out_subdir = Path(outputdir) / run_tag
    out_subdir.mkdir(parents=True, exist_ok=True)

    stem         = build_filename(date, time, band, segment).replace(".DAT", "")
    out_fullseg  = out_subdir / f"{stem}_fullseg.png"
    out_borneo   = out_subdir / f"{stem}_borneo.png"
    out_nc       = out_subdir / f"{stem}_borneo.nc"

    print("=" * 60)
    print(f"Himawari-9 Pipeline: {run_tag}")
    print("=" * 60)

    # ── Step 1: Download ──────────────────────────────────────
    print("\n[1/5] DOWNLOAD")
    if skip_download:
        dat_path = Path(outdir) / build_filename(date, time, band, segment)
        if not dat_path.exists():
            alt_path = Path("data/himawari/raw") / build_filename(date, time, band, segment)
            if alt_path.exists():
                dat_path = alt_path
        print(f"  Skipping download. Expected file: {dat_path}")
    else:
        bz2_path = download_file(
            date=date, time=time, band=band, segment=segment,
            outdir=outdir,
        )
        if not skip_decompress:
            dat_path = decompress_file(bz2_path)
        else:
            dat_path = bz2_path.with_suffix("")

    if not dat_path.exists():
        raise FileNotFoundError(f"DAT file not found: {dat_path}")
    print(f"  DAT file: {dat_path}  ({dat_path.stat().st_size/1e6:.1f} MB)")

    # ── Step 2: Read & calibrate ──────────────────────────────
    print("\n[2/5] READ + CALIBRATE")
    da = read_himawari_band(str(dat_path), band, calibration)
    print_band_summary(da, band)

    data_np = np.array(da)
    units   = da.attrs.get("units", "unknown")
    cal     = da.attrs.get("calibration", "unknown")
    start_t = da.attrs.get("start_time", "unknown")

    # ── Step 3: Visualize full segment ────────────────────────
    print("\n[3/5] VISUALIZE FULL SEGMENT")
    visualize_and_save(
        data_np, units,
        title=f"Himawari-9 AHI {band} -- Full Segment {segment}\n"
              f"{start_t}  |  Calibration: {cal}",
        output_path=out_fullseg,
    )

    # ── Step 4: Geolocation ───────────────────────────────────
    print("\n[4/5] GEOLOCATE + SUBSET")
    print("  Computing lat/lon grid...")
    lons, lats, valid_mask = get_lonlat_grid(da)

    seg_bbox = get_segment_bbox(da, lons, lats, valid_mask)
    print(f"  Segment data bbox:")
    print(f"    Lat: [{seg_bbox['lat_min']:.2f}, {seg_bbox['lat_max']:.2f}] deg")
    print(f"    Lon: [{seg_bbox['lon_min']:.2f}, {seg_bbox['lon_max']:.2f}] deg")

    overlap = check_overlap(seg_bbox, bbox)
    print(f"  Kalimantan overlap: {overlap['has_overlap']}")

    n_borneo, _ = count_pixels_in_bbox(lons, lats, valid_mask, bbox)
    print(f"  Pixels in Kalimantan bbox: {n_borneo:,}")

    if n_borneo == 0:
        print("  [WARN] Segment does not cover Kalimantan bbox. No subset saved.")
        return {
            "dat_path"   : str(dat_path),
            "fullseg_png": str(out_fullseg),
            "borneo_png" : None,
            "borneo_nc"  : None,
        }

    # Subset
    data_sub, lons_sub, lats_sub, slice_info = subset_to_bbox(da, lons, lats, bbox)
    print(f"  Subset shape: {data_sub.shape}")

    # Visualize subset
    visualize_and_save(
        data_sub, units,
        title=(f"Himawari-9 AHI {band} -- Kalimantan Subset\n"
               f"{start_t}  |  Calibration: {cal}\n"
               f"Lon [{bbox['lon_min']} - {bbox['lon_max']} E]  "
               f"Lat [{bbox['lat_min']} - {bbox['lat_max']}]"),
        output_path=out_borneo,
    )

    # ── Step 5: Save NetCDF ───────────────────────────────────
    print("\n[5/5] SAVE NetCDF")
    save_as_netcdf(
        data_sub, lons_sub, lats_sub,
        da_attrs=da.attrs, band=band,
        bbox=bbox, slice_info=slice_info,
        output_path=str(out_nc),
    )

    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"  Output dir: {out_subdir}")
    print(f"  {out_fullseg.name}")
    print(f"  {out_borneo.name}")
    print(f"  {out_nc.name}")
    print(f"{'='*60}")

    return {
        "dat_path"   : str(dat_path),
        "fullseg_png": str(out_fullseg),
        "borneo_png" : str(out_borneo),
        "borneo_nc"  : str(out_nc),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Himawari-9 AHI full pipeline: download -> read -> geolocate -> subset -> save"
    )
    parser.add_argument("--date",       required=True, help="Date YYYYMMDD")
    parser.add_argument("--time",       required=True, help="Time HHMM (UTC)")
    parser.add_argument("--band",       required=True, help="Band e.g. B07")
    parser.add_argument("--segment",    required=True, help="Segment e.g. S0510")
    parser.add_argument("--outdir",     default="data",    help="Data directory (default: data)")
    parser.add_argument("--outputdir",  default="outputs", help="Output directory (default: outputs)")
    parser.add_argument("--calibration", default="brightness_temperature",
                        help="Satpy calibration type (default: brightness_temperature)")
    parser.add_argument("--lon-min",    type=float, default=108.0)
    parser.add_argument("--lon-max",    type=float, default=119.0)
    parser.add_argument("--lat-min",    type=float, default=-5.0)
    parser.add_argument("--lat-max",    type=float, default=7.0)
    parser.add_argument("--no-download",    action="store_true",
                        help="Skip download (file already present)")
    parser.add_argument("--no-decompress",  action="store_true",
                        help="Skip decompression (DAT already present)")
    args = parser.parse_args()

    bbox = {
        "lon_min": args.lon_min, "lon_max": args.lon_max,
        "lat_min": args.lat_min, "lat_max": args.lat_max,
    }

    run_pipeline(
        date=args.date, time=args.time, band=args.band, segment=args.segment,
        outdir=args.outdir, outputdir=args.outputdir,
        bbox=bbox, calibration=args.calibration,
        skip_download=args.no_download,
        skip_decompress=args.no_decompress,
    )


if __name__ == "__main__":
    main()
