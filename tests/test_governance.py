"""Unit tests for the Governance Engine (Agent Viability Framework)."""

import unittest
from governance import GovernanceEngine, AlertLevel, GovernanceSnapshot


class TestAVFGovernance(unittest.TestCase):
    """Verifies AVF mathematical invariants and monotonic restrictions."""

    def setUp(self):
        self.engine = GovernanceEngine()

    def test_alert_level_monotonicity(self):
        """P3 invariant: Alert level values must increase strictly monotonically."""
        self.assertLess(AlertLevel.MONITOR, AlertLevel.WATCH)
        self.assertLess(AlertLevel.WATCH, AlertLevel.WARNING)
        self.assertLess(AlertLevel.WARNING, AlertLevel.EMERGENCY)

    def test_alert_level_from_string(self):
        self.assertEqual(AlertLevel.from_string("warning"), AlertLevel.WARNING)
        self.assertEqual(AlertLevel.from_string("UNKNOWN"), AlertLevel.MONITOR)

    def test_governance_weights_sum_to_one(self):
        """Weights w1 + w2 + w3 must sum to 1.0."""
        total_w = self.engine.w1 + self.engine.w2 + self.engine.w3
        self.assertAlmostEqual(total_w, 1.0, places=4)

    def test_viability_index_bounds_and_positivity(self):
        """VI(t) must be bounded in [-1.0, 1.0] and positive under healthy conditions."""
        mock_fires = [
            {
                "fire_id": f"FIRE-{i:03d}",
                "name": f"Borneo Incident {i}",
                "latitude": -2.2 + (i * 0.05),
                "longitude": 113.9 + (i * 0.05),
                "daily_acres": 150.0 + (i * 10),
                "percent_contained": 45.0,
                "province": "Kalimantan Tengah",
                "alert_level": "MONITOR"
            }
            for i in range(10)
        ]
        mock_changes = {
            "new": [mock_fires[0]],
            "escalating": [],
            "resolved": [],
            "total_acres": 1500.0
        }

        snapshot = self.engine.evaluate(mock_fires, mock_changes)
        self.assertIsInstance(snapshot, GovernanceSnapshot)
        self.assertGreaterEqual(snapshot.viability_index, -1.0)
        self.assertLessEqual(snapshot.viability_index, 1.0)
        self.assertGreater(snapshot.viability_index, 0.0, "Viability index should be positive under standard baseline")
        self.assertGreaterEqual(snapshot.c1_safety, -1.0)
        self.assertLessEqual(snapshot.c1_safety, 1.0)
        self.assertGreaterEqual(snapshot.c2_fairness, -1.0)
        self.assertLessEqual(snapshot.c2_fairness, 1.0)
        self.assertGreaterEqual(snapshot.c3_stability, -1.0)
        self.assertLessEqual(snapshot.c3_stability, 1.0)


if __name__ == "__main__":
    unittest.main()
