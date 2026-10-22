"""Unit tests for Emergency Dispatcher Daops coordination and persistence."""

import unittest
from emergency_dispatcher import EmergencyDispatcher, MANGGALA_AGNI_DAOPS, STRATEGIC_WATER_SOURCES


class TestEmergencyDispatcher(unittest.TestCase):
    """Verifies official KLHK Daops synchronization and dispatch creation."""

    def setUp(self):
        self.dispatcher = EmergencyDispatcher()

    def test_daops_hq_synchronization(self):
        """All 12 fallback Daops must use the official HQ-MA-* standard schema IDs."""
        self.assertEqual(len(MANGGALA_AGNI_DAOPS), 12)
        valid_prefixes = ("HQ-MA-KT", "HQ-MA-KB", "HQ-MA-KS", "HQ-MA-KI", "HQ-MA-KU")
        for hq in MANGGALA_AGNI_DAOPS:
            self.assertTrue(
                hq["hq_id"].startswith(valid_prefixes),
                f"Invalid Daops HQ ID format: {hq['hq_id']}"
            )

    def test_kotawaringin_barat_present(self):
        """Daops Kotawaringin Barat (HQ-MA-KT-03) must be present in the HQ list."""
        kt03 = [h for h in MANGGALA_AGNI_DAOPS if h["hq_id"] == "HQ-MA-KT-03"]
        self.assertEqual(len(kt03), 1, "HQ-MA-KT-03 Kotawaringin Barat missing from Daops list")

    def test_dispatch_generation(self):
        """A high-risk peatland fire should generate a complete emergency dispatch."""
        mock_fire = {
            "fire_id": "TEST-FIRE-001",
            "name": "Kebakaran Gambut Sebangau",
            "latitude": -2.45,
            "longitude": 114.05,
            "daily_acres": 250.0,
            "percent_contained": 10.0,
            "province": "Kalimantan Tengah",
            "county": "Pulang Pisau",
            "alert_level": "EMERGENCY"
        }
        report = self.dispatcher.dispatch(mock_fire, alert_level="EMERGENCY")
        self.assertIsNotNone(report)
        self.assertEqual(report.fire_id, "TEST-FIRE-001")
        self.assertTrue(report.assigned_hq_id.startswith("HQ-MA-KT") or "Palangka Raya" in report.nearest_station)
        self.assertGreater(len(report.resources_deployed), 0)


if __name__ == "__main__":
    unittest.main()
