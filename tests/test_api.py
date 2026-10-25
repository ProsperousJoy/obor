"""Integration tests for FastAPI REST endpoints."""

import unittest
from fastapi.testclient import TestClient
from src.api.app import app


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

    def test_api_warehouse_sync(self):
        resp_status = self.client.get("/api/warehouse/sync/status")
        self.assertEqual(resp_status.status_code, 200)
        self.assertIn("status", resp_status.json())

        resp_sync = self.client.post("/api/warehouse/sync")
        self.assertEqual(resp_sync.status_code, 200)
        self.assertEqual(resp_sync.json().get("status"), "success")

    def test_api_jev(self):
        resp = self.client.get("/api/jev")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("enabled", data)
        self.assertIn("last_decision", data)
        self.assertIsNotNone(data["last_decision"])
        decision = data["last_decision"]
        self.assertIn("is_immediate_threat", decision)
        self.assertIn("requires_emergency_dispatch", decision)
        self.assertIn("avf_override_recommended", decision)
        self.assertIn("recommended_response_level", decision)
        self.assertIn("overall_severity_score", decision)

    def test_api_predictions(self):
        resp = self.client.get("/api/predictions")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("analysis", data)

    def test_api_prediction_top_risk(self):
        resp = self.client.get("/api/prediction/top-risk?limit=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("top_risk_cells", data)
        self.assertIn("count", data)
        self.assertIsInstance(data["top_risk_cells"], list)
        if data["top_risk_cells"]:
            cell = data["top_risk_cells"][0]
            self.assertIn("grid_id", cell)
            self.assertIn("calibrated_risk", cell)
            self.assertIn("risk_tier", cell)
            self.assertIn("estimated_eta", cell)

    def test_api_prediction_heatmap(self):
        resp = self.client.get("/api/prediction/heatmap?limit=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("type"), "FeatureCollection")
        self.assertIn("features", data)
        self.assertIsInstance(data["features"], list)

    def test_api_prediction_benchmark(self):
        resp = self.client.get("/api/prediction/benchmark")
        self.assertIn(resp.status_code, [200, 404])

    def test_api_actions(self):
        resp = self.client.get("/api/actions")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("actions", resp.json())

    def test_api_warehouse_assets(self):
        resp = self.client.get("/api/warehouse/assets")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("assets", data)
        self.assertGreaterEqual(len(data["assets"]), 5)


if __name__ == "__main__":
    unittest.main()
