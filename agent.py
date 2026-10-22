"""
Wildfire Agent — AI-powered reasoning engine for fire risk analysis.

Uses Google Gemini for intelligent risk assessment and prediction,
with fallback to rule-based analysis when API key is unavailable.
Integrates with the AVF governance engine and emergency dispatcher.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI

from config import config
from governance import GovernanceEngine, GovernanceSnapshot, AlertLevel
from emergency_dispatcher import EmergencyDispatcher, DispatchReport
from data_fetcher import WildfireDataFetcher
from jev_supervisor import JevSupervisor, JevDecision
from wildfire_predictor import get_wildfire_predictor, WildfirePredictor
import database as db

logger = logging.getLogger("wildfire.agent")


SYSTEM_PROMPT = """You are Wildfire Sentinel, an autonomous AI agent monitoring wildfire incidents across Kalimantan (Borneo), Indonesia in real-time.

Your role:
1. Analyze current wildfire incidents across Kalimantan provinces (West, Central, South, East, North)
2. Assess risk levels based on fire growth trends, peatland depth, containment progress, and weather factors
3. Predict fire behavior over the next 6-24 hours
4. Recommend emergency response actions for Manggala Agni Daops and BPBD teams

You operate under the Agent Viability Framework (AVF) governance:
- Your decisions are monitored by a Viability Index (VI) that tracks system safety
- Alert levels are monotonically restricted (can only escalate, never downgrade)
- You must justify escalation decisions with quantitative reasoning

