"""
Verification & Simulation Suite for Response System (Modules 1-9)
-----------------------------------------------------------------
Simulates a real-world wildfire scenario in a high-risk peatland corridor
in Central Kalimantan (Pulang Pisau / Sebangau) and verifies all agent outputs.
"""

import sys
import unittest
from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import config
from src.agents.warehouse_orchestrator import ResponseSystemOrchestrator
from src.agents.execution_agent import ExecutionAgent


class TestWarehouseResponseSystem(unittest.TestCase):
    """End-to-end integration test for modules 1 through 9."""

    def test_end_to_end_simulation(self):
        db_path = config.WAREHOUSE_DB_PATH
        orchestrator = ResponseSystemOrchestrator(db_path)

        incident_id = "INC-PULANGPISAU-2026-09"
        fire_prediction = {
            "incident_id": incident_id,
            "grid_id": "G0120_0295",
            "lat": -2.485,
            "lon": 114.080,
            "prediction_time": "2026-09-25T14:00:00+07:00",
            "fire_probability": 0.92,
            "fire_status": "PROBABLE",
            "fire_intensity": "HIGH",
            "estimated_area_ha": 14.5,
            "model_version": "wildfire-lgbm-v1.0",
        }

        viirs_evidence = {
            "confidence": "high",
            "frp": 48.6,
            "brightness_temperature": 348.5,
            "delta_bt": 28.2,
        }

        himawari_evidence = {
            "thermal_anomaly": True,
            "persistence_30m": True,
            "persistence_1h": True,
            "cloud_coverage": 0.12,
        }

        weather_evidence = {
            "temperature_c": 34.5,
            "humidity_pct": 42.0,
            "wind_speed_kph": 22.0,
            "wind_direction_deg": 135.0,
        }

        result = orchestrator.process_incident(
            incident_id=incident_id,
            fire_prediction=fire_prediction,
            viirs_evidence=viirs_evidence,
            himawari_evidence=himawari_evidence,
            weather_evidence=weather_evidence,
            authorization_level="AUTO_HIGH",
        )

        trust = result["trust"]
        self.assertGreaterEqual(trust["overall_trust"], 0.75)
        self.assertEqual(trust["trust_level"], "HIGH")

        impact = result["impact"]
        self.assertIn("priority", impact)
        self.assertGreater(impact["impact_score"], 0)

        water = result["water"]
        self.assertIn("recommended_water_source", water)
        self.assertGreater(water["water_suitability"], 0)

        resource = result["resource"]
        self.assertIn("hq", resource)
        self.assertGreater(resource["recommended_crew"], 0)

        plan = result["plan"]
        self.assertIn("action", plan)
        self.assertGreater(len(plan["steps"]), 0)

        exec_res = result["execution"]
        self.assertIn(exec_res["action_execution_status"], ["PENDING", "EXECUTING", "EXECUTED"])

        # Module 9 - Feedback & Learning Loop
        exec_agent = ExecutionAgent(db_path)
        fb = exec_agent.log_incident_feedback(
            incident_id=incident_id,
            predicted_fire_prob=fire_prediction["fire_probability"],
            real_fire_confirmed=True,
            actual_burn_area_ha=11.2,
            actual_response_time_min=35,
            actual_water_source_used=water["recommended_water_source"],
        )
        self.assertIn("feedback_id", fb)
        self.assertGreaterEqual(fb["plan_success_score"], 0.0)

        conn = duckdb.connect(db_path)
        try:
            fb_row = conn.execute(
                f"SELECT feedback_id, plan_success_score, retraining_candidate FROM fact_incident_feedback WHERE incident_id = '{incident_id}'"
            ).fetchone()
            self.assertIsNotNone(fb_row)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
