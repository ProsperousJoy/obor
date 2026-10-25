"""
Low-Token API Endpoint Test.
Verifies /api/status and /api/jev endpoints using FastAPI TestClient (zero external calls).
"""

import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import unittest
from fastapi.testclient import TestClient
from src.api.app import app


class TestLowTokenEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_api_status(self):
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        self.assertIn("has_jev", r.json())
        self.assertIn("status", r.json())

    def test_api_jev(self):
        r = self.client.get("/api/jev")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("enabled", data)
        self.assertIn("last_decision", data)

    def test_api_fires(self):
        r = self.client.get("/api/fires")
        self.assertEqual(r.status_code, 200)
        self.assertIn("fires", r.json())

    def test_api_viability(self):
        r = self.client.get("/api/viability")
        self.assertEqual(r.status_code, 200)
        self.assertIn("viability_index", r.json())


if __name__ == "__main__":
    unittest.main()

