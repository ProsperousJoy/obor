import boto3
from botocore import UNSIGNED
from botocore.config import Config
from pathlib import Path

s3 = boto3.client(
    "s3",
    region_name="us-east-1",
    config=Config(signature_version=UNSIGNED)
)

key = (
    "AHI-L1b-FLDK/2026/09/20/0000/"
    "HS_H09_20260920_0000_B07_FLDK_R20_S0510.DAT.bz2"
)

output_dir = Path("data")
output_dir.mkdir(exist_ok=True)

filename = Path(key).name
output_path = output_dir / filename

print(f"Downloading: {filename}")

s3.download_file(
    "noaa-himawari9",
    key,
    str(output_path)
)

print(f"Saved to: {output_path}")