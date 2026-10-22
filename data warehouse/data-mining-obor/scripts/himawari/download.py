"""
scripts/download_himawari.py
============================
Download and decompress a single Himawari-9 AHI HSD file from
the public NOAA AWS S3 bucket (no credentials required).

Usage:
    python scripts/download_himawari.py --date 20260920 --time 0000 --band B07 --segment S0510

Parameters:
    --date      : Observation date in YYYYMMDD format
    --time      : Observation time in HHMM format (UTC)
    --band      : Band identifier, e.g. B07
    --segment   : Segment identifier, e.g. S0510
    --outdir    : (optional) Output directory. Defaults to "data/"
    --no-decompress : (optional) Skip decompression of .bz2 file

Output:
    data/<filename>.DAT.bz2   (raw download)
    data/<filename>.DAT       (decompressed, unless --no-decompress)

Notes:
    - If the file already exists locally, download is SKIPPED.
    - Bucket: s3://noaa-himawari9 (public, no auth required)
    - Path pattern: AHI-L1b-FLDK/{YYYY}/{MM}/{DD}/{HHMM}/
"""

import argparse
import bz2
import sys
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config


# ─────────────────────────────────────────────
# S3 CLIENT (anonymous access)
# ─────────────────────────────────────────────
def _get_s3_client():
    return boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(signature_version=UNSIGNED),
    )


# ─────────────────────────────────────────────
# FILENAME BUILDER
# ─────────────────────────────────────────────
def build_filename(date: str, time: str, band: str, segment: str) -> str:
    """
    Build the HSD filename from components.

    Args:
        date    : YYYYMMDD
        time    : HHMM
        band    : e.g. B07
        segment : e.g. S0510

    Returns:
        filename stem, e.g. HS_H09_20260920_0000_B07_FLDK_R20_S0510.DAT
    """
    # Resolution lookup by band
    BAND_RESOLUTION = {
        "B01": "R10", "B02": "R10", "B03": "R05",
        "B04": "R10", "B05": "R20", "B06": "R10",
        "B07": "R20", "B08": "R20", "B09": "R20",
        "B10": "R20", "B11": "R20", "B12": "R20",
        "B13": "R20", "B14": "R20", "B15": "R20",
        "B16": "R20",
    }
    res = BAND_RESOLUTION.get(band.upper(), "R20")
    return f"HS_H09_{date}_{time}_{band.upper()}_FLDK_{res}_{segment}.DAT"


def build_s3_key(date: str, time: str, filename_bz2: str) -> str:
    """
    Build the S3 key for the given file.

    Args:
        date         : YYYYMMDD
        time         : HHMM
        filename_bz2 : e.g. HS_H09_20260920_0000_B07_FLDK_R20_S0510.DAT.bz2

    Returns:
        S3 key string
    """
    yyyy = date[:4]
    mm   = date[4:6]
    dd   = date[6:8]
    return f"AHI-L1b-FLDK/{yyyy}/{mm}/{dd}/{time}/{filename_bz2}"


# ─────────────────────────────────────────────
# DOWNLOAD
# ─────────────────────────────────────────────
def download_file(date: str, time: str, band: str, segment: str,
                  outdir: str = "data", skip_if_exists: bool = True) -> Path:
    """
    Download a single Himawari-9 HSD .bz2 file from S3.

    Returns path to the downloaded .bz2 file.
    Skips download if file already exists locally.
    """
    outdir_path = Path(outdir)
    outdir_path.mkdir(parents=True, exist_ok=True)

    filename     = build_filename(date, time, band, segment)
    filename_bz2 = filename + ".bz2"
    s3_key       = build_s3_key(date, time, filename_bz2)
    local_path   = outdir_path / filename_bz2

    if skip_if_exists and local_path.exists():
        print(f"[SKIP] Already exists: {local_path}")
        return local_path

    s3 = _get_s3_client()
    print(f"[DOWNLOAD] s3://noaa-himawari9/{s3_key}")
    print(f"        -> {local_path}")

    try:
        s3.download_file("noaa-himawari9", s3_key, str(local_path))
        size_mb = local_path.stat().st_size / 1e6
        print(f"[OK] Downloaded {size_mb:.1f} MB")
    except Exception as e:
        print(f"[ERROR] Download failed: {e}", file=sys.stderr)
        raise

    return local_path


# ─────────────────────────────────────────────
# DECOMPRESS
# ─────────────────────────────────────────────
def decompress_file(bz2_path: Path, skip_if_exists: bool = True) -> Path:
    """
    Decompress a .bz2 file in-place.

    Returns path to the decompressed .DAT file.
    """
    dat_path = bz2_path.with_suffix("")  # remove .bz2

    if skip_if_exists and dat_path.exists():
        print(f"[SKIP] Already decompressed: {dat_path}")
        return dat_path

    print(f"[DECOMPRESS] {bz2_path.name} -> {dat_path.name}")
    with bz2.open(bz2_path, "rb") as src:
        with open(dat_path, "wb") as dst:
            dst.write(src.read())

    size_mb = dat_path.stat().st_size / 1e6
    print(f"[OK] Decompressed {size_mb:.1f} MB -> {dat_path}")
    return dat_path


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Download and decompress Himawari-9 AHI HSD file from NOAA S3"
    )
    parser.add_argument("--date",    required=True, help="Date YYYYMMDD")
    parser.add_argument("--time",    required=True, help="Time HHMM (UTC)")
    parser.add_argument("--band",    required=True, help="Band e.g. B07")
    parser.add_argument("--segment", required=True, help="Segment e.g. S0510")
    parser.add_argument("--outdir",  default="data", help="Output directory (default: data)")
    parser.add_argument("--no-decompress", action="store_true",
                        help="Skip decompression step")
    args = parser.parse_args()

    bz2_path = download_file(
        date=args.date, time=args.time,
        band=args.band, segment=args.segment,
        outdir=args.outdir,
    )

    if not args.no_decompress:
        decompress_file(bz2_path)


if __name__ == "__main__":
    main()
