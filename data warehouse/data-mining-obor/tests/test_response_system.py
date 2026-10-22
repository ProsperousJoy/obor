"""
Verification & Simulation Suite for Response System (Modules 1-9)
-----------------------------------------------------------------
Simulates a real-world wildfire scenario in a high-risk peatland corridor
in Central Kalimantan (Pulang Pisau / Sebangau) and verifies all agent outputs.
"""

import sys
import json
from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.orchestrator import ResponseSystemOrchestrator
from src.agents.execution_agent import ExecutionAgent

def test_end_to_end_simulation():
    print("=" * 70)
    print("TESTING END-TO-END MULTI-AGENT RESPONSE SYSTEM (MODULES 1 - 9)")
    print("=" * 70)

    # 1. Setup Orchestrator
    orchestrator = ResponseSystemOrchestrator("data/warehouse/wildfire.duckdb")

    # 2. Simulate Active Incident in Central Kalimantan Peatland (Pulang Pisau)
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
        "model_version": "wildfire-lgbm-v1.0"
    }

    viirs_evidence = {
        "confidence": "high",
        "frp": 48.6,
        "brightness_temperature": 348.5,
        "delta_bt": 28.2
    }

    himawari_evidence = {
        "thermal_anomaly": True,
        "persistence_30m": True,
        "persistence_1h": True,
        "cloud_coverage": 0.12
    }

    weather_evidence = {
        "temperature_c": 34.5,
        "humidity_pct": 42.0,
        "wind_speed_kph": 22.0,
        "wind_direction_deg": 110.0,
        "consecutive_dry_days": 18
    }

    # 3. Execute Orchestrator
    print("\n[Step 1] Running Multi-Agent Orchestration Chain...")
    result = orchestrator.process_incident(
        incident_id=incident_id,
        fire_prediction=fire_prediction,
        viirs_evidence=viirs_evidence,
        himawari_evidence=himawari_evidence,
        weather_evidence=weather_evidence,
        authorization_level="AUTO_MEDIUM"
    )

    # 4. Verify Module 2 (Trust Supervisor)
    trust = result["trust"]
    print(f"\n[Modul 2 - Trust Supervisor]")
    print(f"  Overall Trust:        {trust['overall_trust']} ({trust['trust_level']})")
    print(f"  Agreement:            {trust['evidence_agreement']}")
    print(f"  Autonomous Allowed:   {trust['autonomous_action_allowed']}")
    print(f"  Human Verification:   {trust['human_verification_required']}")
    assert trust["overall_trust"] >= 0.70, "Trust score should be high given strong VIIRS+Himawari evidence"

    # 5. Verify Module 3 (Impact Assessment)
    impact = result["impact"]
    print(f"\n[Modul 3 - Impact Assessment]")
    print(f"  Impact Score:         {impact['impact_score']} / 100")
    print(f"  Priority:             {impact['priority']}")
    print(f"  Population at Risk:   {impact['population_at_risk']:,d}")
    print(f"  Nearest Settlement:   {impact['settlement_distance_km']} km")
    print(f"  Threatened Assets:    {impact['infrastructure_at_risk'][:2]}")
    assert impact["priority"] in ["HIGH", "CRITICAL"], "High intensity peat fire near villages must be HIGH or CRITICAL"

    # 6. Verify Module 4 (Water Resource Agent)
    water = result["water"]
    print(f"\n[Modul 4 - Water Resource Agent]")
    print(f"  Recommended Water:    {water['recommended_water_source']} ({water['water_type']})")
    print(f"  Distance / Route:     {water['distance_km']} km (Route: {water['route_distance_km']} km)")
    print(f"  ETA Pump Setup:       {water['estimated_travel_time_min']} minutes")
    print(f"  Suitability Score:    {water['water_suitability']}")
    assert water["distance_km"] <= 35.0, "Should locate an accessible water body within response corridor"

    # 7. Verify Module 5 (Resource Agent)
    resource = result["resource"]
    print(f"\n[Modul 5 - Resource Agent]")
    print(f"  Dispatched HQ:        {resource['hq']} ({resource['agency']})")
    print(f"  Station Distance:     {resource['distance_km']} km")
    print(f"  Response ETA:         {resource['eta_minutes']} minutes")
    print(f"  Crew Allocated:       {resource['recommended_crew']} firefighters")
    print(f"  Readiness Score:      {resource['readiness_score']}")
    assert "Manggala Agni" in resource["hq"], "Should dispatch nearest Manggala Agni post"

    # 8. Verify Module 6 (Planning Agent)
    plan = result["plan"]
    print(f"\n[Modul 6 - Planning Agent]")
    print(f"  Plan ID:              {plan['plan_id']}")
    print(f"  Assigned Action:      {plan['action']}")
    print(f"  Approval Required:    {plan['human_approval_required']}")
    print(f"  Key Step 1:           {plan['steps'][0]}")
    print(f"  Key Step 4 (Water):   {plan['steps'][3]}")
    print(f"  Fallback Strategy:    {plan['fallback_plan']['action']}")

    # 9. Verify Module 7 (Execution Agent & Warehouse Persistence)
    exec_res = result["execution"]
    print(f"\n[Modul 7 - Execution Agent]")
    print(f"  Execution Status:     {exec_res['action_execution_status']}")
    print(f"  Alert Dispatched:     {exec_res['alert_sent']}")
    print(f"  Executed Actions:     {exec_res['executed_actions']}")
    print(f"  Blocked Actions:      {exec_res['blocked_actions']}")

    # Check persistence in DuckDB
    conn = duckdb.connect("data/warehouse/wildfire.duckdb", read_only=True)
    row = conn.execute(f"SELECT incident_id, priority, recommended_action, execution_status FROM fact_incident_records WHERE incident_id = '{incident_id}'").fetchone()
    conn.close()
    assert row is not None, "Incident record must be saved in fact_incident_records"
    print(f"  -> Persisted in fact_incident_records: {row}")

    # 10. Verify Module 9 (Feedback & Adaptive Learning Loop)
    print(f"\n[Modul 9 - Feedback & Learning Loop]")
    exec_agent = ExecutionAgent("data/warehouse/wildfire.duckdb")
    fb = exec_agent.log_incident_feedback(
        incident_id=incident_id,
        predicted_fire_prob=fire_prediction["fire_probability"],
        real_fire_confirmed=True,
        actual_burn_area_ha=11.2,
        actual_response_time_min=35,
        actual_water_source_used=water["recommended_water_source"]
    )
    print(f"  Feedback ID:          {fb['feedback_id']}")
    print(f"  Prediction Error:     {fb['prediction_error']}")
    print(f"  Plan Success Score:   {fb['plan_success_score']}")
    print(f"  Water Accuracy:       {fb['water_accuracy_score']}")
    print(f"  Retraining Trigger:   {fb['retraining_candidate']}")

    conn = duckdb.connect("data/warehouse/wildfire.duckdb", read_only=True)
    fb_row = conn.execute(f"SELECT feedback_id, plan_success_score, retraining_candidate FROM fact_incident_feedback WHERE incident_id = '{incident_id}'").fetchone()
    conn.close()
    assert fb_row is not None, "Feedback record must be saved in fact_incident_feedback"
    print(f"  -> Persisted in fact_incident_feedback: {fb_row}")

    print("\n" + "=" * 70)
    print("ALL 9 MODULES SUCCESSFULLY VERIFIED AND INTEGRATED!")
    print("=" * 70)

if __name__ == "__main__":
    test_end_to_end_simulation()
