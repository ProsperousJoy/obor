"""Integration tests for FastAPI REST endpoints."""

import unittest
from fastapi.testclient import TestClient
from server import app


class TestAPIEndpoints(unittest.TestCase):
    """Verifies all core REST endpoints return 200 OK and valid schemas."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "healthy")

    def test_api_fires(self):
        resp = self.client.get("/api/fires")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("fires", data)
        self.assertIn("count", data)

    def test_api_viability(self):
        resp = self.client.get("/api/viability")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("viability_index", data)
        self.assertIn("c1_safety", data)

    def test_api_dispatches(self):
        resp = self.client.get("/api/dispatches")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("dispatches", data)

    def test_api_warehouse_hqs(self):
        resp = self.client.get("/api/warehouse/hqs")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("hqs", data)
        self.assertGreaterEqual(len(data["hqs"]), 12)

    def test_api_warehouse_water_sources(self):
        resp = self.client.get("/api/warehouse/water-sources")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("water_sources", data)
        self.assertGreaterEqual(len(data["water_sources"]), 8)


if __name__ == "__main__":
    unittest.main()
