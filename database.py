"""
SQLite database layer for the Wildfire Monitoring Agent.
Stores fire incident snapshots, agent actions, alerts, and governance state.
"""

import aiosqlite
import json
import time
from typing import Optional

from config import config

DB_PATH = config.DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fire_incidents (
    fire_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    daily_acres REAL DEFAULT 0,
    percent_contained REAL DEFAULT 0,
    fire_cause TEXT,
    discovery_time TEXT,
    state TEXT,
    county TEXT,
    alert_level TEXT DEFAULT 'MONITOR',
    last_updated TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS fire_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fire_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    daily_acres REAL,
    percent_contained REAL,
    alert_level TEXT,
    FOREIGN KEY (fire_id) REFERENCES fire_incidents(fire_id)
);

CREATE TABLE IF NOT EXISTS agent_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    action_type TEXT NOT NULL,
    fire_id TEXT,
    description TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    fire_id TEXT NOT NULL,
    alert_level TEXT NOT NULL,
    message TEXT,
    dispatched INTEGER DEFAULT 0,
    dispatch_details TEXT
);

CREATE TABLE IF NOT EXISTS governance_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    viability_index REAL NOT NULL,
    c1_safety REAL,
    c2_fairness REAL,
    c3_stability REAL,
    t_star REAL,
    active_fires_count INTEGER,
    total_acres REAL
);

CREATE TABLE IF NOT EXISTS jev_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    is_immediate_threat REAL,
    requires_emergency_dispatch REAL,
    avf_override_recommended REAL,
    recommended_response_level TEXT,
    response_level_confidence REAL,
    overall_severity_score REAL,
    severity_confidence REAL,
    latency_ms REAL,
    raw_response TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_fire ON fire_snapshots(fire_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_actions_time ON agent_actions(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_fire ON alerts(fire_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_governance_time ON governance_state(timestamp);
CREATE INDEX IF NOT EXISTS idx_jev_time ON jev_decisions(timestamp);
"""


async def init_db():
    """Initialize the database with schema."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()


async def upsert_fire(fire: dict):
    """Insert or update a fire incident."""
    await upsert_fires_batch([fire])


async def upsert_fires_batch(fires: list[dict]):
    """Insert or update multiple fire incidents in a single transaction."""
    if not fires:
        return
    rows = [
        (
            fire["fire_id"], fire["name"], fire["latitude"], fire["longitude"],
            fire.get("daily_acres", 0) or 0, fire.get("percent_contained", 0) or 0,
            fire.get("fire_cause"), fire.get("discovery_time"),
            fire.get("state"), fire.get("county"),
            fire.get("alert_level", "MONITOR"), fire.get("last_updated"),
            json.dumps(fire)
        )
        for fire in fires
    ]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """
            INSERT INTO fire_incidents
                (fire_id, name, latitude, longitude, daily_acres, percent_contained,
                 fire_cause, discovery_time, state, county, alert_level, last_updated, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fire_id) DO UPDATE SET
                name=excluded.name,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                daily_acres=excluded.daily_acres,
                percent_contained=excluded.percent_contained,
                fire_cause=excluded.fire_cause,
                last_updated=excluded.last_updated,
                raw_json=excluded.raw_json
            """,
            rows
        )
        await db.commit()


async def update_fire_alert_level(fire_id: str, alert_level: str):
    """Update the alert level for a fire."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE fire_incidents SET alert_level = ? WHERE fire_id = ?",
            (alert_level, fire_id)
        )
        await db.commit()


async def save_snapshot(fire_id: str, daily_acres: float, percent_contained: float, alert_level: str):
    """Save a point-in-time snapshot for trend tracking."""
    await save_snapshots_batch([(fire_id, daily_acres, percent_contained, alert_level)])


async def save_snapshots_batch(snapshots: list[tuple[str, float, float, str]]):
    """Save point-in-time snapshots for multiple fires in a single transaction."""
    if not snapshots:
        return
    now = time.time()
    rows = [
        (fire_id, now, daily_acres, percent_contained, alert_level)
        for fire_id, daily_acres, percent_contained, alert_level in snapshots
    ]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT INTO fire_snapshots (fire_id, timestamp, daily_acres, percent_contained, alert_level) "
            "VALUES (?, ?, ?, ?, ?)",
            rows
        )
        await db.commit()


async def log_action(action_type: str, fire_id: Optional[str], description: str, details: Optional[dict] = None):
    """Log an agent action for audit trail."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO agent_actions (timestamp, action_type, fire_id, description, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (time.time(), action_type, fire_id, description, json.dumps(details) if details else None)
        )
        await db.commit()


async def save_alert(fire_id: str, alert_level: str, message: str, dispatched: bool = False, dispatch_details: Optional[dict] = None):
    """Save an alert record."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO alerts (timestamp, fire_id, alert_level, message, dispatched, dispatch_details) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), fire_id, alert_level, message, int(dispatched),
             json.dumps(dispatch_details) if dispatch_details else None)
        )
        await db.commit()


async def save_governance_state(vi: float, c1: float, c2: float, c3: float,
                                 t_star: Optional[float], active_count: int, total_acres: float):
    """Save a governance state snapshot."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO governance_state "
            "(timestamp, viability_index, c1_safety, c2_fairness, c3_stability, t_star, active_fires_count, total_acres) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), vi, c1, c2, c3, t_star, active_count, total_acres)
        )
        await db.commit()


