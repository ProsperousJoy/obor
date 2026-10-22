"""
Module 6 — Planning Agent
-------------------------
Does NOT predict fire itself; synthesizes outputs from Moduls 1 through 5
into a coherent, actionable, safety-compliant Incident Action Plan (PLAN).
"""

from typing import Dict, Any, List
import uuid

class PlanningAgent:
    """
    Synthesizes Multi-Agent Intelligence into an executable operational plan.
    """
    def generate_plan(
        self,
        incident_id: str,
        fire_prediction: Dict[str, Any],
        trust_assessment: Dict[str, Any],
        impact_assessment: Dict[str, Any],
        water_recommendation: Dict[str, Any],
        resource_allocation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Creates an Incident Action Plan (IAP) with steps, dispatch orders, and fallbacks.
        """
        plan_id = f"PLAN-{incident_id}-{uuid.uuid4().hex[:4].upper()}"
        priority = impact_assessment.get("priority", "MEDIUM")
        fire_prob = float(fire_prediction.get("fire_probability", 0.5))
        trust_level = trust_assessment.get("trust_level", "MEDIUM")
        
        # Determine Response Action
        if priority == "CRITICAL" and fire_prob >= 0.85:
            if resource_allocation.get("equipment", {}).get("helicopter_available"):
                action = "AIR_RESPONSE"
            elif impact_assessment.get("settlement_distance_km", 10.0) <= 2.0:
                action = "EVACUATION_SUPPORT"
            else:
                action = "GROUND_RESPONSE"
        elif priority in ["HIGH", "MEDIUM"] or fire_prob >= 0.50:
            action = "GROUND_RESPONSE"
        else:
            action = "MONITOR"

        # Determine human approval policy
        # CRITICAL always requires human approval; LOW/MEDIUM can be autonomous if trust is HIGH
        if priority == "CRITICAL" or not trust_assessment.get("autonomous_action_allowed", False):
            human_approval_required = True
        else:
            human_approval_required = False

        # Build operational steps
        hq_name = resource_allocation.get("hq", "Nearest Daops")
        crew_count = resource_allocation.get("recommended_crew", 6)
        water_name = water_recommendation.get("recommended_water_source", "Primary Canal")
        water_dist = water_recommendation.get("distance_km", 2.0)
        eta = resource_allocation.get("eta_minutes", 30)

        steps = [
            f"Transmit automated incident alert to command center and {hq_name}",
            f"Deploy aerial verification drone for thermal mapping of perimeter",
            f"Dispatch {crew_count}-person ground suppression crew via primary access road",
            f"Establish pumping relay and water intake point at {water_name} ({water_dist} km from flank)",
            f"Construct perimeter firebreak along vulnerable boundary"
        ]

        if impact_assessment.get("settlement_distance_km", 10.0) <= 3.0:
            steps.append("Coordinate with local BPBD and village heads for defensive misting near settlements")

        # Communication targets
        comms = ["command_center_provinsi", f"hq_{resource_allocation.get('hq_id', 'local')}"]
        if impact_assessment.get("settlement_distance_km", 10.0) <= 5.0:
            comms.append("bpbd_kabupaten")

        # Fallback Plan
        backups = water_recommendation.get("backup_water_sources", [])
        backup_water_name = backups[0]["source_name"] if backups else "Secondary Peat Trench"
        fallback = {
            "condition": f"Primary water source ({water_name}) dry or blocked access",
            "action": f"Reroute water tenders to {backup_water_name}"
        }

        # Replanning Triggers
        replan_conditions = [
            "Wind shift greater than 45 degrees",
            "Fire intensity upgraded to HIGH/CRITICAL",
            "Primary water source depleted",
            "Crew response delayed beyond 45 minutes"
        ]

        return {
            "plan_id": plan_id,
            "incident_id": incident_id,
            "priority": priority,
            "action": action,
            "dispatch": {
                "hq": hq_name,
                "hq_id": resource_allocation.get("hq_id"),
                "crew": crew_count,
                "equipment": resource_allocation.get("equipment")
            },
            "water_source": {
                "source_id": water_recommendation.get("source_id"),
                "name": water_name,
                "distance_km": water_dist,
                "route_distance_km": water_recommendation.get("route_distance_km")
            },
            "eta_minutes": eta,
            "steps": steps,
            "communication_target": comms,
            "human_approval_required": human_approval_required,
            "fallback_plan": fallback,
            "replan_conditions": replan_conditions
        }
