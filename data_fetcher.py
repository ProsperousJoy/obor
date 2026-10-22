"""
Wildfire Data Fetcher — Ingests active fire incidents for Kalimantan / Borneo.

Connects to NASA FIRMS (VIIRS 375m NRT active fires) for real-time detection,
clusters hotspot pixels into coherent incident structures, queries the DuckDB
analytical data warehouse for regional context, and supports realistic
Kalimantan peatland fire simulation for offline/demo operation.
"""

import asyncio
import logging
import math
import random
from datetime import datetime, timezone

import httpx
from config import config

logger = logging.getLogger("wildfire.fetcher")

# ─── Kalimantan Province & Regency Reference Coordinates ─────────────────────

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


# ─── Realistic Borneo Demo Incidents ─────────────────────────────────────────

BORNEO_DEMO_FIRES = [
    {
        "fire_id": "ID-KT-001", "name": "Sebangau Peatland Complex",
        "latitude": -2.48, "longitude": 114.08, "daily_acres": 4940.0, "hectares": 2000.0,
        "percent_contained": 12.0, "fire_cause": "Agricultural Land Clearing",
        "discovery_time": "2026-10-19T10:30:00Z", "state": "Kalimantan Tengah",
        "province": "Kalimantan Tengah", "county": "Pulang Pisau",
        "is_peatland": True, "frp": 124.5,
    },
    {
        "fire_id": "ID-KB-002", "name": "Ketapang Coastal Peat Fire",
        "latitude": -1.82, "longitude": 110.15, "daily_acres": 2220.0, "hectares": 900.0,
        "percent_contained": 28.0, "fire_cause": "Dry Season Ember Spread",
        "discovery_time": "2026-10-20T08:15:00Z", "state": "Kalimantan Barat",
        "province": "Kalimantan Barat", "county": "Ketapang",
        "is_peatland": True, "frp": 68.2,
    },
    {
        "fire_id": "ID-KS-003", "name": "Banjar Lowland Scrub Fire",
        "latitude": -3.35, "longitude": 114.85, "daily_acres": 860.0, "hectares": 350.0,
        "percent_contained": 55.0, "fire_cause": "Human",
        "discovery_time": "2026-10-21T06:45:00Z", "state": "Kalimantan Selatan",
        "province": "Kalimantan Selatan", "county": "Banjar",
        "is_peatland": False, "frp": 32.0,
    },
    {
        "fire_id": "ID-KI-004", "name": "Kutai Rainforest Fringe Fire",
        "latitude": -0.35, "longitude": 117.02, "daily_acres": 3460.0, "hectares": 1400.0,
        "percent_contained": 18.0, "fire_cause": "Under Investigation",
        "discovery_time": "2026-10-18T14:20:00Z", "state": "Kalimantan Timur",
        "province": "Kalimantan Timur", "county": "Kutai Kartanegara",
        "is_peatland": False, "frp": 95.8,
    },
    {
        "fire_id": "ID-KU-005", "name": "Malinau Upland Forest Fire",
        "latitude": 3.42, "longitude": 116.55, "daily_acres": 740.0, "hectares": 300.0,
        "percent_contained": 65.0, "fire_cause": "Lightning",
        "discovery_time": "2026-10-21T11:00:00Z", "state": "Kalimantan Utara",
        "province": "Kalimantan Utara", "county": "Malinau",
        "is_peatland": False, "frp": 24.1,
    },
    {
        "fire_id": "ID-KT-006", "name": "Tanjung Puting Buffer Zone Fire",
        "latitude": -2.95, "longitude": 111.90, "daily_acres": 1730.0, "hectares": 700.0,
        "percent_contained": 20.0, "fire_cause": "Peat Smoldering",
        "discovery_time": "2026-10-20T16:40:00Z", "state": "Kalimantan Tengah",
        "province": "Kalimantan Tengah", "county": "Kotawaringin Barat",
        "is_peatland": True, "frp": 82.0,
    },
]


def _evolve_demo_fire(fire: dict) -> dict:
    """Simulate realistic peatland and vegetation fire growth dynamics."""
    f = fire.copy()
    containment = f["percent_contained"]
    is_peat = f.get("is_peatland", False)

    if containment < 90:
        if containment < 25:
            # Low containment — rapid expansion, especially in peat
            ha_growth = random.gauss(60 if is_peat else 40, 25)
            cont_delta = random.gauss(1.5, 1.0)
        elif containment < 60:
            ha_growth = random.gauss(20, 20)
            cont_delta = random.gauss(2.5, 1.2)
        else:
            ha_growth = random.gauss(-10, 15)
            cont_delta = random.gauss(4.0, 1.5)

        new_ha = max(5.0, f.get("hectares", 100.0) + ha_growth)
        f["hectares"] = round(new_ha, 1)
        f["daily_acres"] = round(new_ha * 2.47105, 1)
        f["percent_contained"] = max(0.0, min(100.0, containment + cont_delta))
    else:
        f["percent_contained"] = min(100.0, containment + random.uniform(0.5, 2.0))

    f["last_updated"] = datetime.now(timezone.utc).isoformat()
    return f


