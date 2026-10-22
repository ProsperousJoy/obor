import bz2
from pathlib import Path

input_path = Path(
    "data/HS_H09_20260920_0000_B07_FLDK_R20_S0510.DAT.bz2"
)

output_path = input_path.with_suffix("")

print(f"Decompressing: {input_path.name}")

with bz2.open(input_path, "rb") as src:
    with open(output_path, "wb") as dst:
        dst.write(src.read())

print(f"Saved to: {output_path}")