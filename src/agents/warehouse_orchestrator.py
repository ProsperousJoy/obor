"""
End-to-End Fire Response AI Orchestrator
----------------------------------------
Chains all 9 modules from Fire Prediction to Trust, Impact, Water,
Resource Allocation, Planning, Execution, and Feedback Learning.
"""

from typing import Dict, Any
from datetime import datetime
import duckdb

from src.agents.trust_agent import TrustSupervisor
from src.agents.impact_agent import ImpactAgent
from src.agents.water_agent import WaterResourceAgent
from src.agents.resource_agent import ResourceAgent
from src.agents.planning_agent import PlanningAgent
from src.agents.execution_agent import ExecutionAgent

class ResponseSystemOrchestrator:
    """
    Coordinates multi-agent incident triage and response workflows.
    """
    def __init__(self, db_path: str = "data/warehouse/wildfire.duckdb"):
        self.db_path = db_path
        self.trust_supervisor = TrustSupervisor()
        self.impact_agent = ImpactAgent(db_path)
        self.water_agent = WaterResourceAgent(db_path)
        self.resource_agent = ResourceAgent(db_path)
        self.planning_agent = PlanningAgent()
        self.execution_agent = ExecutionAgent(db_path)

    def process_incident(
        self,
        incident_id: str,
        fire_prediction: Dict[str, Any],
        viirs_evidence: Dict[str, Any],
        himawari_evidence: Dict[str, Any] = None,
        weather_evidence: Dict[str, Any] = None,
        authorization_level: str = "AUTO_MEDIUM"
    ) -> Dict[str, Any]:
        """
        Executes end-to-end multi-agent workflow for an incident.
        """
        conn = duckdb.connect(self.db_path, read_only=False)
        try:
            try:
                from src.storage.bootstrap import bootstrap_response_warehouse
                bootstrap_response_warehouse(conn)
            except Exception:
                pass

            # 1. Modul 2: Trust Assessment
            trust_out = self.trust_supervisor.evaluate_trust(
                incident_id=incident_id,
                fire_prediction=fire_prediction,
                viirs_evidence=viirs_evidence,
                himawari_evidence=himawari_evidence,
                weather_evidence=weather_evidence
            )

            # 2. Modul 3: Impact Assessment
            impact_out = self.impact_agent.assess_impact(
                incident_id=incident_id,
                fire_lat=fire_prediction["lat"],
                fire_lon=fire_prediction["lon"],
                fire_probability=fire_prediction["fire_probability"],
                fire_intensity=fire_prediction.get("fire_intensity", "MEDIUM"),
                estimated_area_ha=fire_prediction.get("estimated_area_ha", 5.0),
                wind_speed_kph=weather_evidence.get("wind_speed_kph", 15.0) if weather_evidence else 15.0,
                conn=conn
            )

            # 3. Modul 4: Water Resource Recommendation
            water_out = self.water_agent.recommend_water_source(
                incident_id=incident_id,
                fire_lat=fire_prediction["lat"],
                fire_lon=fire_prediction["lon"],
                conn=conn
            )

            # 4. Modul 5: Responder Resource Allocation
            resource_out = self.resource_agent.allocate_resources(
                incident_id=incident_id,
                fire_lat=fire_prediction["lat"],
                fire_lon=fire_prediction["lon"],
                priority=impact_out["priority"],
                fire_intensity=fire_prediction.get("fire_intensity", "MEDIUM"),
                estimated_area_ha=fire_prediction.get("estimated_area_ha", 5.0),
                conn=conn
            )

            # 5. Modul 6: Planning Agent
            plan_out = self.planning_agent.generate_plan(
                incident_id=incident_id,
                fire_prediction=fire_prediction,
                trust_assessment=trust_out,
                impact_assessment=impact_out,
                water_recommendation=water_out,
                resource_allocation=resource_out
            )

            # 6. Modul 7: Execution Agent
            exec_out = self.execution_agent.execute_plan(
                plan=plan_out,
                trust_score=trust_out["overall_trust"],
                fire_prediction=fire_prediction,
                impact_assessment=impact_out,
                authorization_level=authorization_level,
                conn=conn
            )

            return {
                "incident_id": incident_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "fire_prediction": fire_prediction,
                "trust": trust_out,
                "impact": impact_out,
                "water": water_out,
                "resource": resource_out,
                "plan": plan_out,
                "execution": exec_out
            }
        finally:
            conn.close()