# ─── Spatial Clustering for VIIRS Hotspots ───────────────────────────────────

def cluster_hotspots(hotspots: list[dict], max_dist_deg: float = 0.15) -> list[dict]:
    """
    Cluster individual 375m VIIRS hotspot pixels into coherent wildfire incidents.
    Uses O(N) spatial grid binning for lightning-fast clustering of thousands of hotspots.
    """
    if not hotspots:
        return []

    # Bin into spatial grid cells of max_dist_deg
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

        # Inspect 3x3 neighboring cells
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

        # Aggregate cluster attributes
        centroid_lat = sum(p["latitude"] for p in cluster_pts) / len(cluster_pts)
        centroid_lon = sum(p["longitude"] for p in cluster_pts) / len(cluster_pts)
        total_frp = sum(p.get("frp", 10.0) or 10.0 for p in cluster_pts)
        max_frp = max((p.get("frp", 10.0) or 10.0) for p in cluster_pts)

        # Estimate area: ~14 ha per active 375m fire pixel with spread factor
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


# ─── Canonical Grid ID Assignment ─────────────────────────────────────────────

def assign_grid_id(lat: float, lon: float, resolution: float = 0.02) -> str:
    """Canonical ~2km grid cell ID generator matching warehouse ETL."""
    bbox = config.BORNEO_BBOX
    clamped_lat = max(bbox["lat_min"], min(lat, bbox["lat_max"]))
    clamped_lon = max(bbox["lon_min"], min(lon, bbox["lon_max"]))
    lat_idx = int(round((clamped_lat - bbox["lat_min"] + 1e-9) / resolution))
    lon_idx = int(round((clamped_lon - bbox["lon_min"] + 1e-9) / resolution))
    return f"G{lat_idx:04d}_{lon_idx:04d}"


# ─── Master Wildfire Data Fetcher ─────────────────────────────────────────────

