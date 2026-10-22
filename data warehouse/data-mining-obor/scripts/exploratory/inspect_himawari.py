from satpy import Scene

filename = (
    "data/"
    "HS_H09_20260920_0000_B07_FLDK_R20_S0510.DAT"
)

scn = Scene(
    filenames=[filename],
    reader="ahi_hsd"
)

print("Available datasets:")
print(scn.available_dataset_names())

# Load Band 07
scn.load(["B07"])

print("\nLoaded dataset:")
print(scn["B07"])

print("\nMetadata:")
for key, value in scn["B07"].attrs.items():
    print(f"{key}: {value}")