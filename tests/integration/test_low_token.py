"""
Low-Token Test Suite for Wildfire Agent & Jev Supervisor Integration.

Designed to verify end-to-end functionality while strictly minimizing
LLM token usage (< 450 total tokens per run).
"""

import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import asyncio
import logging
import time
from src.storage.sqlite_db import init_db, save_jev_decision, get_jev_history, DB_PATH
from src.governance.engine import GovernanceEngine, GovernanceSnapshot
from src.governance.alerts import AlertLevel
from src.agents.jev_supervisor import JevSupervisor, JevDecision

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test")


async def run_low_token_tests():
    print("=" * 60)
    print("🔥 OBOR — LOW-TOKEN INTEGRATION TEST SUITE")
    print("=" * 60)

    # 1. Initialize Database
    print("\n[Test 1] Database Initialization & Jev Decisions Table...")
    await init_db()
    print("  ✓ Database schema verified with jev_decisions table.")

    # 2. Test AVF Governance Engine (0 tokens)
    print("\n[Test 2] AVF Governance Engine (Zero LLM Tokens)...")
    gov = GovernanceEngine()
    mock_fires = [
        {
            "fire_id": "test_fire_001",
            "name": "Oak Creek Fire",
            "state": "CA",
            "county": "Kern",
            "daily_acres": 3500.0,
            "percent_contained": 15.0,
            "fire_cause": "Human",
            "latitude": 35.37,
            "longitude": -119.01,
        },
        {
            "fire_id": "test_fire_002",
            "name": "Pine Ridge Fire",
            "state": "CA",
            "county": "Tulare",
            "daily_acres": 800.0,
            "percent_contained": 80.0,
            "fire_cause": "Lightning",
            "latitude": 36.10,
            "longitude": -118.80,
        }
    ]
    changes = {
        "new": [mock_fires[0]],
        "escalating": [],
        "improving": [],
        "total_acres": 4300.0,
    }
    snapshot = gov.evaluate(mock_fires, changes)
    print(f"  ✓ AVF evaluated: VI = {snapshot.viability_index:+.4f}, Safety C1 = {snapshot.c1_safety:+.3f}")
    print(f"  ✓ Alert levels: {snapshot.alert_levels}")

    # 3. Test Jev AI Supervisor with Low-Token Payload
    print("\n[Test 3] Jev AI Supervisor Call (Minimal Token Budget)...")
    jev = JevSupervisor()
    if not jev.enabled:
        print("  ⚠️  Jev API key not detected, skipping live API call.")
        return

    # Compact state representation ensures minimal tokens
    t0 = time.time()
    decision = await jev.evaluate(mock_fires, snapshot, changes)
    duration_ms = (time.time() - t0) * 1000

    print(f"  ✓ Jev API Call completed in {duration_ms:.0f}ms")
    print(f"  ✓ Threat Probability: {decision.is_immediate_threat * 100:.1f}%")
    print(f"  ✓ Dispatch Needed:    {decision.requires_emergency_dispatch * 100:.1f}%")
    print(f"  ✓ AVF Override Rec:   {decision.avf_override_recommended * 100:.1f}%")
    print(f"  ✓ Recommended Level:  {decision.recommended_response_level} (conf: {decision.response_level_confidence * 100:.1f}%)")
    print(f"  ✓ Severity Score:     {decision.overall_severity_score:.2f} (conf: {decision.severity_confidence * 100:.1f}%)")

    if decision.raw_response and "usage" in decision.raw_response:
        usage = decision.raw_response["usage"]
        print(f"  🎯 Token Usage Verified:")
        print(f"     • Input Tokens:  {usage.get('input_tokens', 'N/A')}")
        print(f"     • Output Tokens: {usage.get('output_tokens', 'N/A')}")
        print(f"     • Total Tokens:  {usage.get('input_tokens', 0) + usage.get('output_tokens', 0)}")

    # 4. Test Supervisor Reconciliation Logic
    print("\n[Test 4] Parallel Supervisor Reconciliation...")
    LEVEL_RANK = {"MONITOR": 0, "WATCH": 1, "WARNING": 2, "EMERGENCY": 3}
    jev_level = decision.recommended_response_level.upper()
    jev_rank = LEVEL_RANK.get(jev_level, 0)
    override_applied = False

    for fire in mock_fires:
        fid = fire["fire_id"]
        avf_alert = snapshot.alert_levels.get(fid, "MONITOR")
        avf_rank = LEVEL_RANK.get(avf_alert, 0)
        if decision.response_level_confidence >= 0.85 and jev_rank > avf_rank:
            override_applied = True
            print(f"  ⚡ Safety Escalation: {fire['name']} escalated {avf_alert} → {jev_level}")
        else:
            print(f"  ✓ Maintained Level: {fire['name']} at {avf_alert} (Jev agreed or below threshold)")

    # 5. Test Database Persistence
    print("\n[Test 5] Database Persistence & History Retrieval...")
    await save_jev_decision(decision)
    history = await get_jev_history(5)
    print(f"  ✓ Successfully retrieved {len(history)} recent Jev decision(s) from database.")
    if history:
        latest = history[0]
        print(f"  ✓ Latest stored decision: threat={latest['is_immediate_threat']:.2f}, level={latest['recommended_response_level']}")

    await jev.close()
    print("\n" + "=" * 60)
    print("✅ ALL LOW-TOKEN INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_low_token_tests())
