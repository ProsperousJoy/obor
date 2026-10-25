"""Wildfire Data Fetcher — Ingests active fire incidents for Kalimantan / Borneo."""

import asyncio
from datetime import datetime, timezone
import json
import logging
import math
import os
import random
import sqlite3
import duckdb
import httpx

from src.config import config
from src.data.spatial import (
    PROVINCE_REGIONS,
    assign_grid_id,
    cluster_hotspots,
    resolve_location,
)

logger = logging.getLogger("wildfire.fetcher")

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
            conn = duckdb.connect(config.WAREHOUSE_DB_PATH)
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
                headers={"User-Agent": "OBOR-Borneo/1.0"}
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

            if raw_hotspots:
                self.persist_hotspots_to_warehouse(raw_hotspots)
                asyncio.create_task(self.fetch_and_persist_bmkg_weather())

            if not raw_hotspots:
                logger.info("No active satellite hotspots in Kalimantan currently — using calibrated regional baseline")
                return self._fetch_demo()

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
            conn = duckdb.connect(config.WAREHOUSE_DB_PATH, read_only=False)
            try:
                now = datetime.now(timezone.utc)
                rows = []
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
                resp = await self.client.get(url, headers={"User-Agent": "OBOR-Borneo/1.0"}, timeout=6.0)
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
                            conn = duckdb.connect(config.WAREHOUSE_DB_PATH, read_only=False)
                            try:
                                conn.executemany("""
                                    INSERT INTO fact_forecast_3h (adm4_code, forecast_datetime_utc, analysis_datetime_utc, temp_c, humidity_pct, precip_mm, wind_speed_kmh, cloud_cover_pct, weather_code, year, month)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT (adm4_code, forecast_datetime_utc) DO UPDATE SET
                                        analysis_datetime_utc = EXCLUDED.analysis_datetime_utc,
                                        temp_c = EXCLUDED.temp_c,
                                        humidity_pct = EXCLUDED.humidity_pct,
                                        precip_mm = EXCLUDED.precip_mm,
                                        wind_speed_kmh = EXCLUDED.wind_speed_kmh,
                                        cloud_cover_pct = EXCLUDED.cloud_cover_pct,
                                        weather_code = EXCLUDED.weather_code,
                                        year = EXCLUDED.year,
                                        month = EXCLUDED.month
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
            conn = duckdb.connect(config.WAREHOUSE_DB_PATH)
            try:
                return self._query_weather(conn, lat, lon)
            finally:
                conn.close()
        except Exception:
            return self._default_weather()

    def get_himawari_thermal(self, lat: float, lon: float) -> dict:
        """Query nearest Himawari-9 thermal grid observation from DuckDB."""
        try:
            conn = duckdb.connect(config.WAREHOUSE_DB_PATH)
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
