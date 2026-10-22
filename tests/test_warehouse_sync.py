"""Unit tests for WarehouseSyncBridge (SQLite Operational -> DuckDB OLAP)."""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
import duckdb

from src.storage.sync import WarehouseSyncBridge, _to_dt


class TestWarehouseSync(unittest.TestCase):
    """Verifies incremental ETL synchronization between SQLite and DuckDB."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.sqlite_path = os.path.join(self.tmp_dir.name, "test_operational.db")
        self.duckdb_path = os.path.join(self.tmp_dir.name, "test_warehouse.duckdb")

        # Create mock SQLite schema and data
        conn = sqlite3.connect(self.sqlite_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE governance_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                viability_index REAL,
                c1_safety REAL,
                c2_fairness REAL,
                c3_stability REAL,
                t_star REAL,
                active_fires_count INTEGER,
                total_acres REAL
            )
        """)
        cur.execute("""
            CREATE TABLE jev_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                is_immediate_threat REAL,
                requires_emergency_dispatch REAL,
                avf_override_recommended REAL,
                recommended_response_level TEXT,
                response_level_confidence REAL,
                overall_severity_score REAL,
                severity_confidence REAL,
                latency_ms REAL,
                raw_response TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE agent_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                action_type TEXT,
                fire_id TEXT,
                description TEXT,
                details TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE fire_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fire_id TEXT,
                timestamp REAL,
                daily_acres REAL,
                percent_contained REAL,
                alert_level TEXT
            )
        """)

        # Insert sample rows
        now_ts = 1790000000.0
        cur.execute(
            "INSERT INTO governance_state (timestamp, viability_index, c1_safety, c2_fairness, c3_stability, t_star, active_fires_count, total_acres) VALUES (?, 0.85, 0.8, 0.9, 0.95, 120.0, 5, 1500.0)",
            (now_ts,)
        )
        cur.execute(
            "INSERT INTO jev_decisions (timestamp, is_immediate_threat, requires_emergency_dispatch, avf_override_recommended, recommended_response_level, response_level_confidence, overall_severity_score, severity_confidence, latency_ms, raw_response) VALUES (?, 0.2, 0.7, 0.1, 'WARNING', 0.9, 1.2, 0.8, 350.0, '{}')",
            (now_ts,)
        )
        cur.execute(
            "INSERT INTO agent_actions (timestamp, action_type, fire_id, description, details) VALUES (?, 'DISPATCH', 'FIRE-001', 'Dispatched Manggala Agni', '{}')",
            (now_ts,)
        )
        cur.execute(
            "INSERT INTO fire_snapshots (fire_id, timestamp, daily_acres, percent_contained, alert_level) VALUES ('FIRE-001', ?, 250.0, 30.0, 'WARNING')",
            (now_ts,)
        )
        conn.commit()
        conn.close()

        self.bridge = WarehouseSyncBridge(
            sqlite_path=self.sqlite_path,
            duckdb_path=self.duckdb_path
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_sync_pass_and_checkpoints(self):
        """Verifies initial sync populates DuckDB and tracks checkpoints."""
        result = self.bridge.run_sync()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["synced_records"]["governance_snapshots"], 1)
        self.assertEqual(result["synced_records"]["jev_decisions"], 1)
        self.assertEqual(result["synced_records"]["agent_actions"], 1)
        self.assertEqual(result["synced_records"]["fire_snapshots"], 1)

        # Verify DuckDB records
        conn = duckdb.connect(self.duckdb_path, read_only=True)
        gov_row = conn.execute("SELECT id, viability_index FROM fact_governance_snapshots").fetchone()
        self.assertIsNotNone(gov_row)
        self.assertEqual(gov_row[0], 1)
        self.assertAlmostEqual(gov_row[1], 0.85)

        jev_row = conn.execute("SELECT id, recommended_response_level FROM fact_jev_decisions").fetchone()
        self.assertIsNotNone(jev_row)
        self.assertEqual(jev_row[1], "WARNING")

        action_row = conn.execute("SELECT id, action_type FROM fact_operational_dispatches").fetchone()
        self.assertIsNotNone(action_row)
        self.assertEqual(action_row[1], "DISPATCH")

        snap_row = conn.execute("SELECT id, fire_id FROM fact_operational_fire_snapshots").fetchone()
        self.assertIsNotNone(snap_row)
        self.assertEqual(snap_row[1], "FIRE-001")
        conn.close()

        # Incremental second run should sync 0 records
        second_result = self.bridge.run_sync()
        self.assertEqual(second_result["status"], "success")
        self.assertEqual(second_result["synced_records"]["total"], 0)

    def test_get_sync_status(self):
        """Verifies checkpoint reporting."""
        self.bridge.run_sync()
        status = self.bridge.get_sync_status()
        self.assertEqual(status["status"], "operational")
        checkpoints = {cp["table_name"]: cp["last_synced_id"] for cp in status["checkpoints"]}
        self.assertEqual(checkpoints["governance_state"], 1)
        self.assertEqual(checkpoints["jev_decisions"], 1)
        self.assertEqual(checkpoints["agent_actions"], 1)
        self.assertEqual(checkpoints["fire_snapshots"], 1)


if __name__ == "__main__":
    unittest.main()
