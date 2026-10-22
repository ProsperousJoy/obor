import boto3
from botocore import UNSIGNED
from botocore.config import Config

s3 = boto3.client(
    "s3",
    region_name="us-east-1",
    config=Config(signature_version=UNSIGNED)
)

prefix = "AHI-L1b-FLDK/2026/09/20/0000/"

response = s3.list_objects_v2(
    Bucket="noaa-himawari9",
    Prefix=prefix
)

for obj in response.get("Contents", []):
    key = obj["Key"]

    if "_B07_" in key:
        print(key)