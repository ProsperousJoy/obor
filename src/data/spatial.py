"""Spatial utilities, coordinate resolution, and grid binning for Kalimantan / Borneo."""

from datetime import datetime, timezone
import math
from src.config import config

PROVINCE_REGIONS = [
    {
        "name": "Kalimantan Tengah",
        "code": "KT",
        "bbox": {"lat_min": -3.5, "lat_max": 0.5, "lon_min": 111.0, "lon_max": 115.8},
        "regencies": [
            ("Pulang Pisau", -2.48, 114.08, True),    # Peatland zone
            ("Palangka Raya", -2.21, 113.92, True),
            ("Kotawaringin Barat", -2.68, 111.62, True),
            ("Kotawaringin Timur", -2.53, 112.95, True),
            ("Kapuas", -2.95, 114.38, True),
            ("Katingan", -2.07, 113.40, True),
        ]
    },
    {
        "name": "Kalimantan Barat",
        "code": "KB",
        "bbox": {"lat_min": -3.1, "lat_max": 2.1, "lon_min": 108.5, "lon_max": 114.2},
        "regencies": [
            ("Ketapang", -1.82, 110.15, True),        # Peatland zone
            ("Pontianak", -0.02, 109.34, False),
            ("Kubu Raya", -0.55, 109.40, True),
            ("Sambas", 1.35, 109.30, False),
            ("Sintang", 0.07, 111.49, False),
        ]
    },
    {
        "name": "Kalimantan Selatan",
        "code": "KS",
        "bbox": {"lat_min": -4.2, "lat_max": -1.3, "lon_min": 114.2, "lon_max": 116.6},
        "regencies": [
            ("Banjar", -3.35, 114.85, False),
            ("Banjarmasin", -3.32, 114.59, False),
            ("Tanah Laut", -3.88, 114.78, False),
            ("Barito Kuala", -3.05, 114.58, True),
            ("Tapin", -2.92, 115.18, False),
        ]
    },
    {
        "name": "Kalimantan Timur",
        "code": "KI",
        "bbox": {"lat_min": -2.5, "lat_max": 2.5, "lon_min": 115.5, "lon_max": 119.2},
        "regencies": [
            ("Kutai Kartanegara", -0.35, 117.02, False),
            ("Samarinda", -0.50, 117.15, False),
            ("Paser", -1.85, 116.10, False),
            ("Berau", 2.15, 117.48, False),
            ("Kutai Timur", 0.55, 117.55, False),
        ]
    },
    {
        "name": "Kalimantan Utara",
        "code": "KU",
        "bbox": {"lat_min": 1.0, "lat_max": 4.5, "lon_min": 114.5, "lon_max": 118.0},
        "regencies": [
            ("Nunukan", 4.13, 117.65, False),
            ("Malinau", 3.42, 116.55, False),
            ("Bulungan", 2.84, 117.37, False),
            ("Tarakan", 3.32, 117.60, False),
        ]
    },
]


def resolve_location(lat: float, lon: float) -> tuple[str, str, bool]:
    """Resolve province, regency (kabupaten), and peatland flag from coordinates."""
    min_dist = float("inf")
    best_prov = "Kalimantan Tengah"
    best_regency = "Pulang Pisau"
    best_peat = False

    for prov in PROVINCE_REGIONS:
        for reg_name, r_lat, r_lon, is_peat in prov["regencies"]:
            d = (lat - r_lat) ** 2 + (lon - r_lon) ** 2
            if d < min_dist:
                min_dist = d
                best_prov = prov["name"]
                best_regency = reg_name
                best_peat = is_peat

    return best_prov, best_regency, best_peat


def assign_grid_id(lat: float, lon: float, resolution: float = 0.02) -> str:
    """Canonical ~2km grid cell ID generator matching warehouse ETL."""
    bbox = config.BORNEO_BBOX
    clamped_lat = max(bbox["lat_min"], min(lat, bbox["lat_max"]))
    clamped_lon = max(bbox["lon_min"], min(lon, bbox["lon_max"]))
    lat_idx = int(round((clamped_lat - bbox["lat_min"] + 1e-9) / resolution))
    lon_idx = int(round((clamped_lon - bbox["lon_min"] + 1e-9) / resolution))
    return f"G{lat_idx:04d}_{lon_idx:04d}"


def cluster_hotspots(hotspots: list[dict], max_dist_deg: float = 0.15) -> list[dict]:
    """
    Cluster individual 375m VIIRS hotspot pixels into coherent wildfire incidents.
    Uses O(N) spatial grid binning for lightning-fast clustering of thousands of hotspots.
    """
    if not hotspots:
        return []

    grid: dict[tuple[int, int], list[int]] = {}
    for i, h in enumerate(hotspots):
        cell = (int(h["latitude"] / max_dist_deg), int(h["longitude"] / max_dist_deg))
        grid.setdefault(cell, []).append(i)

    clusters = []
    visited = set()

    for i, h in enumerate(hotspots):
        if i in visited:
            continue

        cluster_pts = [h]
        visited.add(i)
        c_lat = int(h["latitude"] / max_dist_deg)
        c_lon = int(h["longitude"] / max_dist_deg)

        for d_lat in (-1, 0, 1):
            for d_lon in (-1, 0, 1):
                neighbor_cell = (c_lat + d_lat, c_lon + d_lon)
                for j in grid.get(neighbor_cell, []):
                    if j not in visited:
                        other = hotspots[j]
                        dist = math.hypot(h["latitude"] - other["latitude"], h["longitude"] - other["longitude"])
                        if dist <= max_dist_deg:
                            cluster_pts.append(other)
                            visited.add(j)

        centroid_lat = sum(p["latitude"] for p in cluster_pts) / len(cluster_pts)
        centroid_lon = sum(p["longitude"] for p in cluster_pts) / len(cluster_pts)
        total_frp = sum(p.get("frp", 10.0) or 10.0 for p in cluster_pts)
        max_frp = max((p.get("frp", 10.0) or 10.0) for p in cluster_pts)

        est_hectares = round(len(cluster_pts) * 14.0 * (1.0 + max_frp / 50.0), 1)
        est_acres = round(est_hectares * 2.47105, 1)

        prov, regency, is_peat = resolve_location(centroid_lat, centroid_lon)
        cluster_id = f"BORNEO-{prov[:3].upper()}-{int(abs(centroid_lat)*100)%1000:03d}{int(abs(centroid_lon)*100)%1000:03d}"

        cluster_fire = {
            "fire_id": cluster_id,
            "name": f"{regency} {'Peat' if is_peat else 'Forest'} Fire Cluster",
            "latitude": round(centroid_lat, 4),
            "longitude": round(centroid_lon, 4),
            "daily_acres": est_acres,
            "hectares": est_hectares,
            "percent_contained": max(5.0, min(80.0, 50.0 - len(cluster_pts) * 2.0)),
            "fire_cause": "Agricultural / Drainage Peat Clearing" if is_peat else "Dry Season Forest Fire",
            "discovery_time": cluster_pts[0].get("acq_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "state": prov,
            "province": prov,
            "county": regency,
            "is_peatland": is_peat,
            "frp": round(total_frp, 1),
            "pixel_count": len(cluster_pts),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        clusters.append(cluster_fire)

    clusters.sort(key=lambda c: c["daily_acres"], reverse=True)
    return clusters[:50]
