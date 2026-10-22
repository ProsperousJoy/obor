"""Unit tests for asynchronous database operations and batching."""

import asyncio
import unittest
import database as db


class TestDatabaseBatch(unittest.IsolatedAsyncioTestCase):
    """Verifies batch upserts and snapshots in SQLite."""

    async def asyncSetUp(self):
        await db.init_db()

    async def test_batch_upsert_and_snapshots(self):
        fires = [
            {
                "fire_id": f"TEST-BATCH-{i:03d}",
                "name": f"Batch Test Fire {i}",
                "latitude": -2.0 + (i * 0.01),
                "longitude": 113.0 + (i * 0.01),
                "daily_acres": 50.0 + i,
                "percent_contained": 20.0 + i,
                "fire_cause": "Human",
                "discovery_time": "2026-10-22 10:00:00",
                "state": "Kalimantan Tengah",
                "county": "Pulang Pisau",
                "alert_level": "WATCH",
                "last_updated": "2026-10-22 10:00:00"
            }
            for i in range(25)
        ]

        # Test batch upsert
        await db.upsert_fires_batch(fires)

        # Verify all fires count
        all_fires = await db.get_all_fires()
        batch_ids = {f["fire_id"] for f in fires}
        persisted = [f for f in all_fires if f["fire_id"] in batch_ids]
        self.assertEqual(len(persisted), 25)

        # Test batch snapshots
        snapshots = [
            (f["fire_id"], f["daily_acres"], f["percent_contained"], f["alert_level"])
            for f in fires
        ]
        await db.save_snapshots_batch(snapshots)

        # Verify snapshots exist
        history = await db.get_fire_snapshots(fires[0]["fire_id"], limit=5)
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["alert_level"], "WATCH")


if __name__ == "__main__":
    unittest.main()
