"""Unit tests for TypeSafe Jev AI Supervisor."""

import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from src.agents.jev_supervisor import JevSupervisor, JevDecision
from src.governance import GovernanceSnapshot


class TestJevSupervisor(unittest.IsolatedAsyncioTestCase):
    """Verifies JevSupervisor state machine, parsing, and error fallback."""

    def setUp(self):
        self.supervisor = JevSupervisor()

    def test_initial_state(self):
        """Supervisor must initialize with a valid last_decision and dictionary representation."""
        self.assertIsNotNone(self.supervisor.last_decision)
        self.assertIsInstance(self.supervisor.last_decision, JevDecision)
        self.assertGreater(self.supervisor.last_decision.timestamp, 0)

        data = self.supervisor.to_dict()
        self.assertIn("enabled", data)
        self.assertIn("total_decisions", data)
        self.assertIn("last_decision", data)
        self.assertIn("decision_history", data)
        self.assertIsNotNone(data["last_decision"])

    def test_build_state_formatting(self):
        """State formatting must include VI, fire count, and peatland indicators."""
        mock_snapshot = GovernanceSnapshot(
            timestamp=1700000000.0,
            viability_index=0.85,
            c1_safety=0.90,
            c2_fairness=0.80,
            c3_stability=0.85,
            t_star=None,
            active_fires=2,
            total_acres=500.0,
            alert_levels={"F-1": "MONITOR", "F-2": "WARNING"},
        )
        mock_fires = [
            {"fire_id": "F-1", "name": "Sebangau Fire", "hectares": 120, "daily_acres": 296, "percent_contained": 20, "is_peatland": True, "county": "Pulang Pisau"},
            {"fire_id": "F-2", "name": "Ketapang Fire", "hectares": 80, "daily_acres": 197, "percent_contained": 60, "is_peatland": False, "county": "Ketapang"},
        ]
        mock_changes = {"total_hectares": 200, "new": [], "escalating": ["F-1"]}

        state = self.supervisor._build_state(mock_fires, mock_snapshot, mock_changes)
        self.assertIn("Kalimantan", state)
        self.assertIn("VI=+0.850", state)
        self.assertIn("Sebangau Fire", state)
        self.assertIn("peat=YES", state)

    def test_parse_response(self):
        """Parsing TypeSafe Jev JSON structure must populate all decision dimensions."""
        mock_api_response = {
            "answers": {
                "is_immediate_threat": {"noul": 0.88},
                "requires_emergency_dispatch": {"noul": 0.92},
                "avf_override_recommended": {"noul": 0.75},
                "recommended_response_level": {
                    "choice": "EMERGENCY",
                    "confidence": 0.95,
                    "probabilities": {"EMERGENCY": 0.95, "WARNING": 0.05}
                },
                "overall_severity": {
                    "score": 2.8,
                    "confidence": 0.90,
                    "probabilities": {"CRITICAL": 0.85, "HIGH": 0.15}
                }
            }
        }

        decision = self.supervisor._parse_response(mock_api_response, latency=145.2)
        self.assertAlmostEqual(decision.is_immediate_threat, 0.88)
        self.assertAlmostEqual(decision.requires_emergency_dispatch, 0.92)
        self.assertAlmostEqual(decision.avf_override_recommended, 0.75)
        self.assertEqual(decision.recommended_response_level, "EMERGENCY")
        self.assertAlmostEqual(decision.response_level_confidence, 0.95)
        self.assertAlmostEqual(decision.overall_severity_score, 2.8)
        self.assertAlmostEqual(decision.latency_ms, 145.2)

    def test_fallback_decision(self):
        """Fallback decision must provide safe defaults with error flag."""
        fallback = self.supervisor._fallback_decision(error="Network unreachable", latency=12.0)
        self.assertEqual(fallback.is_immediate_threat, 0.0)
        self.assertEqual(fallback.recommended_response_level, "MONITOR")
        self.assertEqual(fallback.error, "Network unreachable")
        self.assertEqual(fallback.latency_ms, 12.0)

        # Dictionary should be JSON-serializable
        d_dict = fallback.to_dict()
        self.assertEqual(d_dict["error"], "Network unreachable")
        self.assertEqual(d_dict["recommended_response_level"], "MONITOR")

    async def test_evaluate_handles_http_error(self):
        """Supervisor must catch HTTP errors and return fallback without throwing."""
        with patch.object(self.supervisor.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "503 Service Unavailable",
                request=MagicMock(),
                response=httpx.Response(503, text="Overloaded")
            )
            self.supervisor._enabled = True

            mock_snapshot = GovernanceSnapshot(
                timestamp=1700000000.0, viability_index=0.5, c1_safety=0.5, c2_fairness=0.5,
                c3_stability=0.5, t_star=None, active_fires=0, total_acres=0.0, alert_levels={}
            )
            decision = await self.supervisor.evaluate([], mock_snapshot, {})
            self.assertIsNotNone(decision)
            self.assertIn("HTTP 503", decision.error)
            self.assertEqual(self.supervisor.last_decision, decision)


if __name__ == "__main__":
    unittest.main()
