"""
Low-Token API Endpoint Test.
Verifies /api/status and /api/jev endpoints using FastAPI TestClient (zero external calls).
"""

from fastapi.testclient import TestClient
from server import app

client = TestClient(app)

def test_api():
    print("Testing /api/status...")
    r = client.get("/api/status")
    print("Status:", r.status_code)
    print("Response:", r.json())
    assert r.status_code == 200
    assert r.json().get("has_jev") is True

    print("\nTesting /api/jev...")
    r = client.get("/api/jev")
    print("Status:", r.status_code)
    print("Response keys:", list(r.json().keys()))
    assert r.status_code == 200
    assert "enabled" in r.json()
    assert r.json()["enabled"] is True

    print("\nTesting /api/fires...")
    r = client.get("/api/fires")
    print("Status:", r.status_code)
    assert r.status_code == 200

    print("\nTesting /api/viability...")
    r = client.get("/api/viability")
    print("Status:", r.status_code)
    assert r.status_code == 200

    print("\n✅ All API routes verified successfully!")

if __name__ == "__main__":
    test_api()