async def get_all_fires() -> list[dict]:
    """Get all current fire incidents."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM fire_incidents ORDER BY daily_acres DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_fire(fire_id: str) -> Optional[dict]:
    """Get a single fire incident."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM fire_incidents WHERE fire_id = ?", (fire_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_fire_snapshots(fire_id: str, limit: int = 50) -> list[dict]:
    """Get recent snapshots for a fire."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM fire_snapshots WHERE fire_id = ? ORDER BY timestamp DESC LIMIT ?",
            (fire_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_recent_actions(limit: int = 50) -> list[dict]:
    """Get the most recent agent actions."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM agent_actions ORDER BY timestamp DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_recent_alerts(limit: int = 50) -> list[dict]:
    """Get the most recent alerts."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_governance_history(limit: int = 100) -> list[dict]:
    """Get recent governance state history."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM governance_state ORDER BY timestamp DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_recent_dispatches(limit: int = 50) -> list[dict]:
    """Get the most recent emergency dispatches with parsed details."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alerts WHERE dispatched = 1 ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                r = dict(row)
                if r.get("dispatch_details"):
                    try:
                        details = json.loads(r["dispatch_details"])
                        results.append(details)
                    except Exception:
                        results.append(r)
                else:
                    results.append(r)
            return results


async def get_last_dispatch_time(fire_id: str) -> Optional[float]:
    """Get the timestamp of the last dispatch for a fire."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT MAX(timestamp) FROM alerts WHERE fire_id = ? AND dispatched = 1",
            (fire_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None


async def save_jev_decision(decision) -> None:
    """Save a Jev AI supervisor decision snapshot."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO jev_decisions "
            "(timestamp, is_immediate_threat, requires_emergency_dispatch, "
            "avf_override_recommended, recommended_response_level, "
            "response_level_confidence, overall_severity_score, "
            "severity_confidence, latency_ms, raw_response) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                decision.timestamp,
                decision.is_immediate_threat,
                decision.requires_emergency_dispatch,
                decision.avf_override_recommended,
                decision.recommended_response_level,
                decision.response_level_confidence,
                decision.overall_severity_score,
                decision.severity_confidence,
                decision.latency_ms,
                json.dumps(decision.raw_response) if decision.raw_response else None,
            ),
        )
        await db.commit()


async def get_jev_history(limit: int = 50) -> list[dict]:
    """Get recent Jev decision history."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jev_decisions ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

