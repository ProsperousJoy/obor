"""
Warehouse Synchronization Bridge (SQLite Operational -> DuckDB OLAP)
---------------------------------------------------------------------
Feeds transactional operational agent data (governance state, fire snapshots,
Jev cognitive decisions, and dispatch actions) into the DuckDB analytical
data warehouse on an hourly schedule or on-demand.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import duckdb

from src.config import config

logger = logging.getLogger("wildfire.storage.sync")


def _to_dt(epoch_val: Any) -> Optional[datetime]:
    if epoch_val is None:
        return None
    try:
        if isinstance(epoch_val, (int, float)):
            return datetime.fromtimestamp(epoch_val)
        if isinstance(epoch_val, str):
            try:
                return datetime.fromtimestamp(float(epoch_val))
            except ValueError:
                return datetime.fromisoformat(epoch_val.replace("Z", "+00:00"))
        return epoch_val
    except Exception:
        return None


class WarehouseSyncBridge:
    """
    Synchronizes operational SQLite records to analytical DuckDB warehouse tables.
    """

    def __init__(
        self,
        sqlite_path: Optional[str] = None,
        duckdb_path: Optional[str] = None,
    ):
        self.sqlite_path = sqlite_path or config.DB_PATH
        self.duckdb_path = duckdb_path or config.WAREHOUSE_DB_PATH

    def initialize_warehouse_tables(self, conn: duckdb.DuckDBPyConnection):
        """Ensure destination analytical sync tables exist in DuckDB."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _sync_checkpoints (
                table_name VARCHAR PRIMARY KEY,
                last_synced_id BIGINT,
                last_synced_timestamp TIMESTAMP,
                total_records_synced BIGINT DEFAULT 0,
                last_run_at TIMESTAMP
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fact_governance_snapshots (
                id BIGINT PRIMARY KEY,
                timestamp TIMESTAMP,
                viability_index DOUBLE,
                c1_safety DOUBLE,
                c2_fairness DOUBLE,
                c3_stability DOUBLE,
                t_star DOUBLE,
                active_fires_count INTEGER,
                total_acres DOUBLE,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fact_jev_decisions (
                id BIGINT PRIMARY KEY,
                timestamp TIMESTAMP,
                is_immediate_threat DOUBLE,
                requires_emergency_dispatch DOUBLE,
                avf_override_recommended DOUBLE,
                recommended_response_level VARCHAR,
                response_level_confidence DOUBLE,
                overall_severity_score DOUBLE,
                severity_confidence DOUBLE,
                latency_ms DOUBLE,
                raw_response VARCHAR,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fact_operational_dispatches (
                id BIGINT PRIMARY KEY,
                timestamp TIMESTAMP,
                action_type VARCHAR,
                fire_id VARCHAR,
                description VARCHAR,
                details VARCHAR,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fact_operational_fire_snapshots (
                id BIGINT PRIMARY KEY,
                fire_id VARCHAR,
                timestamp TIMESTAMP,
                daily_acres DOUBLE,
                percent_contained DOUBLE,
                alert_level VARCHAR,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

    def sync_governance_state(
        self, sqlite_cur: sqlite3.Cursor, duck_conn: duckdb.DuckDBPyConnection
    ) -> int:
        """Syncs governance_state rows from SQLite to DuckDB."""
        checkpoint = duck_conn.execute(
            "SELECT last_synced_id FROM _sync_checkpoints WHERE table_name = 'governance_state'"
        ).fetchone()
        last_id = checkpoint[0] if checkpoint and checkpoint[0] is not None else 0

        rows = sqlite_cur.execute(
            """
            SELECT id, timestamp, viability_index, c1_safety, c2_fairness, c3_stability, t_star, active_fires_count, total_acres
            FROM governance_state
            WHERE id > ?
            ORDER BY id ASC
            """,
            (last_id,),
        ).fetchall()

        if not rows:
            return 0

        converted_rows = [
            (r[0], _to_dt(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8])
            for r in rows
        ]

        duck_conn.executemany(
            """
            INSERT OR REPLACE INTO fact_governance_snapshots (
                id, timestamp, viability_index, c1_safety, c2_fairness, c3_stability, t_star, active_fires_count, total_acres
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            converted_rows,
        )

        max_id = max(r[0] for r in rows)
        duck_conn.execute(
            """
            INSERT INTO _sync_checkpoints (table_name, last_synced_id, total_records_synced, last_run_at)
            VALUES ('governance_state', ?, ?, now())
            ON CONFLICT (table_name) DO UPDATE SET
                last_synced_id = excluded.last_synced_id,
                total_records_synced = _sync_checkpoints.total_records_synced + excluded.total_records_synced,
                last_run_at = now()
            """,
            (max_id, len(rows)),
        )
        return len(rows)

    def sync_jev_decisions(
        self, sqlite_cur: sqlite3.Cursor, duck_conn: duckdb.DuckDBPyConnection
    ) -> int:
        """Syncs jev_decisions rows from SQLite to DuckDB."""
        checkpoint = duck_conn.execute(
            "SELECT last_synced_id FROM _sync_checkpoints WHERE table_name = 'jev_decisions'"
        ).fetchone()
        last_id = checkpoint[0] if checkpoint and checkpoint[0] is not None else 0

        rows = sqlite_cur.execute(
            """
            SELECT id, timestamp, is_immediate_threat, requires_emergency_dispatch,
                   avf_override_recommended, recommended_response_level, response_level_confidence,
                   overall_severity_score, severity_confidence, latency_ms, raw_response
            FROM jev_decisions
            WHERE id > ?
            ORDER BY id ASC
            """,
            (last_id,),
        ).fetchall()

        if not rows:
            return 0

        converted_rows = [
            (r[0], _to_dt(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10])
            for r in rows
        ]

        duck_conn.executemany(
            """
            INSERT OR REPLACE INTO fact_jev_decisions (
                id, timestamp, is_immediate_threat, requires_emergency_dispatch,
                avf_override_recommended, recommended_response_level, response_level_confidence,
                overall_severity_score, severity_confidence, latency_ms, raw_response
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            converted_rows,
        )

        max_id = max(r[0] for r in rows)
        duck_conn.execute(
            """
            INSERT INTO _sync_checkpoints (table_name, last_synced_id, total_records_synced, last_run_at)
            VALUES ('jev_decisions', ?, ?, now())
            ON CONFLICT (table_name) DO UPDATE SET
                last_synced_id = excluded.last_synced_id,
                total_records_synced = _sync_checkpoints.total_records_synced + excluded.total_records_synced,
                last_run_at = now()
            """,
            (max_id, len(rows)),
        )
        return len(rows)

    def sync_agent_actions(
        self, sqlite_cur: sqlite3.Cursor, duck_conn: duckdb.DuckDBPyConnection
    ) -> int:
        """Syncs agent_actions (dispatches & governance interventions) from SQLite to DuckDB."""
        checkpoint = duck_conn.execute(
            "SELECT last_synced_id FROM _sync_checkpoints WHERE table_name = 'agent_actions'"
        ).fetchone()
        last_id = checkpoint[0] if checkpoint and checkpoint[0] is not None else 0

        rows = sqlite_cur.execute(
            """
            SELECT id, timestamp, action_type, fire_id, description, details
            FROM agent_actions
            WHERE id > ?
            ORDER BY id ASC
            """,
            (last_id,),
        ).fetchall()

        if not rows:
            return 0

        converted_rows = [
            (r[0], _to_dt(r[1]), r[2], r[3], r[4], r[5])
            for r in rows
        ]

        duck_conn.executemany(
            """
            INSERT OR REPLACE INTO fact_operational_dispatches (
                id, timestamp, action_type, fire_id, description, details
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            converted_rows,
        )

        max_id = max(r[0] for r in rows)
        duck_conn.execute(
            """
            INSERT INTO _sync_checkpoints (table_name, last_synced_id, total_records_synced, last_run_at)
            VALUES ('agent_actions', ?, ?, now())
            ON CONFLICT (table_name) DO UPDATE SET
                last_synced_id = excluded.last_synced_id,
                total_records_synced = _sync_checkpoints.total_records_synced + excluded.total_records_synced,
                last_run_at = now()
            """,
            (max_id, len(rows)),
        )
        return len(rows)

    def sync_fire_snapshots(
        self, sqlite_cur: sqlite3.Cursor, duck_conn: duckdb.DuckDBPyConnection, limit: int = 2500
    ) -> int:
        """Syncs fire_snapshots from SQLite to DuckDB in incremental chunks."""
        checkpoint = duck_conn.execute(
            "SELECT last_synced_id FROM _sync_checkpoints WHERE table_name = 'fire_snapshots'"
        ).fetchone()
        last_id = checkpoint[0] if checkpoint and checkpoint[0] is not None else 0

        rows = sqlite_cur.execute(
            """
            SELECT id, fire_id, timestamp, daily_acres, percent_contained, alert_level
            FROM fire_snapshots
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (last_id, limit),
        ).fetchall()

        if not rows:
            return 0

        converted_rows = [
            (r[0], r[1], _to_dt(r[2]), r[3], r[4], r[5])
            for r in rows
        ]

        duck_conn.executemany(
            """
            INSERT OR IGNORE INTO fact_operational_fire_snapshots (
                id, fire_id, timestamp, daily_acres, percent_contained, alert_level
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            converted_rows,
        )

        max_id = max(r[0] for r in rows)
        duck_conn.execute(
            """
            INSERT INTO _sync_checkpoints (table_name, last_synced_id, total_records_synced, last_run_at)
            VALUES ('fire_snapshots', ?, ?, now())
            ON CONFLICT (table_name) DO UPDATE SET
                last_synced_id = excluded.last_synced_id,
                total_records_synced = _sync_checkpoints.total_records_synced + excluded.total_records_synced,
                last_run_at = now()
            """,
            (max_id, len(rows)),
        )
        return len(rows)

    def run_sync(self) -> Dict[str, Any]:
        """
        Executes an incremental sync pass from SQLite to DuckDB warehouse.
        """
        if not Path(self.sqlite_path).exists():
            return {
                "status": "skipped",
                "message": f"SQLite database {self.sqlite_path} does not exist yet.",
                "synced": 0,
            }

        start_time = datetime.utcnow()
        logger.info(f"🔄 Starting Warehouse Sync: {self.sqlite_path} -> {self.duckdb_path}")

        sqlite_conn = sqlite3.connect(self.sqlite_path)
        duck_conn = duckdb.connect(self.duckdb_path, read_only=False)

        try:
            self.initialize_warehouse_tables(duck_conn)
            c = sqlite_conn.cursor()

            gov_count = self.sync_governance_state(c, duck_conn)
            jev_count = self.sync_jev_decisions(c, duck_conn)
            action_count = self.sync_agent_actions(c, duck_conn)
            snapshot_count = self.sync_fire_snapshots(c, duck_conn)

            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            total_synced = gov_count + jev_count + action_count + snapshot_count

            logger.info(
                f"✅ Warehouse Sync completed in {elapsed_ms:.1f}ms: "
                f"{gov_count} governance, {jev_count} jev, {action_count} actions, {snapshot_count} snapshots"
            )

            return {
                "status": "success",
                "synced_records": {
                    "governance_snapshots": gov_count,
                    "jev_decisions": jev_count,
                    "agent_actions": action_count,
                    "fire_snapshots": snapshot_count,
                    "total": total_synced,
                },
                "elapsed_ms": round(elapsed_ms, 2),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        finally:
            sqlite_conn.close()
            duck_conn.close()

    def get_sync_status(self) -> Dict[str, Any]:
        """Returns the current synchronization status and checkpoints."""
        if not Path(self.duckdb_path).exists():
            return {"status": "uninitialized", "checkpoints": []}

        duck_conn = duckdb.connect(self.duckdb_path, read_only=True)
        try:
            tables = set(duck_conn.execute("SHOW TABLES").df()["name"].tolist())
            if "_sync_checkpoints" not in tables:
                return {"status": "uninitialized", "checkpoints": []}

            rows = duck_conn.execute("""
                SELECT table_name, last_synced_id, 
                       CAST(last_synced_timestamp AS VARCHAR), 
                       total_records_synced, 
                       CAST(last_run_at AS VARCHAR) 
                FROM _sync_checkpoints
            """).fetchall()

            checkpoints = [
                {
                    "table_name": r[0],
                    "last_synced_id": r[1],
                    "last_synced_timestamp": r[2],
                    "total_records_synced": r[3],
                    "last_run_at": r[4],
                }
                for r in rows
            ]
            return {
                "status": "operational",
                "checkpoints": checkpoints,
            }
        finally:
            duck_conn.close()
