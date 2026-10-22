"""
Module 7 & 9 — Execution & Feedback Agent
-----------------------------------------
Module 7 determines authorized operational actions, dispatches alerts,
and persists execution state to fact_incident_records in the warehouse.
Module 9 ingests ground-truth field outcomes, computes error & plan success,
and logs feedback for adaptive learning and model retraining.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import duckdb


def _resolve_default_db_path() -> str:
    # 1. Try src.config
    try:
        from src.config import config
        if Path(config.WAREHOUSE_DB_PATH).exists():
            return config.WAREHOUSE_DB_PATH
    except Exception:
        pass

    # 2. Direct relative search from this file or parent dirs
    current = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = current / "data warehouse" / "data-mining-obor" / "data" / "warehouse" / "wildfire.duckdb"
        if candidate.exists():
            return str(candidate)
        candidate2 = current / "data" / "warehouse" / "wildfire.duckdb"
        if candidate2.exists():
            return str(candidate2)
        current = current.parent

    # 3. Try root config
    try:
        import config as root_cfg
        if hasattr(root_cfg, "config") and Path(root_cfg.config.WAREHOUSE_DB_PATH).exists():
            return root_cfg.config.WAREHOUSE_DB_PATH
    except Exception:
        pass

    return "data warehouse/data-mining-obor/data/warehouse/wildfire.duckdb"


class ExecutionAgent:
    """
    Executes or gates plans based on trust levels and authorization policies.
    Logs incident records and feedback loops directly into the warehouse.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or _resolve_default_db_path()

    def execute_plan(
        self,
        plan: Dict[str, Any],
        trust_score: float,
        fire_prediction: Dict[str, Any],
        impact_assessment: Dict[str, Any],
        authorization_level: str = "AUTO_MEDIUM",
        conn: duckdb.DuckDBPyConnection = None
    ) -> Dict[str, Any]:
        """
        Gates actions based on trust score and authorization level.
        Persists incident state into fact_incident_records.
        """
        executed_actions = []
        blocked_actions = []

        requires_approval = plan.get("human_approval_required", True)

        # Automated alerts always permitted if trust >= 0.50
        if trust_score >= 0.50:
            executed_actions.extend([
                "notify_command_center",
                "notify_nearby_hq",
                "generate_access_route"
            ])
            alert_sent = True
            hq_contacted = True
        else:
            blocked_actions.append("notify_nearby_hq (trust too low)")
            alert_sent = False
            hq_contacted = False

        # Autonomous dispatch
        if not requires_approval and authorization_level in ["AUTO_MEDIUM", "AUTO_LOW"]:
            executed_actions.append("dispatch_ground_verification_drone")
            executed_actions.append("dispatch_ground_crew")
            action_status = "EXECUTING"
            operator_approval_requested = False
        else:
            blocked_actions.append("dispatch_ground_crew (requires human operator approval)")
            action_status = "PENDING"
            operator_approval_requested = True

        execution_result = {
            "incident_id": plan["incident_id"],
            "plan_id": plan["plan_id"],
            "action_execution_status": action_status,
            "alert_sent": alert_sent,
            "hq_contacted": hq_contacted,
            "operator_approval_requested": operator_approval_requested,
            "executed_actions": executed_actions,
            "blocked_actions": blocked_actions
        }

        # Persist into fact_incident_records
        close_conn = False
        if conn is None:
            conn = duckdb.connect(self.db_path, read_only=False)
            close_conn = True

        try:
            target_dt = fire_prediction.get("prediction_time", "2026-09-25 00:00:00")
            grid_id = fire_prediction.get("grid_id", "G0000_0000")
            fire_prob = float(fire_prediction.get("fire_probability", 0.5))
            fire_intensity = fire_prediction.get("fire_intensity", "MEDIUM")
            impact_score = int(impact_assessment.get("impact_score", 50))
            priority = impact_assessment.get("priority", "MEDIUM")
            rec_action = plan.get("action", "GROUND_RESPONSE")
            assigned_hq = plan.get("dispatch", {}).get("hq_id", "HQ-MA-KT-01")
            assigned_water = plan.get("water_source", {}).get("source_id", "WTR-RIV-03")
            eta = int(plan.get("eta_minutes", 30))
            steps_str = json.dumps(plan.get("steps", []))

            conn.execute("""
                INSERT INTO fact_incident_records (
                    incident_id, plan_id, target_datetime, grid_id,
                    fire_probability, fire_intensity, impact_score, priority,
                    recommended_action, assigned_hq_id, assigned_water_id,
                    eta_minutes, steps_json, authorization_level, execution_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (incident_id) DO UPDATE SET
                    plan_id = EXCLUDED.plan_id,
                    target_datetime = EXCLUDED.target_datetime,
                    grid_id = EXCLUDED.grid_id,
                    fire_probability = EXCLUDED.fire_probability,
                    fire_intensity = EXCLUDED.fire_intensity,
                    impact_score = EXCLUDED.impact_score,
                    priority = EXCLUDED.priority,
                    recommended_action = EXCLUDED.recommended_action,
                    assigned_hq_id = EXCLUDED.assigned_hq_id,
                    assigned_water_id = EXCLUDED.assigned_water_id,
                    eta_minutes = EXCLUDED.eta_minutes,
                    steps_json = EXCLUDED.steps_json,
                    authorization_level = EXCLUDED.authorization_level,
                    execution_status = EXCLUDED.execution_status
            """, [
                plan["incident_id"], plan["plan_id"], target_dt, grid_id,
                fire_prob, fire_intensity, impact_score, priority,
                rec_action, assigned_hq, assigned_water,
                eta, steps_str, authorization_level, action_status
            ])
            conn.commit()
        except Exception as e:
            # Table insert failure should not crash execution response
            print(f"Warning: could not insert incident record: {e}")
        finally:
            if close_conn:
                conn.close()

        return execution_result

    def log_incident_feedback(
        self,
        incident_id: str,
        predicted_fire_prob: float,
        real_fire_confirmed: bool,
        actual_burn_area_ha: float = 0.0,
        actual_response_time_min: int = 30,
        actual_water_source_used: str = "Embung Sebangau 01",
        conn: duckdb.DuckDBPyConnection = None
    ) -> Dict[str, Any]:
        """
        Modul 9: Records field outcome and updates model learning indicators.
        """
        # Calculate error metrics
        pred_val = 1.0 if predicted_fire_prob >= 0.5 else 0.0
        actual_val = 1.0 if real_fire_confirmed else 0.0
        prediction_error = abs(predicted_fire_prob - actual_val)
        
        # Plan success based on response speed and confirmation
        plan_success = 0.90 if real_fire_confirmed and actual_response_time_min <= 45 else 0.65
        retraining_candidate = (prediction_error >= 0.60) # High prediction error triggers retraining

        feedback_data = {
            "feedback_id": f"FB-{incident_id}",
            "incident_id": incident_id,
            "real_fire_confirmed": real_fire_confirmed,
            "actual_burn_area_ha": actual_burn_area_ha,
            "actual_response_time_min": actual_response_time_min,
            "actual_water_source_used": actual_water_source_used,
            "prediction_error": round(float(prediction_error), 3),
            "plan_success_score": round(float(plan_success), 2),
            "water_accuracy_score": 0.95 if actual_water_source_used else 0.50,
            "retraining_candidate": retraining_candidate
        }

        close_conn = False
        if conn is None:
            conn = duckdb.connect(self.db_path, read_only=False)
            close_conn = True

        try:
            conn.execute("""
                INSERT INTO fact_incident_feedback (
                    feedback_id, incident_id, real_fire_confirmed,
                    actual_burn_area_ha, actual_response_time_min,
                    actual_water_source_used, prediction_error,
                    plan_success_score, water_accuracy_score, retraining_candidate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (feedback_id) DO UPDATE SET
                    incident_id = EXCLUDED.incident_id,
                    real_fire_confirmed = EXCLUDED.real_fire_confirmed,
                    actual_burn_area_ha = EXCLUDED.actual_burn_area_ha,
                    actual_response_time_min = EXCLUDED.actual_response_time_min,
                    actual_water_source_used = EXCLUDED.actual_water_source_used,
                    prediction_error = EXCLUDED.prediction_error,
                    plan_success_score = EXCLUDED.plan_success_score,
                    water_accuracy_score = EXCLUDED.water_accuracy_score,
                    retraining_candidate = EXCLUDED.retraining_candidate
            """, [
                feedback_data["feedback_id"], incident_id, real_fire_confirmed,
                actual_burn_area_ha, actual_response_time_min, actual_water_source_used,
                feedback_data["prediction_error"], feedback_data["plan_success_score"],
                feedback_data["water_accuracy_score"], retraining_candidate
            ])
            conn.commit()
        except Exception as e:
            print(f"Warning: could not insert incident feedback: {e}")
        finally:
            if close_conn:
                conn.close()

        return feedback_data
