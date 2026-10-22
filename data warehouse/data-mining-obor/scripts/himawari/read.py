"""
scripts/read_himawari.py
========================
Read a Himawari-9 AHI HSD file using Satpy and return the loaded Scene.

Usage (as module):
    from scripts.read_himawari import read_himawari_band
    da = read_himawari_band("data/HS_H09_20260920_0000_B07_FLDK_R20_S0510.DAT", "B07")

Usage (CLI):
    python scripts/read_himawari.py --file data/HS_H09_...DAT --band B07

Output:
    Prints band metadata summary to stdout.
    Returns xarray.DataArray when used as a module.
"""

import argparse
import warnings

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)


def read_himawari_band(filepath: str, band: str,
                       calibration: str = "brightness_temperature"):
    """
    Load a single band from a Himawari-9 AHI HSD file.

    Args:
        filepath    : Path to the .DAT file (decompressed HSD)
        band        : Band name, e.g. "B07"
        calibration : Satpy calibration type. Options:
                      "brightness_temperature" (default for thermal bands),
                      "reflectance" (for visible/near-IR bands),
                      "radiance" (raw radiance)

    Returns:
        xarray.DataArray with shape (rows, cols), calibrated values,
        and full metadata in .attrs

    Raises:
        ValueError  : If the band is not available in the file
        FileNotFoundError : If the file does not exist
    """
    from pathlib import Path
    from satpy import Scene

    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"HSD file not found: {filepath}")

    scn = Scene(filenames=[str(path)], reader="ahi_hsd")
    available = scn.available_dataset_names()

    if band not in available:
        raise ValueError(
            f"Band '{band}' not available in {path.name}. "
            f"Available: {available}"
        )

    scn.load([band], calibration=calibration)
    da = scn[band]
    return da


def print_band_summary(da, band: str):
    """Print a human-readable summary of a loaded DataArray."""
    data_np = np.array(da)
    valid   = np.isfinite(data_np)
    attrs   = da.attrs

    print(f"  Band         : {band}")
    print(f"  Platform     : {attrs.get('platform_name', 'N/A')}")
    print(f"  Sensor       : {attrs.get('sensor', 'N/A')}")
    print(f"  Start time   : {attrs.get('start_time', 'N/A')}")
    print(f"  End time     : {attrs.get('end_time', 'N/A')}")
    print(f"  Calibration  : {attrs.get('calibration', 'N/A')}")
    print(f"  Units        : {attrs.get('units', 'N/A')}")
    print(f"  Wavelength   : {attrs.get('wavelength', 'N/A')}")
    print(f"  Resolution   : {attrs.get('resolution', 'N/A')} m")
    print(f"  Shape        : {da.shape}  (rows x cols)")
    print(f"  Dtype        : {da.dtype}")
    print(f"  Valid pixels : {valid.sum():,} / {data_np.size:,}  "
          f"({100*valid.sum()/data_np.size:.1f}%)")
    if valid.any():
        v = data_np[valid]
        print(f"  Min          : {v.min():.4f}")
        print(f"  Max          : {v.max():.4f}")
        print(f"  Mean         : {v.mean():.4f}")
        print(f"  Std          : {v.std():.4f}")


def main():
    parser = argparse.ArgumentParser(
        description="Read a Himawari-9 AHI HSD file and print band summary"
    )
    parser.add_argument("--file",        required=True, help="Path to .DAT file")
    parser.add_argument("--band",        default="B07", help="Band name (default: B07)")
    parser.add_argument("--calibration", default="brightness_temperature",
                        help="Calibration type (default: brightness_temperature)")
    args = parser.parse_args()

    print(f"Reading: {args.file}")
    da = read_himawari_band(args.file, args.band, args.calibration)
    print_band_summary(da, args.band)


if __name__ == "__main__":
    main()