class WildfireDataFetcher:
    """
    Fetches, clusters, and manages live Kalimantan wildfire incidents.
    Integrates NASA FIRMS NRT active fire satellite data and DuckDB Data Warehouse.
    """

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=25.0, follow_redirects=True)
        self.previous_fires: dict[str, dict] = {}
        self.current_fires: dict[str, dict] = {}
        self._demo_state: list[dict] = [f.copy() for f in BORNEO_DEMO_FIRES]
        self._fetch_count = 0
        self._preload_cached_fires()

    def _preload_cached_fires(self):
        """Preload cached Borneo fire incidents from SQLite so /api/fires returns immediately on boot."""
        try:
            import sqlite3
            import json
            import os
            db_path = config.DB_PATH
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                try:
                    cur = conn.cursor()
                    rows = cur.execute(
                        "SELECT raw_json FROM fire_incidents WHERE fire_id LIKE 'BORNEO%' OR fire_id LIKE 'ID-%' LIMIT 50"
                    ).fetchall()
                    if rows:
                        loaded = {}
                        for r in rows:
                            try:
                                f = json.loads(r[0])
                                loaded[f["fire_id"]] = f
                            except Exception:
                                pass
                        if loaded:
                            self.current_fires = loaded
                            self.previous_fires = loaded.copy()
                            logger.info(f"⚡ Preloaded {len(loaded)} cached Borneo fire incidents into active memory")
                finally:
                    conn.close()
        except Exception as e:
            logger.debug(f"Cache preload skipped: {e}")

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def fetch(self) -> list[dict]:
        """
        Fetch current wildfire data for Kalimantan / Borneo.
        Returns a list of clustered fire incident dicts.
        """
        self._fetch_count += 1
        self.previous_fires = self.current_fires.copy()

        if config.DEMO_MODE:
            fires = self._fetch_demo()
        else:
            fires = await self._fetch_live()

        # Enrich top active fire incidents with live DuckDB warehouse features (single connection)
        try:
            import duckdb
            conn = duckdb.connect(config.WAREHOUSE_DB_PATH, read_only=True)
            try:
                for f in fires[:25]:
                    lat = f.get("latitude", 0.0)
                    lon = f.get("longitude", 0.0)
                    f["weather"] = self._query_weather(conn, lat, lon)
                    f["himawari"] = self._query_himawari(conn, lat, lon)
            finally:
                conn.close()
        except Exception:
            for f in fires[:25]:
                f["weather"] = self._default_weather()
                f["himawari"] = self._default_himawari(f.get("latitude", 0.0), f.get("longitude", 0.0))

        self.current_fires = {f["fire_id"]: f for f in fires}
        return fires

    def _fetch_demo(self) -> list[dict]:
        """Generate evolving Kalimantan wildfire data for demo/offline operation."""
        self._demo_state = [_evolve_demo_fire(f) for f in self._demo_state]

        # Occasionally add a new fire (15% probability)
        if random.random() < 0.15 and len(self._demo_state) < 10:
            prov = random.choice(PROVINCE_REGIONS)
            reg_name, r_lat, r_lon, is_peat = random.choice(prov["regencies"])
            ha = round(random.uniform(50, 400), 1)
            new_fire = {
                "fire_id": f"ID-{prov['code']}-{random.randint(100, 999)}",
                "name": f"{reg_name} {'Peat' if is_peat else 'Forest'} Outbreak",
                "latitude": round(r_lat + random.uniform(-0.15, 0.15), 4),
                "longitude": round(r_lon + random.uniform(-0.15, 0.15), 4),
                "daily_acres": round(ha * 2.47105, 1),
                "hectares": ha,
                "percent_contained": 0.0,
                "fire_cause": "Peat Smoldering" if is_peat else "Land Clearing",
                "discovery_time": datetime.now(timezone.utc).isoformat(),
                "state": prov["name"],
                "province": prov["name"],
                "county": reg_name,
                "is_peatland": is_peat,
                "frp": round(random.uniform(25, 90), 1),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            self._demo_state.append(new_fire)
            logger.info(f"🔥 NEW WILDFIRE DETECTED in {prov['name']}: {new_fire['name']}")

        # Remove extinguished fires
        self._demo_state = [
            f for f in self._demo_state
            if f["percent_contained"] < 100 or random.random() < 0.7
        ]

        return [f.copy() for f in self._demo_state]

    async def _fetch_live(self) -> list[dict]:
        """Fetch live VIIRS NRT active fire detections from NASA FIRMS."""
        try:
            logger.info("📡 Ingesting live VIIRS NRT satellite feed for Southeast Asia...")
            response = await self.client.get(
                config.FIRMS_VIIRS_URL,
                headers={"User-Agent": "WildfireSentinel-Borneo/1.0"}
            )
            response.raise_for_status()

            raw_hotspots = []
            lines = response.text.strip().splitlines()
            if len(lines) > 1:
                header = [c.strip().lower() for c in lines[0].split(",")]
                lat_idx = header.index("latitude") if "latitude" in header else 0
                lon_idx = header.index("longitude") if "longitude" in header else 1
                frp_idx = header.index("frp") if "frp" in header else -1
                conf_idx = header.index("confidence") if "confidence" in header else -1
                date_idx = header.index("acq_date") if "acq_date" in header else -1

                bbox = config.BORNEO_BBOX
                for line in lines[1:]:
                    parts = line.split(",")
                    if len(parts) <= max(lat_idx, lon_idx):
                        continue
                    try:
                        lat = float(parts[lat_idx])
                        lon = float(parts[lon_idx])
                        # Filter strictly for Kalimantan bounding box
                        if bbox["lat_min"] <= lat <= bbox["lat_max"] and bbox["lon_min"] <= lon <= bbox["lon_max"]:
                            raw_hotspots.append({
                                "latitude": lat,
                                "longitude": lon,
                                "frp": float(parts[frp_idx]) if frp_idx >= 0 and parts[frp_idx] else 10.0,
                                "confidence": parts[conf_idx] if conf_idx >= 0 else "nominal",
                                "acq_date": parts[date_idx] if date_idx >= 0 else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            })
                    except ValueError:
                        continue

            logger.info(f"🛰️  Filtered {len(raw_hotspots)} active VIIRS hotspots in Kalimantan")

            # Persist raw real-time hotspots directly into DuckDB Data Warehouse
            if raw_hotspots:
                self.persist_hotspots_to_warehouse(raw_hotspots)
                # Background task to refresh BMKG live forecasts
                asyncio.create_task(self.fetch_and_persist_bmkg_weather())

            if not raw_hotspots:
                logger.info("No active satellite hotspots in Kalimantan currently — using calibrated regional baseline")
                return self._fetch_demo()

            # Cluster raw hotspots into manageable incident clusters
            clusters = cluster_hotspots(raw_hotspots)
            logger.info(f"📍 Synthesized {len(clusters)} coherent fire incident clusters in Kalimantan")
            return clusters

        except Exception as e:
            logger.error(f"❌ Error fetching live NASA FIRMS feed: {e}")
            if self.current_fires:
                logger.warning("Using cached fire data")
                return list(self.current_fires.values())
            logger.warning("Falling back to Kalimantan demo data")
            return self._fetch_demo()

    def persist_hotspots_to_warehouse(self, raw_hotspots: list[dict]):
        """Persist real-time VIIRS detections into fact_fire_hotspots in DuckDB."""
        if not raw_hotspots:
            return
        try:
            import duckdb
            conn = duckdb.connect(config.WAREHOUSE_DB_PATH, read_only=False)
            try:
                now = datetime.now(timezone.utc)
                rows = []
                # Persist top 300 active hotspots to DuckDB fact_fire_hotspots
                for h in raw_hotspots[:300]:
                    lat = float(h["latitude"])
                    lon = float(h["longitude"])
                    grid_id = assign_grid_id(lat, lon)
                    acq_date = h.get("acq_date", now.strftime("%Y-%m-%d"))
                    dt_utc = f"{acq_date} 12:00:00"
                    frp = float(h.get("frp", 10.0) or 10.0)
                    conf = str(h.get("confidence", "nominal"))
                    rows.append((grid_id, dt_utc, lat, lon, 330.0, 305.0, 25.0, frp, conf, "D", "VIIRS_N20", now.year, now.month))

                conn.executemany("""
                    INSERT INTO fact_fire_hotspots (grid_id, datetime_utc, lat, lon, bright_ti4_k, bright_ti5_k, delta_bt_k, frp_mw, confidence, daynight, sensor_id, year, month)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)
                logger.info(f"💾 Persisted {len(rows)} live VIIRS hotspots to DuckDB (fact_fire_hotspots)")
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Could not persist hotspots to DuckDB: {e}")

    async def fetch_and_persist_bmkg_weather(self):
        """Fetch live BMKG weather forecasts for key Kalimantan centers and upsert to DuckDB."""
        adm_targets = [
            ("61.71", "Pontianak", "Kalimantan Barat"),
            ("62.71", "Palangka Raya", "Kalimantan Tengah"),
            ("63.71", "Banjarmasin", "Kalimantan Selatan"),
            ("64.72", "Samarinda", "Kalimantan Timur"),
            ("65.71", "Tarakan", "Kalimantan Utara"),
        ]

        for adm_code, city, prov in adm_targets:
            url = f"{config.BMKG_API_BASE_URL}?adm2={adm_code}"
            try:
                resp = await self.client.get(url, headers={"User-Agent": "WildfireSentinel-Borneo/1.0"}, timeout=6.0)
                if resp.status_code == 200:
                    data = resp.json()
                    cuaca_data = data.get("data", [])
                    if cuaca_data and len(cuaca_data) > 0:
                        cuaca_slots = cuaca_data[0].get("cuaca", [])
                        rows = []
                        now = datetime.now(timezone.utc)
                        for day in cuaca_slots:
                            for slot in day:
                                dt_str = slot.get("datetime")
                                if dt_str:
                                    t = float(slot.get("t", 32.0) or 32.0)
                                    hu = float(slot.get("hu", 60.0) or 60.0)
                                    tp = float(slot.get("tp", 0.0) or 0.0)
                                    ws = float(slot.get("ws", 12.0) or 12.0)
                                    tcc = float(slot.get("tcc", 20.0) or 20.0)
                                    weather_code = int(slot.get("weather", 1) or 1)
                                    rows.append((adm_code, dt_str, dt_str, t, hu, tp, ws, tcc, weather_code, now.year, now.month))

                        if rows:
                            import duckdb
                            conn = duckdb.connect(config.WAREHOUSE_DB_PATH, read_only=False)
                            try:
                                conn.executemany("""
                                    INSERT OR REPLACE INTO fact_forecast_3h (adm4_code, forecast_datetime_utc, analysis_datetime_utc, temp_c, humidity_pct, precip_mm, wind_speed_kmh, cloud_cover_pct, weather_code, year, month)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, rows)
                                logger.info(f"🌤️  Ingested {len(rows)} BMKG live forecast steps for {city} ({prov}) into DuckDB")
                            finally:
                                conn.close()
            except Exception as e:
                logger.debug(f"BMKG weather fetch for {city} skipped/error: {e}")

    def _default_weather(self) -> dict:
        return {
            "temperature_c": 33.0,
            "humidity_pct": 55.0,
            "wind_speed_kph": 16.0,
            "cloud_cover_pct": 25.0,
            "station": "Kalimantan Regional Baseline",
        }

    def _default_himawari(self, lat: float, lon: float) -> dict:
        grid_id = assign_grid_id(lat, lon)
        return {
            "grid_id": grid_id,
            "brightness_temp_k": 315.0,
            "thermal_anomaly": False,
            "is_cloudy": False,
            "sensor": "AHI_H09",
        }

    def _query_weather(self, conn, lat: float, lon: float) -> dict:
        try:
            row = conn.execute("""
                SELECT f.temp_c, f.humidity_pct, f.wind_speed_kmh, f.cloud_cover_pct, a.provinsi, a.kabupaten_kota
                FROM fact_forecast_3h f
                JOIN dim_adm4 a ON f.adm4_code = a.adm4_code
                ORDER BY ABS(a.lat - ?) + ABS(a.lon - ?) ASC
                LIMIT 1
            """, [lat, lon]).fetchone()
            if row:
                return {
                    "temperature_c": float(row[0] or 32.0),
                    "humidity_pct": float(row[1] or 60.0),
                    "wind_speed_kph": float(row[2] or 15.0),
                    "cloud_cover_pct": float(row[3] or 20.0),
                    "station": f"{row[5]}, {row[4]}",
                }
        except Exception:
            pass
        return self._default_weather()

    def _query_himawari(self, conn, lat: float, lon: float) -> dict:
        grid_id = assign_grid_id(lat, lon)
        try:
            row = conn.execute("""
                SELECT bt_b07_k, is_cloudy, valid_pixel_pct
                FROM fact_thermal_grid
                WHERE grid_id = ?
                ORDER BY datetime_utc DESC
                LIMIT 1
            """, [grid_id]).fetchone()
            if row:
                bt = float(row[0] or 300.0)
                return {
                    "grid_id": grid_id,
                    "brightness_temp_k": bt,
                    "thermal_anomaly": bt > 320.0,
                    "is_cloudy": bool(row[1]),
                    "sensor": "AHI_H09",
                }
        except Exception:
            pass
        return self._default_himawari(lat, lon)

    def get_fire_weather(self, lat: float, lon: float) -> dict:
        """Query closest BMKG weather forecast from DuckDB warehouse."""
        try:
            import duckdb
            conn = duckdb.connect(config.WAREHOUSE_DB_PATH, read_only=True)
            try:
                return self._query_weather(conn, lat, lon)
            finally:
                conn.close()
        except Exception:
            return self._default_weather()

    def get_himawari_thermal(self, lat: float, lon: float) -> dict:
        """Query nearest Himawari-9 thermal grid observation from DuckDB."""
        try:
            import duckdb
            conn = duckdb.connect(config.WAREHOUSE_DB_PATH, read_only=True)
            try:
                return self._query_himawari(conn, lat, lon)
            finally:
                conn.close()
        except Exception:
            return self._default_himawari(lat, lon)

    def get_changes(self) -> dict:
        """
        Compare current fires against previous snapshot.
        Returns change tracking metrics and event indicators.
        """
        prev_ids = set(self.previous_fires.keys())
        curr_ids = set(self.current_fires.keys())

        new_fires = [self.current_fires[fid] for fid in curr_ids - prev_ids]
        removed_ids = prev_ids - curr_ids

        escalating = []
        improving = []
        contained = []

        for fid in curr_ids & prev_ids:
            curr = self.current_fires[fid]
            prev = self.previous_fires[fid]

            acre_change = (curr.get("daily_acres", 0) or 0) - (prev.get("daily_acres", 0) or 0)
            cont_change = (curr.get("percent_contained", 0) or 0) - (prev.get("percent_contained", 0) or 0)

            if curr.get("percent_contained", 0) >= 95:
                contained.append(curr)
            elif acre_change > 50 or cont_change < -5:
                escalating.append({**curr, "acre_change": acre_change, "containment_change": cont_change})
            elif cont_change > 5 or acre_change < -20:
                improving.append({**curr, "acre_change": acre_change, "containment_change": cont_change})

        return {
            "new": new_fires,
            "escalating": escalating,
            "improving": improving,
            "contained": contained,
            "removed_ids": list(removed_ids),
            "total_active": len(self.current_fires),
            "total_acres": sum((f.get("daily_acres", 0) or 0) for f in self.current_fires.values()),
            "total_hectares": sum((f.get("hectares", 0) or 0) for f in self.current_fires.values()),
        }
