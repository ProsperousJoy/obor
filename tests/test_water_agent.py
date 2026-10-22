"""Unit tests for WaterResourceAgent distance decay and selection."""

import unittest
from src.agents.water_agent import WaterResourceAgent


class TestWaterResourceAgent(unittest.TestCase):
    """Verifies that water suitability avoids distant cross-province misallocations."""

    def setUp(self):
        self.agent = WaterResourceAgent()

    def test_local_source_prioritization(self):
        """
        A fire in Kotawaringin Timur (Central Kalimantan) must allocate Danau Sembuluh
        (local, ~84km) over distant sources like Sungai Kapuas Hulu (>390km).
        """
        fire_lat = -2.53
        fire_lon = 112.95
        result = self.agent.recommend_water_source("INC-TEST-001", fire_lat, fire_lon)

        self.assertIn("recommended_water_source", result)
        source_name = result["recommended_water_source"]

        # Ensure the selected source is geographically local (< 100km)
        self.assertLess(result["distance_km"], 100.0, f"Selected water source {source_name} is too far: {result['distance_km']} km")
        self.assertIn(source_name, ["Sungai Mentaya", "Danau Sembuluh"])
        self.assertGreater(result["water_suitability"], 0.3)


if __name__ == "__main__":
    unittest.main()