Respond ONLY with valid JSON in the following format:
{
    "risk_assessment": "Brief overall risk assessment",
    "fire_analyses": [
        {
            "fire_id": "ID",
            "fire_name": "Name",
            "risk_level": "LOW|MODERATE|HIGH|CRITICAL",
            "predicted_spread": "Prediction for next 6-24 hours",
            "key_concerns": ["concern1", "concern2"],
            "recommended_action": "Specific action recommendation"
        }
    ],
    "system_recommendation": "Overall system-level recommendation",
    "urgency_score": 0.0 to 1.0,
    "reasoning": "Brief reasoning for the assessment"
}
"""


class WildfireAgent:
    """
    AI-powered wildfire monitoring agent.

    Orchestrates data fetching, governance evaluation, AI analysis,
    and emergency dispatch in a continuous monitoring loop.
    """

    def __init__(self):
        self.fetcher = WildfireDataFetcher()
        self.governance = GovernanceEngine()
        self.dispatcher = EmergencyDispatcher()
        self.jev = JevSupervisor()

        # OpenAI / Tokito client (may be None if no API key)
        self._openai: Optional[AsyncOpenAI] = None
        if config.OPENAI_API_KEY:
            self._openai = AsyncOpenAI(
                base_url=config.OPENAI_BASE_URL,
                api_key=config.OPENAI_API_KEY,
            )

        # State
        self.cycle_count = 0
        self.last_analysis: Optional[dict] = None
        self.last_jev_decision: Optional[JevDecision] = None
        self.last_snapshot: Optional[GovernanceSnapshot] = None
        self.predictor: WildfirePredictor = get_wildfire_predictor()
        self.last_predictions: list = []
        self._event_callbacks: list = []  # SSE event push callbacks

    def on_event(self, callback):
        """Register a callback for SSE events: callback(event_type, data_dict)."""
        self._event_callbacks.append(callback)

    def _emit(self, event_type: str, data: dict):
        """Emit an event to all registered callbacks."""
        for cb in self._event_callbacks:
            try:
                cb(event_type, data)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

    async def initialize(self):
        """Initialize the agent — set up database."""
        await db.init_db()
        logger.info("🔥 Wildfire Sentinel Agent initialized")

        warnings = config.validate()
        for w in warnings:
            logger.warning(f"⚠️  {w}")

        await db.log_action(
            "SYSTEM_START", None,
            "Wildfire Sentinel Agent started",
            {"demo_mode": config.DEMO_MODE, "has_openai": bool(self._openai)}
        )

    async def run_cycle(self) -> dict:
        """
        Execute one monitoring cycle:
          1. Fetch latest fire data
          2. Detect changes
          3. Store snapshots
          4. Run AVF governance evaluation
          5. AI risk analysis
          6. Check for emergency dispatches
          7. Emit events for dashboard

        Returns a summary dict of the cycle results.
        """
        self.cycle_count += 1
        cycle_start = time.time()
        logger.info(f"━━━ Monitoring Cycle #{self.cycle_count} ━━━")

        # ── Step 1: Fetch data ──
        fires = await self.fetcher.fetch()
        changes = self.fetcher.get_changes()

        logger.info(
            f"📊 {len(fires)} active fires | "
            f"{len(changes['new'])} new | "
            f"{len(changes['escalating'])} escalating | "
            f"{changes['total_acres']:.0f} total acres"
        )

        # ── Step 2: Store snapshots in batch (single transaction) ──
        await db.upsert_fires_batch(fires)
        snapshots_data = [
            (
                fire["fire_id"],
                float(fire.get("daily_acres", 0) or 0),
                float(fire.get("percent_contained", 0) or 0),
                str(fire.get("alert_level", "MONITOR"))
            )
            for fire in fires
        ]
        await db.save_snapshots_batch(snapshots_data)

        # ── Step 3: Run AVF governance ──
        snapshot = self.governance.evaluate(fires, changes)
        self.last_snapshot = snapshot

        await db.save_governance_state(
            snapshot.viability_index,
            snapshot.c1_safety, snapshot.c2_fairness, snapshot.c3_stability,
            snapshot.t_star, snapshot.active_fires, snapshot.total_acres
        )

        vi_status = "SAFE" if snapshot.viability_index > 0.5 else \
                    "ELEVATED" if snapshot.viability_index > 0 else \
                    "WARNING" if snapshot.viability_index > -0.5 else "CRITICAL"

        logger.info(
            f"📈 VI(t) = {snapshot.viability_index:+.4f} [{vi_status}] | "
            f"C1={snapshot.c1_safety:+.3f} C2={snapshot.c2_fairness:+.3f} C3={snapshot.c3_stability:+.3f}"
        )

        if snapshot.t_star is not None:
            logger.warning(
                f"⏱️  Predicted time to violation: t* = {snapshot.t_star:.0f}s "
                f"({snapshot.t_star/60:.1f} min)"
            )

        # ── Step 3.5: Run Jev AI Supervisor (On-Demand Triggered) ──
        # Evaluates when new fires appear, fire escalates, VI degrades, or on periodic heartbeat
        trigger_jev = (
            self.last_jev_decision is None or
            len(changes.get("new", [])) > 0 or
            len(changes.get("escalating", [])) > 0 or
            snapshot.viability_index < config.VI_MONITOR_THRESHOLD or
            (self.cycle_count % config.SUPERVISOR_TRIGGER_HEARTBEAT_CYCLES == 1)
        )

        if trigger_jev:
            logger.info(f"🧠 Jev Supervisor triggered on cycle #{self.cycle_count} (events/condition met)")
            jev_decision = await self.jev.evaluate(fires, snapshot, changes)
            self.last_jev_decision = jev_decision
            await db.save_jev_decision(jev_decision)
        else:
            logger.debug("🧠 Jev evaluation skipped (stable cycle, zero token usage)")
            jev_decision = self.last_jev_decision or self.jev._fallback_decision()

        # ── Step 3.6: Reconcile supervisors (safety-first) ──
        # Jev can escalate but NEVER downgrade (respects P3 monotonic restriction)
        jev_override_applied = False
        LEVEL_RANK = {"MONITOR": 0, "WATCH": 1, "WARNING": 2, "EMERGENCY": 3}
        jev_level = jev_decision.recommended_response_level.upper()
        jev_rank = LEVEL_RANK.get(jev_level, 0)

        if (
            jev_decision.response_level_confidence >= config.JEV_OVERRIDE_THRESHOLD
            and jev_rank >= LEVEL_RANK["WARNING"]
        ):
            for fire in fires:
                fid = fire["fire_id"]
                current_alert = snapshot.alert_levels.get(fid, "MONITOR")
                curr_rank = LEVEL_RANK.get(current_alert, 0)
                if jev_rank > curr_rank:
                    snapshot.alert_levels[fid] = jev_level
                    if fid in self.governance.fire_states:
                        st = self.governance.fire_states[fid]
                        st.alert_level = AlertLevel.from_string(jev_level)
                        now_ts = time.time()
                        st.last_escalation_time = now_ts
                        if hasattr(st, "escalation_history"):
                            st.escalation_history.append(now_ts)
                    jev_override_applied = True
                    logger.warning(
                        f"🧠 Jev OVERRIDE: {fire.get('name', fid)} "
                        f"escalated {current_alert} → {jev_level} "
                        f"(confidence={jev_decision.response_level_confidence:.2f})"
                    )

        if jev_override_applied:
            await db.log_action(
                "JEV_OVERRIDE", None,
                f"Jev AI overrode AVF: escalated fires to {jev_level} "
                f"(threat={jev_decision.is_immediate_threat:.2f}, "
                f"confidence={jev_decision.response_level_confidence:.2f})",
                jev_decision.to_dict()
            )
            self._emit("action", {
                "type": "jev_override",
                "message": (
                    f"🧠 Jev AI OVERRIDE: Escalated to {jev_level} "
                    f"(threat={jev_decision.is_immediate_threat:.2f}, "
                    f"severity={jev_decision.overall_severity_score:.1f})"
                ),
                "timestamp": time.time(),
            })

        # Emit Jev decision event for dashboard
        self._emit("jev_decision", jev_decision.to_dict())

        # ── Step 3.7: 24h ML Predictive Wildfire Risk Foresight ──
        try:
            if self.predictor and self.predictor.is_ready:
                self.last_predictions = self.predictor.get_top_at_risk_cells(limit=5)
                for cell in self.last_predictions:
                    if "AWAS" in cell.get("risk_tier", ""):
                        logger.warning(
                            f"🔮 24h Risk AWAS: {cell['grid_id']} ({cell['province']}) "
                            f"- Calibrated Risk: {cell['calibrated_risk']*100:.1f}%, "
                            f"FRP: {cell['predicted_frp_mw']} MW"
                        )
        except Exception as e:
            logger.debug(f"Predictor query in cycle: {e}")

        # ── Step 4: AI Analysis (every 3 cycles or on escalation) ──
        should_analyze = (
            self.cycle_count % 3 == 1 or
            len(changes.get("new", [])) > 0 or
            len(changes.get("escalating", [])) > 0 or
            snapshot.viability_index < 0
        )

        if should_analyze:
            analysis = await self._run_ai_analysis(fires, snapshot, changes)
            self.last_analysis = analysis
        else:
            analysis = self.last_analysis

        # ── Step 5: Check for emergency dispatches ──
        dispatches = await self._check_dispatches(fires, snapshot, analysis)

        # ── Step 6: Log new fires and escalations ──
        for fire in changes.get("new", []):
            await db.log_action(
                "NEW_FIRE_DETECTED", fire["fire_id"],
                f"New fire detected: {fire['name']} in {fire.get('state', 'Unknown')}",
                {"acres": fire.get("daily_acres", 0), "location": [fire.get("latitude"), fire.get("longitude")]}
            )
            self._emit("action", {
                "type": "new_fire",
                "message": f"🔥 New fire detected: {fire['name']} ({fire.get('daily_acres', 0):.0f} acres)",
                "timestamp": time.time(),
                "fire_id": fire["fire_id"],
            })

        for fire in changes.get("escalating", []):
            await db.log_action(
                "FIRE_ESCALATING", fire["fire_id"],
                f"Fire escalating: {fire['name']} (+{fire.get('acre_change', 0):.0f} acres)",
                {"acre_change": fire.get("acre_change"), "containment_change": fire.get("containment_change")}
            )
            self._emit("action", {
                "type": "escalation",
                "message": f"⬆️ Fire escalating: {fire['name']} (+{fire.get('acre_change', 0):.0f} acres)",
                "timestamp": time.time(),
                "fire_id": fire["fire_id"],
            })

        # ── Step 7: Emit dashboard events ──
        # Fire update
        fire_data = []
        for fire in fires:
            fid = fire["fire_id"]
            alert = snapshot.alert_levels.get(fid, "MONITOR")
            fire_data.append({**fire, "alert_level": alert})

        self._emit("fire_update", {"fires": fire_data})

        # Governance update
        self._emit("governance_update", {
            "viability_index": snapshot.viability_index,
            "c1_safety": snapshot.c1_safety,
            "c2_fairness": snapshot.c2_fairness,
            "c3_stability": snapshot.c3_stability,
            "t_star": snapshot.t_star,
            "active_fires": snapshot.active_fires,
            "total_acres": snapshot.total_acres,
        })

        # Prediction
        if analysis:
            self._emit("prediction", analysis)

        # 24h ML Predictive Risk
        if self.last_predictions:
            self._emit("predictive_risk", {"top_cells": self.last_predictions})

        cycle_time = time.time() - cycle_start

        summary = {
            "cycle": self.cycle_count,
            "active_fires": len(fires),
            "total_acres": changes["total_acres"],
            "viability_index": snapshot.viability_index,
            "t_star": snapshot.t_star,
            "new_fires": len(changes.get("new", [])),
            "escalating": len(changes.get("escalating", [])),
            "dispatches": len(dispatches),
            "cycle_time_ms": round(cycle_time * 1000),
        }

        logger.info(f"✅ Cycle #{self.cycle_count} completed in {cycle_time*1000:.0f}ms")
        return summary

    # ── AI Analysis ───────────────────────────────────────────────────────

    async def _run_ai_analysis(self, fires: list[dict], snapshot: GovernanceSnapshot,
                                changes: dict) -> dict:
        """Run AI-powered risk analysis using OpenAI / Tokito or rule-based fallback."""
        if self._openai:
            return await self._ai_analysis_openai(fires, snapshot, changes)
        else:
            return self._ai_analysis_rules(fires, snapshot, changes)

    async def _ai_analysis_openai(self, fires: list[dict], snapshot: GovernanceSnapshot,
                                  changes: dict) -> dict:
        """Use OpenAI / Tokito API for intelligent risk analysis."""
        try:
            # Sort fires by acres descending and take top 5 critical incidents to prevent context blowup
            sorted_fires = sorted(fires, key=lambda f: f.get("daily_acres", 0) or 0, reverse=True)
            fire_summaries = []
            for fire in sorted_fires[:5]:
                fid = fire["fire_id"]
                alert = snapshot.alert_levels.get(fid, "MONITOR")
                fire_summaries.append({
                    "fire_id": fid,
                    "name": fire.get("name", "Unknown"),
                    "province": fire.get("province", fire.get("state", "Kalimantan")),
                    "acres": fire.get("daily_acres", 0),
                    "hectares": fire.get("hectares", 0),
                    "containment_pct": fire.get("percent_contained", 0),
                    "is_peatland": fire.get("is_peatland", False),
                    "alert_level": alert,
                })

            pred_summary = [
                f"{c['grid_id']} ({c['province']}): Risk={c['calibrated_risk']*100:.1f}%, FRP={c['predicted_frp_mw']} MW, CDD={c.get('consecutive_dry_days', 0)}d"
                for c in self.last_predictions[:3]
            ]

            user_prompt = (
                f"Current monitoring data ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}):\n\n"
                f"VIABILITY INDEX: {snapshot.viability_index:+.4f}\n"
                f"Safety (C1): {snapshot.c1_safety:+.3f} | Fairness (C2): {snapshot.c2_fairness:+.3f} | "
                f"Stability (C3): {snapshot.c3_stability:+.3f}\n"
                f"Predicted time to violation (t*): {snapshot.t_star if snapshot.t_star else 'N/A'}\n\n"
                f"TOP PRIORITY ACTIVE FIRES ({len(fire_summaries)} of {len(fires)} active):\n"
                f"{json.dumps(fire_summaries, indent=2)}\n\n"
                f"24-HOUR PREDICTIVE IGNITION HOTSPOTS:\n"
                f"{json.dumps(pred_summary, indent=2)}\n\n"
                f"CHANGES THIS CYCLE:\n"
                f"- New fires: {len(changes.get('new', []))}\n"
                f"- Escalating: {len(changes.get('escalating', []))}\n"
                f"- Total acres: {changes.get('total_acres', 0):.0f}\n\n"
                f"Analyze the situation and return concise JSON."
            )

            response = await self._openai.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=1500,
            )

            content = response.choices[0].message.content or "{}"
            import re
            content = content.strip()
            if content.startswith('```'):
                content = re.sub(r'^```(?:json)?\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
            content = re.sub(r',\s*}', '}', content)
            content = re.sub(r',\s*]', ']', content)
            content = re.sub(r'//.*?\n', '\n', content)

            try:
                analysis = json.loads(content)
            except Exception:
                # Attempt to extract first complete JSON object if string was truncated
                match = re.search(r'(\{.*\})', content, re.DOTALL)
                if match:
                    analysis = json.loads(match.group(1))
                else:
                    return self._ai_analysis_rules(fires, snapshot, changes)

            # Normalize field variations from LLM output
            raw_text = (
                analysis.get("risk_assessment") or
                analysis.get("analysis") or
                analysis.get("overall_assessment") or
                analysis.get("summary") or
                analysis.get("assessment") or
                "Severe wildfire emergency with multiple active clusters under monitoring."
            )
            analysis["risk_assessment"] = raw_text

            recs = analysis.get("system_recommendation") or analysis.get("recommendations") or analysis.get("recommendation") or analysis.get("action")
            if isinstance(recs, list):
                analysis["system_recommendation"] = " · ".join(str(r) for r in recs)
            elif isinstance(recs, str):
                analysis["system_recommendation"] = recs
            else:
                analysis["system_recommendation"] = "Immediate priority containment and suppression response."

            lvl = str(analysis.get("status") or analysis.get("risk_level") or "").upper()
            score_map = {"CRITICAL": 0.95, "HIGH": 0.75, "MODERATE": 0.5, "MEDIUM": 0.5, "LOW": 0.25}
            if "urgency_score" not in analysis or analysis["urgency_score"] == 0.7:
                analysis["urgency_score"] = score_map.get(lvl, 0.90 if "CRIT" in lvl else 0.75)

            top_list = analysis.get("fire_analyses") or analysis.get("top_priority_fires") or analysis.get("top_fires") or []
            fa = []
            for item in top_list:
                if isinstance(item, dict):
                    fa.append(item)
                elif isinstance(item, str):
                    fa.append({
                        "fire_id": item.split()[0] if item else "UNKNOWN",
                        "fire_name": item,
                        "risk_level": "CRITICAL" if "EMERGENCY" in item.upper() else "HIGH",
                        "predicted_spread": "Likely to expand due to dry conditions and peatland smoldering",
                        "key_concerns": ["Peatland fire cluster", "Low containment"],
                        "recommended_action": "Manggala Agni ground crew dispatch and aerial water bombing"
                    })
            analysis["fire_analyses"] = fa

            await db.log_action(
                "AI_ANALYSIS", None,
                f"AI risk analysis: urgency={analysis.get('urgency_score', 0):.2f}",
                analysis
            )

            self._emit("action", {
                "type": "analysis",
                "message": f"🤖 AI Analysis: {analysis.get('risk_assessment', 'Completed')}",
                "timestamp": time.time(),
            })

            logger.info(f"🤖 AI Analysis: {analysis.get('risk_assessment', 'N/A')}")
            return analysis

        except Exception as e:
            logger.error(f"OpenAI/Tokito analysis error: {e}")
            return self._ai_analysis_rules(fires, snapshot, changes)

    def _ai_analysis_rules(self, fires: list[dict], snapshot: GovernanceSnapshot,
                            changes: dict) -> dict:
        """Rule-based fallback when OpenAI is unavailable."""
        fire_analyses = []
        max_urgency = 0.0

        for fire in fires[:15]:
            acres = fire.get("daily_acres", 0) or 0
            containment = fire.get("percent_contained", 0) or 0
            fid = fire["fire_id"]
            alert = snapshot.alert_levels.get(fid, "MONITOR")

            # Simple risk scoring
            if alert == "EMERGENCY":
                risk = "CRITICAL"
                urgency = 0.95
            elif alert == "WARNING":
                risk = "HIGH"
                urgency = 0.7
            elif alert == "WATCH":
                risk = "MODERATE"
                urgency = 0.4
            else:
                risk = "LOW"
                urgency = 0.1

            max_urgency = max(max_urgency, urgency)

            concerns = []
            if acres > 5000:
                concerns.append(f"Large fire at {acres:.0f} acres")
            if containment < 20:
                concerns.append(f"Very low containment ({containment:.0f}%)")
            if not concerns:
                concerns.append("Being monitored")

            fire_analyses.append({
                "fire_id": fid,
                "fire_name": fire.get("name", "Unknown"),
                "risk_level": risk,
                "predicted_spread": f"{'Likely to grow' if containment < 30 else 'Containment progressing'}",
                "key_concerns": concerns,
                "recommended_action": f"{'Immediate response needed' if risk in ('CRITICAL', 'HIGH') else 'Continue monitoring'}"
            })

        # Overall assessment
        emergency_count = sum(1 for f in fires if snapshot.alert_levels.get(f["fire_id"]) == "EMERGENCY")
        total_acres = sum((f.get("daily_acres", 0) or 0) for f in fires)

        if emergency_count > 0:
            assessment = f"CRITICAL: {emergency_count} fires at emergency level. {total_acres:.0f} total acres burning."
        elif snapshot.viability_index < 0:
            assessment = f"WARNING: Viability Index negative ({snapshot.viability_index:+.3f}). System approaching safety boundary."
        elif len(changes.get("escalating", [])) > 0:
            assessment = f"ELEVATED: {len(changes['escalating'])} fires escalating. Close monitoring required."
        else:
            assessment = f"STABLE: {len(fires)} fires under monitoring. {total_acres:.0f} acres."

        analysis = {
            "risk_assessment": assessment,
            "fire_analyses": fire_analyses,
            "system_recommendation": "Maintain current monitoring cadence" if max_urgency < 0.5 else "Increase monitoring frequency and prepare response resources",
            "urgency_score": round(max_urgency, 2),
            "reasoning": f"Rule-based analysis. VI={snapshot.viability_index:+.4f}, {len(fires)} active fires, {total_acres:.0f} acres."
        }

        self._emit("action", {
            "type": "analysis",
            "message": f"📊 Analysis (rule-based): {assessment}",
            "timestamp": time.time(),
        })

        return analysis

    # ── Emergency Dispatch ────────────────────────────────────────────────

    async def _check_dispatches(self, fires: list[dict], snapshot: GovernanceSnapshot,
                                 analysis: Optional[dict]) -> list[DispatchReport]:
        """Check if any fires require emergency dispatch."""
        dispatches = []
        emergency_ids = set(self.governance.get_emergency_fires()) | {
            fid for fid, lvl in snapshot.alert_levels.items()
            if str(lvl).upper() == "EMERGENCY"
        }

        for fire in fires:
            fid = fire["fire_id"]
            if fid not in emergency_ids:
                continue

            if not self.dispatcher.can_dispatch(fid):
                continue

            # Get AI analysis for this specific fire
            fire_analysis = None
            if analysis and analysis.get("fire_analyses"):
                for fa in analysis["fire_analyses"]:
                    if fa.get("fire_id") == fid:
                        fire_analysis = fa
                        break

            alert_level = snapshot.alert_levels.get(fid, "EMERGENCY")
            report = self.dispatcher.dispatch(fire, alert_level, fire_analysis)
            dispatches.append(report)

            # Save to database
            await db.save_alert(
                fid, alert_level,
                f"Emergency dispatch {report.dispatch_id} for {fire.get('name', 'Unknown')}",
                dispatched=True,
                dispatch_details=report.to_dict()
            )

            await db.log_action(
                "EMERGENCY_DISPATCH", fid,
                f"Dispatched {report.dispatch_id}: {report.severity} response for {fire.get('name')}",
                report.to_dict()
            )

            # Emit dispatch event
            self._emit("dispatch", {
                "dispatch_id": report.dispatch_id,
                "fire_name": report.fire_name,
                "severity": report.severity,
                "priority_code": report.priority_code,
                "resources": [r["display"] for r in report.resources_deployed],
                "total_personnel": report.total_personnel,
                "response_time_min": report.estimated_response_time_min,
                "evacuation": report.evacuation_advisory,
                "station": report.nearest_station,
                "timestamp": time.time(),
            })

            self._emit("action", {
                "type": "dispatch",
                "message": (
                    f"🚨 EMERGENCY DISPATCH {report.dispatch_id}: "
                    f"{report.fire_name} — {report.severity} — "
                    f"{report.total_personnel} personnel deployed"
                ),
                "timestamp": time.time(),
                "fire_id": fid,
            })

            # Record action for governance stability tracking
            self.governance.record_action({
                "type": "dispatch",
                "fire_id": fid,
                "severity": report.severity,
            })

        return dispatches

    async def close(self):
        """Clean up resources."""
        await self.fetcher.close()
        await self.jev.close()

    def get_state(self) -> dict:
        """Get current agent state for API."""
        return {
            "cycle_count": self.cycle_count,
            "fires": list(self.fetcher.current_fires.values()),
            "governance": self.governance.to_dict(),
            "jev": self.jev.to_dict(),
            "last_analysis": self.last_analysis,
            "last_predictions": self.last_predictions,
            "has_predictor": self.predictor.is_ready if self.predictor else False,
            "last_jev_decision": self.last_jev_decision.to_dict() if self.last_jev_decision else None,
            "recent_dispatches": self.dispatcher.get_recent_dispatches(),
        }
