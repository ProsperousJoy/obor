"""
test_borneo_low_token.py
========================
Low-Token Verification & End-to-End Simulation Suite for Kalimantan (Borneo)
Wildfire Sentinel with DuckDB Data Warehouse and Dual Supervisors (AVF + Jev AI).

Strictly adheres to:
  1. Low-token testing constraint (< 600 input tokens per evaluation)
  2. Zero real emergency calls (strictly simulated / logged)
  3. Validates full integration: DuckDB -> Fetcher -> Agents -> AVF -> Jev AI -> Dispatcher -> Persistence
"""

import sys
import time
import asyncio
from pathlib import Path
import duckdb

# Add workspace to path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from config import config
from data_fetcher import WildfireDataFetcher, assign_grid_id
from governance import GovernanceEngine
from emergency_dispatcher import EmergencyDispatcher
from jev_supervisor import JevSupervisor

# Add warehouse to path after root imports
WH_DIR = WORKSPACE_ROOT / "data warehouse" / "data-mining-obor"
if str(WH_DIR) not in sys.path:
    sys.path.append(str(WH_DIR))

from src.agents.impact_agent import ImpactAgent
from src.agents.water_agent import WaterResourceAgent
from src.agents.resource_agent import ResourceAgent


async def main():
    print("=" * 75)
    print("🌲 BORNEO WILDFIRE SENTINEL — LOW-TOKEN END-TO-END VERIFICATION")
    print("=" * 75)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Verify DuckDB Data Warehouse Tables & Dimensions
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Step 1/6] Connecting to DuckDB Data Warehouse...")
    db_path = config.WAREHOUSE_DB_PATH
    conn = duckdb.connect(db_path, read_only=True)
    try:
        tables = set(conn.execute("SHOW TABLES").df()["name"].tolist())
        print(f"  Connected to DuckDB: {db_path}")
        print(f"  Total tables/views found: {len(tables)}")
        
        required_tables = [
            "fact_fire_hotspots", "fact_thermal_grid", "fact_forecast_3h",
            "dim_water_sources", "dim_responder_hq", "dim_vulnerable_assets",
            "fact_incident_records"
        ]
        for tbl in required_tables:
            assert tbl in tables, f"Missing critical table: {tbl}"
            count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"    ✓ {tbl:25s}: {count:,d} records")
    finally:
        conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Test Data Ingestion & Live Warehouse Querying
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Step 2/6] Ingesting Kalimantan Fire Incidents...")
    fetcher = WildfireDataFetcher()
    try:
        fires = await fetcher.fetch()
        changes = fetcher.get_changes()
        print(f"  Fetched {len(fires)} active fire incident clusters across Borneo")
        print(f"  Total burning area: {changes['total_hectares']:,.1f} ha ({changes['total_acres']:,.1f} acres)")

        # Inspect top incident
        top_fire = fires[0]
        print(f"  Top incident: {top_fire['name']}")
        print(f"    Province/Regency: {top_fire['province']} / {top_fire['county']}")
        print(f"    Coordinates:      [{top_fire['latitude']}, {top_fire['longitude']}]")
        print(f"    Canonical Grid:   {assign_grid_id(top_fire['latitude'], top_fire['longitude'])}")
        print(f"    Peatland Status:  {'🔥 PEATLAND' if top_fire['is_peatland'] else 'Mineral Forest'}")
        print(f"    Weather Lookup:   {top_fire.get('weather', {}).get('temperature_c')}°C, Wind: {top_fire.get('weather', {}).get('wind_speed_kph')} km/h ({top_fire.get('weather', {}).get('station')})")
        print(f"    Himawari SWIR:    {top_fire.get('himawari', {}).get('brightness_temp_k'):.1f} K (Sensor: {top_fire.get('himawari', {}).get('sensor')})")
    finally:
        await fetcher.close()

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Test Specialized Warehouse Agents (Impact, Water, Resource)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Step 3/6] Running Specialized Ground Agents...")
    ia = ImpactAgent(db_path)
    wa = WaterResourceAgent(db_path)
    ra = ResourceAgent(db_path)

    fire_id = top_fire["fire_id"]
    lat, lon = top_fire["latitude"], top_fire["longitude"]
    ha = top_fire.get("hectares", 150.0)

    impact = ia.assess_impact(fire_id, lat, lon, 0.92, "HIGH", ha)
    water = wa.recommend_water_source(fire_id, lat, lon)
    resource = ra.allocate_resources(fire_id, lat, lon, impact["priority"], "HIGH", ha)

    print(f"  [Impact Agent]   Priority: {impact['priority']} | Score: {impact['impact_score']}/100 | Pop at Risk: {impact['population_at_risk']:,d}")
    print(f"  [Water Agent]    Source: {water['recommended_water_source']} ({water['water_type']}) | Track Dist: {water['route_distance_km']} km | Pump ETA: {water['estimated_travel_time_min']}m")
    print(f"  [Resource Agent] Station: {resource['hq']} | Allocated Crew: {resource['recommended_crew']} firefighters | ETA: {resource['eta_minutes']}m")

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Evaluate AVF Governance Engine
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Step 4/6] Evaluating AVF Governance Engine...")
    gov = GovernanceEngine()
    snapshot = gov.evaluate(fires, changes)
    print(f"  Viability Index VI(t): {snapshot.viability_index:+.4f} (Threshold: 0.50)")
    print(f"    C1 (Safety - Peatland-weighted): {snapshot.c1_safety:+.3f}")
    print(f"    C2 (Fairness - 5-Province Eq.):  {snapshot.c2_fairness:+.3f}")
    print(f"    C3 (Stability / Agreement):      {snapshot.c3_stability:+.3f}")
    print(f"    Time-to-violation t*:            {snapshot.t_star if snapshot.t_star else 'Safe ✓'}")

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Evaluate TypeSafe Jev AI Decision Model (Low-Token Mode < 600 tokens)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Step 5/6] Invoking TypeSafe Jev AI Cognitive Supervisor...")
    jev = JevSupervisor()
    
    t0 = time.time()
    decision = await jev.evaluate(fires[:3], snapshot, changes)
    latency_ms = (time.time() - t0) * 1000

    print(f"  API Latency:            {latency_ms:.0f} ms")
    print(f"  Threat Level:           {decision.is_immediate_threat * 100:.0f}%")
    print(f"  Requires Dispatch:      {decision.requires_emergency_dispatch * 100:.0f}%")
    print(f"  AVF Override Rec.:      {decision.avf_override_recommended * 100:.0f}%")
    print(f"  Recommended Level:      {decision.recommended_response_level} (conf: {decision.response_level_confidence * 100:.0f}%)")
    print(f"  Severity Confidence:    {decision.severity_confidence * 100:.0f}%")
    print(f"  Model Target:           TypeSafe SystemOne (jev-latest)")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Dispatch Execution & DuckDB Logging
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Step 6/6] Executing Simulated Dispatch & Logging to DuckDB...")
    dispatcher = EmergencyDispatcher()
    report = dispatcher.dispatch(top_fire, "EMERGENCY")

    print(f"  Generated Dispatch ID:  {report.dispatch_id}")
    print(f"  Station:                {report.nearest_station}")
    print(f"  Water Supply:           {report.nearest_water_source}")
    print(f"  Personnel Deployed:     {report.total_personnel} crew members")
    print(f"  Response ETA:           {report.estimated_response_time_min} minutes")
    print(f"  Evacuation Advisory:    {report.evacuation_advisory}")

    # Verify persistence in DuckDB
    conn = duckdb.connect(db_path, read_only=True)
    try:
        logged_row = conn.execute(f"SELECT incident_id, priority, execution_status FROM fact_incident_records WHERE incident_id = '{report.dispatch_id}'").fetchone()
        assert logged_row is not None, "Dispatch record must be saved in fact_incident_records"
        print(f"  ✓ Verified persistence in fact_incident_records: {logged_row}")
    finally:
        conn.close()

    print("\n" + "=" * 75)
    print("🎉 ALL SYSTEMS OPERATIONAL: DATA WAREHOUSE + AVF + JEV AI + DISPATCH")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(main())
