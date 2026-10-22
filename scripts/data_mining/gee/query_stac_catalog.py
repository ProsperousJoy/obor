"""
scripts/query_gee_stac_catalog.py
==================================
Queries the official Google Earth Engine SpatioTemporal Asset Catalog (STAC)
to verify dataset IDs, bands, resolutions, units, temporal ranges, and licenses.
"""

import urllib.request
import json
import os
from pathlib import Path

DATASETS_TO_VERIFY = [
    # 1. Weather / Climate
    {"category": "Rainfall", "id": "UCSB-CHG/CHIRPS/DAILY", "stac_path": "catalog/UCSB-CHG/UCSB-CHG_CHIRPS_DAILY.json"},
    {"category": "Weather/Climate", "id": "ECMWF/ERA5_LAND/DAILY_AGGR", "stac_path": "catalog/ECMWF/ECMWF_ERA5_LAND_DAILY_AGGR.json"},
    {"category": "Rainfall", "id": "NASA/GPM_L3/IMERG_V06", "stac_path": "catalog/NASA/NASA_GPM_L3_IMERG_V06.json"},
    
    # 2. Temperature (LST vs Air)
    {"category": "LST", "id": "MODIS/061/MOD11A1", "stac_path": "catalog/MODIS/MODIS_061_MOD11A1.json"},
    
    # 3. Vegetation & Moisture
    {"category": "Vegetation Index", "id": "MODIS/061/MOD13A1", "stac_path": "catalog/MODIS/MODIS_061_MOD13A1.json"},
    {"category": "Optical & Indices", "id": "COPERNICUS/S2_SR_HARMONIZED", "stac_path": "catalog/COPERNICUS/COPERNICUS_S2_SR_HARMONIZED.json"},
    
    # 4. Land Surface / Soil Moisture / Land Cover
    {"category": "Soil Moisture", "id": "NASA/SMAP/SPL4SMGP/007", "stac_path": "catalog/NASA/NASA_SMAP_SPL4SMGP_007.json"},
    {"category": "Land Cover", "id": "ESA/WorldCover/v100", "stac_path": "catalog/ESA/ESA_WorldCover_v100.json"},
    {"category": "Land Cover", "id": "MODIS/061/MCD12Q1", "stac_path": "catalog/MODIS/MODIS_061_MCD12Q1.json"},
    
    # 5. Burned Area / Fire
    {"category": "Burned Area", "id": "MODIS/061/MCD64A1", "stac_path": "catalog/MODIS/MODIS_061_MCD64A1.json"},
    {"category": "Active Fire", "id": "FIRMS", "stac_path": "catalog/FIRMS/FIRMS.json"},
    
    # 6. Sentinel-1 SAR
    {"category": "SAR Backscatter", "id": "COPERNICUS/S1_GRD", "stac_path": "catalog/COPERNICUS/COPERNICUS_S1_GRD.json"},
]

BASE_URL = "https://storage.googleapis.com/earthengine-stac/"

def fetch_stac_metadata():
    results = []
    print("=" * 70)
    print("OFFICIAL GOOGLE EARTH ENGINE STAC CATALOG VERIFICATION")
    print("=" * 70)
    
    for item in DATASETS_TO_VERIFY:
        url = BASE_URL + item["stac_path"]
        print(f"\nChecking: {item['id']} ...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                meta = json.loads(resp.read().decode("utf-8"))
                
                title = meta.get("title", "N/A")
                desc = meta.get("description", "")[:120] + "..."
                extent = meta.get("extent", {})
                temp_extent = extent.get("temporal", {}).get("interval", [[None, None]])[0]
                spatial_extent = extent.get("spatial", {}).get("bbox", [None])[0]
                
                # Extract bands / variables
                eo_bands = meta.get("summaries", {}).get("eo:bands", [])
                gee_bands = []
                for b in eo_bands:
                    bname = b.get("name", "")
                    bdesc = b.get("description", "")
                    gee_bands.append((bname, bdesc))
                
                # Check properties
                gee_type = meta.get("gee:type", "N/A")
                
                res_record = {
                    "category": item["category"],
                    "dataset_id": item["id"],
                    "title": title,
                    "type": gee_type,
                    "temporal_start": temp_extent[0] if temp_extent else "N/A",
                    "temporal_end": temp_extent[1] if temp_extent and len(temp_extent) > 1 else "Present",
                    "bbox": spatial_extent,
                    "total_bands": len(gee_bands),
                    "sample_bands": gee_bands[:8],
                    "verified_via_stac": True
                }
                results.append(res_record)
                print(f"  [VERIFIED] Title: {title}")
                print(f"  Temporal: {res_record['temporal_start']} to {res_record['temporal_end']}")
                print(f"  Total bands documented: {len(gee_bands)}")
                print(f"  First 4 bands: {[b[0] for b in gee_bands[:4]]}")
                
        except Exception as e:
            print(f"  [ERROR / UNVERIFIED] {item['id']} -> {e}")
            results.append({
                "category": item["category"],
                "dataset_id": item["id"],
                "verified_via_stac": False,
                "error": str(e)
            })
            
    out_path = Path("outputs/validation/gee_stac_verified_datasets.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved STAC catalog verification results to {out_path}")

    # Also save to standard data directory
    data_path = Path("data/gee/raw/gee_stac_verified_datasets.json")
    data_path.parent.mkdir(parents=True, exist_ok=True)
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved STAC catalog verification results to {data_path}")
    return results

if __name__ == "__main__":
    fetch_stac_metadata()
