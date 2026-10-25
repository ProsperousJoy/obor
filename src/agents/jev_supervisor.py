"""Jev AI Supervisor — Structured decision-making via TypeSafe's Jev model."""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
import httpx

from src.config import config

logger = logging.getLogger("wildfire.jev")


@dataclass
class JevDecision:
    """Structured output from a Jev decision evaluation cycle."""
    timestamp: float

    # noul questions — probability values in [0, 1]
    is_immediate_threat: float = 0.0
    requires_emergency_dispatch: float = 0.0
    avf_override_recommended: float = 0.0

    # choice question — response level
    recommended_response_level: str = "MONITOR"
    response_level_probabilities: dict = field(default_factory=dict)
    response_level_confidence: float = 0.0

    # score question — overall severity
    overall_severity_score: float = 0.0
    severity_distribution: dict = field(default_factory=dict)
    severity_confidence: float = 0.0

    # metadata
    raw_response: Optional[dict] = None
    latency_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize for API / SSE / database."""
        return {
            "timestamp": self.timestamp,
            "is_immediate_threat": self.is_immediate_threat,
            "requires_emergency_dispatch": self.requires_emergency_dispatch,
            "avf_override_recommended": self.avf_override_recommended,
            "recommended_response_level": self.recommended_response_level,
            "response_level_probabilities": self.response_level_probabilities,
            "response_level_confidence": self.response_level_confidence,
            "overall_severity_score": self.overall_severity_score,
            "severity_distribution": self.severity_distribution,
            "severity_confidence": self.severity_confidence,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


class JevSupervisor:
    """
    Jev AI decision supervisor — parallel to AVF governance.
    """

    def __init__(self):
        self.api_key: str = config.JEV_API_KEY
        self.api_url: str = config.JEV_API_URL
        self.model: str = config.JEV_MODEL
        self.client: httpx.AsyncClient = httpx.AsyncClient(timeout=15.0)

        self.decision_history: list[JevDecision] = []
        self._enabled: bool = bool(self.api_key)
        self.last_decision: JevDecision = self._fallback_decision(error=None if self._enabled else "STANDBY")
        self.decision_history.append(self.last_decision)

        if self._enabled:
            logger.info("🧠 Jev AI Supervisor initialized")
        else:
            logger.warning("⚠️  Jev API key not set — Jev supervisor disabled")

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def evaluate(
        self, fires: list[dict], avf_snapshot, changes: dict
    ) -> JevDecision:
        """Run a full Jev decision evaluation against current fire state."""
        if not self._enabled:
            fallback = self._fallback_decision(error="STANDBY")
            self.last_decision = fallback
            return fallback

        start = time.time()
        try:
            state = self._build_state(fires, avf_snapshot, changes)

            payload = {
                "model": self.model,
                "state": state,
                "questions": {
                    "is_immediate_threat": {
                        "type": "noul",
                        "instructions": (
                            "Does the wildfire situation pose an immediate threat to life, "
                            "critical infrastructure, or settlements within 6 hours?"
                        ),
                    },
                    "requires_emergency_dispatch": {
                        "type": "noul",
                        "instructions": (
                            "Should emergency resources be dispatched immediately based on "
                            "uncontained fires, growth rate, and Viability Index trend?"
                        ),
                    },
                    "avf_override_recommended": {
                        "type": "noul",
                        "instructions": (
                            "Should the automated AVF governance be overridden due to "
                            "underestimated risk or rapid situation escalation?"
                        ),
                    },
                    "recommended_response_level": {
                        "type": "choice",
                        "instructions": "Select system-wide response level based on aggregate fire risk.",
                        "criteria": {
                            "MONITOR": "Routine tracking, small or contained fires",
                            "WATCH": "Elevated attention, growing fires or low containment",
                            "WARNING": "Significant risk, active uncontained spread",
                            "EMERGENCY": "Immediate danger, urgent emergency response required"
                        },
                    },
                    "overall_severity": {
                        "type": "score",
                        "instructions": "Rate overall severity of current wildfire situation.",
                        "criteria": [
                            "LOW - Minimal active fire activity",
                            "MODERATE - Contained or isolated fires with manageable risk",
                            "HIGH - Multiple growing fires or significant spread rate",
                            "CRITICAL - Out-of-control fires with catastrophic potential"
                        ],
                    },
                },
            }

            response = await self.client.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            latency = (time.time() - start) * 1000
            decision = self._parse_response(data, latency)

            self.last_decision = decision
            self.decision_history.append(decision)

            if len(self.decision_history) > 100:
                self.decision_history = self.decision_history[-100:]

            logger.info(
                f"🧠 Jev Decision: "
                f"threat={decision.is_immediate_threat:.2f} "
                f"dispatch={decision.requires_emergency_dispatch:.2f} "
                f"override={decision.avf_override_recommended:.2f} "
                f"level={decision.recommended_response_level} "
                f"severity={decision.overall_severity_score:.1f} "
                f"({latency:.0f}ms)"
            )

            return decision

        except httpx.HTTPStatusError as e:
            latency = (time.time() - start) * 1000
            logger.error(f"Jev API HTTP error {e.response.status_code}: {e.response.text[:200]}")
            fallback = self._fallback_decision(
                error=f"HTTP {e.response.status_code}", latency=latency
            )
            self.last_decision = fallback
            self.decision_history.append(fallback)
            return fallback
        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.error(f"Jev evaluation error: {e}")
            fallback = self._fallback_decision(error=str(e), latency=latency)
            self.last_decision = fallback
            self.decision_history.append(fallback)
            return fallback

    def _build_state(self, fires: list[dict], avf_snapshot, changes: dict) -> str:
        """Build a compact, token-efficient state string for Jev evaluation."""
        total_ha = changes.get("total_hectares", changes.get("total_acres", 0) / 2.47105)
        lines = [
            "REGION: Kalimantan / Borneo (Indonesia)",
            f"VI={avf_snapshot.viability_index:+.3f} | C1_Safety={avf_snapshot.c1_safety:+.2f} | "
            f"C2_Fairness={avf_snapshot.c2_fairness:+.2f} | C3_Stability={avf_snapshot.c3_stability:+.2f} | "
            f"t*={avf_snapshot.t_star if avf_snapshot.t_star is not None else 'inf'}s",
            f"Active fires: {len(fires)} | Total area: {total_ha:.0f} ha | "
            f"New: {len(changes.get('new', []))} | Escalating: {len(changes.get('escalating', []))}",
        ]

        sorted_fires = sorted(
            fires,
            key=lambda f: (f.get("hectares", f.get("daily_acres", 0) / 2.47105) or 0) * (1.0 - (f.get("percent_contained", 0) or 0) / 100.0),
            reverse=True
        )[:5]

        if sorted_fires:
            lines.append("Top Priority Incidents:")
            for fire in sorted_fires:
                fid = fire.get("fire_id", "?")
                name = fire.get("name", "Unknown")
                ha = fire.get("hectares", fire.get("daily_acres", 0) / 2.47105)
                cont = fire.get("percent_contained", 0) or 0
                is_peat = fire.get("is_peatland", False)
                county = fire.get("county", "?")
                alert = avf_snapshot.alert_levels.get(fid, "MONITOR")
                lines.append(f" • {name} ({county}): {ha:.0f}ha, {cont:.0f}% cont, alert={alert}, peat={'YES' if is_peat else 'No'}")

        return "\n".join(lines)

    def _parse_response(self, data: dict, latency: float) -> JevDecision:
        """Parse Jev API response into a JevDecision dataclass."""
        answers = data.get("answers", {})

        threat_answer = answers.get("is_immediate_threat", {})
        dispatch_answer = answers.get("requires_emergency_dispatch", {})
        override_answer = answers.get("avf_override_recommended", {})

        response_answer = answers.get("recommended_response_level", {})
        severity_answer = answers.get("overall_severity", {})

        choice_level = response_answer.get("choice") or response_answer.get("selected", "MONITOR")
        severity_dist = severity_answer.get("probabilities") or severity_answer.get("distribution", {})

        return JevDecision(
            timestamp=time.time(),
            is_immediate_threat=float(threat_answer.get("noul", 0.0)),
            requires_emergency_dispatch=float(dispatch_answer.get("noul", 0.0)),
            avf_override_recommended=float(override_answer.get("noul", 0.0)),
            recommended_response_level=str(choice_level),
            response_level_probabilities=response_answer.get("probabilities", {}),
            response_level_confidence=float(response_answer.get("confidence", 0.0)),
            overall_severity_score=float(severity_answer.get("score", 0.0)),
            severity_distribution=severity_dist,
            severity_confidence=float(severity_answer.get("confidence", 0.0)),
            raw_response=data,
            latency_ms=latency,
        )

    def _fallback_decision(
        self, error: Optional[str] = None, latency: float = 0.0
    ) -> JevDecision:
        """Return a neutral/conservative fallback when Jev is unavailable."""
        return JevDecision(
            timestamp=time.time(),
            is_immediate_threat=0.0,
            requires_emergency_dispatch=0.0,
            avf_override_recommended=0.0,
            recommended_response_level="MONITOR",
            response_level_probabilities={
                "MONITOR": 1.0, "WATCH": 0.0, "WARNING": 0.0, "EMERGENCY": 0.0
            },
            response_level_confidence=0.0,
            overall_severity_score=0.0,
            severity_distribution={
                "LOW": 1.0, "MODERATE": 0.0, "HIGH": 0.0, "CRITICAL": 0.0
            },
            severity_confidence=0.0,
            latency_ms=latency,
            error=error,
        )

    def to_dict(self) -> dict:
        """Serialize current Jev supervisor state for API / dashboard."""
        decision = self.last_decision or self._fallback_decision(error=None if self._enabled else "STANDBY")
        return {
            "enabled": self._enabled,
            "total_decisions": len(self.decision_history),
            "last_decision": decision.to_dict(),
            "decision_history": [
                {
                    "timestamp": d.timestamp,
                    "is_immediate_threat": d.is_immediate_threat,
                    "recommended_response_level": d.recommended_response_level,
                    "overall_severity_score": d.overall_severity_score,
                }
                for d in self.decision_history[-20:]
            ],
        }

    async def close(self):
        """Clean up the HTTP client."""
        await self.client.aclose()
