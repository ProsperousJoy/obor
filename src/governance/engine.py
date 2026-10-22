"""AVF Governance Engine — Implements the Agent Viability Framework.
Implements:
  P1 (Monitoring):   Continuous tracking of fire state deltas
  P2 (Anticipation): OLS-based t* prediction for time-to-violation
  P3 (Monotonic Restriction): Alert levels can only escalate, never downgrade

Viability Index VI(t) ∈ [-1, +1] computed from three constraint channels:
  C1 (Safety):    Fire risk metric drift relative to safe baselines
  C2 (Fairness):  Attention distribution across fires (no blind spots)
  C3 (Stability): Agent decision consistency over time
"""

from collections import deque
from dataclasses import dataclass, field
import logging
import time
from typing import Optional
import numpy as np

from src.config import config
from src.governance.alerts import AlertLevel

logger = logging.getLogger("wildfire.governance")


@dataclass
class GovernanceSnapshot:
    """Point-in-time governance state."""
    timestamp: float
    viability_index: float    # VI(t) ∈ [-1, +1]
    c1_safety: float          # Safety constraint distance
    c2_fairness: float        # Fairness constraint distance
    c3_stability: float       # Stability constraint distance
    t_star: Optional[float]   # Predicted time-to-violation (seconds)
    active_fires: int
    total_acres: float
    alert_levels: dict[str, str] = field(default_factory=dict)  # fire_id → AlertLevel name


@dataclass
class FireGovernanceState:
    """Per-fire governance tracking."""
    fire_id: str
    alert_level: AlertLevel = AlertLevel.MONITOR
    acre_history: deque = field(default_factory=lambda: deque(maxlen=50))
    containment_history: deque = field(default_factory=lambda: deque(maxlen=50))
    escalation_history: deque = field(default_factory=lambda: deque(maxlen=20))
    last_escalation_time: float = 0.0
    escalation_count: int = 0


class GovernanceEngine:
    """
    Agent Viability Framework (AVF) governance engine.

    Computes VI(t) from three constraint channels and predicts t*
    (time until the viability boundary is crossed).
    """

    def __init__(self):
        # Per-fire state tracking
        self.fire_states: dict[str, FireGovernanceState] = {}

        # VI history for t* prediction (P2: Anticipation)
        self.vi_history: deque[tuple[float, float]] = deque(maxlen=config.AVF_WINDOW_SIZE * 3)

        # Agent action history for C3 (Stability)
        self.action_history: deque[dict] = deque(maxlen=100)

        # Constraint weights (from paper: weighted sum for VI)
        self.w1 = 0.5   # Safety weight (highest priority)
        self.w2 = 0.2   # Fairness weight
        self.w3 = 0.3   # Stability weight

        # Previous snapshot for change detection
        self._prev_snapshot: Optional[GovernanceSnapshot] = None

    def evaluate(self, fires: list[dict], changes: dict) -> GovernanceSnapshot:
        """
        Run the full governance evaluation pipeline:
          S1: Update per-fire state tracking (Monitoring / P1)
          S2: Compute C1 (Safety) constraint distance
          S3: Compute C2 (Fairness) constraint distance
          S4: Compute C3 (Stability) constraint distance
          S5: Compute VI(t) from weighted constraints
          S6: Predict t* via OLS regression (Anticipation / P2)
          S7: Apply monotonic alert level transitions (Restriction / P3)
        """
        now = time.time()

        # ── S1: Update per-fire state (P1: Monitoring) ──
        self._update_fire_states(fires)

        # ── S2: C1 — Safety Constraint ──
        c1 = self._compute_c1_safety(fires, changes)

        # ── S3: C2 — Fairness Constraint ──
        c2 = self._compute_c2_fairness(fires)

        # ── S4: C3 — Stability Constraint ──
        c3 = self._compute_c3_stability()

        # ── S5: Compute VI(t) ──
        vi = self._compute_vi(c1, c2, c3)

        # ── S6: Predict t* (P2: Anticipation) ──
        self.vi_history.append((now, vi))
        t_star = self._predict_t_star()

        # ── S7: Determine alert levels (P3: Monotonic Restriction) ──
        alert_levels = self._apply_monotonic_alerts(fires, vi)

        total_acres = sum((f.get("daily_acres", 0) or 0) for f in fires)

        snapshot = GovernanceSnapshot(
            timestamp=now,
            viability_index=vi,
            c1_safety=c1,
            c2_fairness=c2,
            c3_stability=c3,
            t_star=t_star,
            active_fires=len(fires),
            total_acres=total_acres,
            alert_levels=alert_levels,
        )

        self._prev_snapshot = snapshot
        return snapshot

    def _update_fire_states(self, fires: list[dict]):
        """Track per-fire metrics over time (P1: Monitoring)."""
        current_ids = set()
        for fire in fires:
            fid = fire["fire_id"]
            current_ids.add(fid)

            if fid not in self.fire_states:
                self.fire_states[fid] = FireGovernanceState(fire_id=fid)

            state = self.fire_states[fid]
            state.acre_history.append(fire.get("daily_acres", 0) or 0)
            state.containment_history.append(fire.get("percent_contained", 0) or 0)

        # Clean up fires that are no longer active
        stale = set(self.fire_states.keys()) - current_ids
        for fid in stale:
            del self.fire_states[fid]

    def _compute_c1_safety(self, fires: list[dict], changes: dict) -> float:
        """
        Compute safety constraint distance for tropical Kalimantan fires.
        Returns distance ∈ [-1, +1] where +1 is safe, -1 is maximally unsafe.
        """
        if not fires:
            return 1.0  # No fires = maximum safety

        penalties = []

        for fire in fires:
            acres = fire.get("daily_acres", 0) or 0
            containment = fire.get("percent_contained", 0) or 0
            is_peat = fire.get("is_peatland", False)

            # Penalty for large fires
            acre_penalty = min(acres / 25000.0, 1.0) * 0.40

            # Penalty for low containment
            containment_penalty = max(0.0, (100.0 - containment) / 100.0) * 0.35

            # Peatland vulnerability penalty: deep smoldering carbon sink risk
            peat_penalty = 0.25 if (is_peat and containment < 50) else (0.10 if is_peat else 0.0)

            fire_risk = acre_penalty + containment_penalty + peat_penalty
            penalties.append(fire_risk)

        max_risk = max(penalties)
        avg_risk = sum(penalties) / len(penalties)
        count_factor = min(len(fires) / 50.0, 1.0)

        new_fires = changes.get("new", [])
        is_initial_load = len(new_fires) >= len(fires) * 0.8 and len(fires) > 5

        escalation_penalty = min(0.3, len(changes.get("escalating", [])) * 0.05)
        new_fire_penalty = 0.0 if is_initial_load else min(0.3, len(new_fires) * 0.05)

        total_risk = (
            0.35 * max_risk +
            0.45 * avg_risk +
            0.20 * count_factor +
            escalation_penalty +
            new_fire_penalty
        )

        c1 = max(-1.0, min(1.0, 1.0 - total_risk))
        return round(c1, 4)

    def _compute_c2_fairness(self, fires: list[dict]) -> float:
        """
        Compute fairness constraint distance across Kalimantan's 5 provinces.
        Returns distance ∈ [-1, +1] where +1 is perfectly fair.
        """
        if not fires or len(fires) <= 1:
            return 1.0

        prov_fires: dict[str, list[dict]] = {}
        for fire in fires:
            prov = fire.get("province", fire.get("state", "Unknown"))
            prov_fires.setdefault(prov, []).append(fire)

        prov_containments = []
        for prov, p_fires in prov_fires.items():
            avg_cont = sum((f.get("percent_contained", 0) or 0) for f in p_fires) / len(p_fires)
            prov_containments.append(avg_cont)

        prov_disparity = float(np.std(prov_containments)) / 100.0 if len(prov_containments) > 1 else 0.0

        neglected_count = 0
        for fire in fires:
            fid = fire.get("fire_id")
            state = self.fire_states.get(fid)
            acres = fire.get("daily_acres", 0) or 0
            is_peat = fire.get("is_peatland", False)

            if state and len(state.containment_history) >= 3:
                recent_conts = list(state.containment_history)[-3:]
                if all(c < 5 for c in recent_conts) and (is_peat or acres > 500):
                    neglected_count += 1

        neglect_ratio = neglected_count / len(fires)
        c2 = 1.0 - (neglect_ratio * 1.0) - (prov_disparity * 0.5)
        return max(-1.0, min(1.0, round(c2, 4)))

    def _compute_c3_stability(self) -> float:
        """
        Compute stability constraint distance using a 15-minute rolling window.
        Returns distance ∈ [-1, +1] where +1 is stable.
        """
        if not self.fire_states:
            return 1.0

        now = time.time()
        window_sec = 900
        n_fires = max(len(self.fire_states), 1)

        recent_escalations = 0
        rapid_churn_fires = 0

        for s in self.fire_states.values():
            recent_times = [t for t in s.escalation_history if (now - t) <= window_sec]
            recent_escalations += len(recent_times)
            if len(recent_times) >= 2:
                rapid_churn_fires += 1

        churn_ratio = rapid_churn_fires / n_fires
        escalation_pressure = min(1.0, recent_escalations / (n_fires * 1.5))

        c3 = 1.0 - (churn_ratio * 1.2) - (escalation_pressure * 0.4)
        return max(-1.0, min(1.0, round(c3, 4)))

    def _compute_vi(self, c1: float, c2: float, c3: float) -> float:
        """Compute the scalar Viability Index VI(t) ∈ [-1, +1]."""
        vi = (
            self.w1 * np.clip(c1, -1, 1) +
            self.w2 * np.clip(c2, -1, 1) +
            self.w3 * np.clip(c3, -1, 1)
        ) / (self.w1 + self.w2 + self.w3)

        return round(float(vi), 4)

    def _predict_t_star(self) -> Optional[float]:
        """Predict time-to-violation t* using OLS over a rolling window."""
        if len(self.vi_history) < 5:
            return None

        window = list(self.vi_history)[-config.AVF_WINDOW_SIZE:]
        if len(window) < 5:
            return None

        times = np.array([t for t, _ in window])
        vis = np.array([v for _, v in window])

        t0 = times[0]
        times_rel = times - t0

        try:
            n = len(times_rel)
            sum_t = np.sum(times_rel)
            sum_v = np.sum(vis)
            sum_tv = np.sum(times_rel * vis)
            sum_t2 = np.sum(times_rel ** 2)

            denom = n * sum_t2 - sum_t ** 2
            if abs(denom) < 1e-12:
                return None

            b = (n * sum_tv - sum_t * sum_v) / denom

            current_vi = vis[-1]

            if b < -1e-8 and current_vi > 0:
                t_star = -current_vi / b
                return round(float(t_star), 1)
            elif b < -1e-8 and current_vi <= 0:
                return 0.0
            else:
                return None

        except Exception as e:
            logger.warning(f"t* prediction error: {e}")
            return None

    def _apply_monotonic_alerts(self, fires: list[dict], vi: float) -> dict[str, str]:
        """Apply monotonic alert level transitions (P3)."""
        alert_levels = {}

        for fire in fires:
            fid = fire["fire_id"]
            state = self.fire_states.get(fid)
            if not state:
                continue

            new_level = self._assess_fire_alert(fire, vi)

            # P3: Monotonic restriction — can only escalate
            if new_level > state.alert_level:
                old_name = state.alert_level.name
                now = time.time()
                state.alert_level = new_level
                state.escalation_count += 1
                state.last_escalation_time = now
                state.escalation_history.append(now)
                logger.info(
                    f"⬆️  Alert ESCALATED for {fire['name']}: "
                    f"{old_name} → {new_level.name}"
                )

            alert_levels[fid] = state.alert_level.name

        return alert_levels

    def _assess_fire_alert(self, fire: dict, vi: float) -> AlertLevel:
        """Determine the appropriate alert level for a single fire."""
        acres = fire.get("daily_acres", 0) or 0
        containment = fire.get("percent_contained", 0) or 0
        fid = fire["fire_id"]
        state = self.fire_states.get(fid)

        growth_rate = 0
        if state and len(state.acre_history) >= 3:
            recent = list(state.acre_history)[-3:]
            growth_rate = recent[-1] - recent[0]

        is_peat = fire.get("is_peatland", False)

        # EMERGENCY
        if (acres > config.ACRES_CRITICAL and containment < config.CONTAINMENT_LOW) or \
           (is_peat and acres > 1000 and containment < 25) or \
           (growth_rate > config.GROWTH_RATE_HIGH) or \
           (vi <= config.VI_WARNING_THRESHOLD and acres > 1000):
            return AlertLevel.EMERGENCY

        # WARNING
        if (acres > config.ACRES_CRITICAL * 0.5 and containment < 40) or \
           (is_peat and acres > 300 and containment < 40) or \
           (growth_rate > config.GROWTH_RATE_HIGH * 0.5) or \
           (vi <= config.VI_WATCH_THRESHOLD and acres > 500):
            return AlertLevel.WARNING

        # WATCH
        if (acres > 500 and containment < 60) or \
           (is_peat and acres > 100) or \
           (growth_rate > 100) or \
           (vi <= config.VI_MONITOR_THRESHOLD):
            return AlertLevel.WATCH

        # MONITOR
        return AlertLevel.MONITOR

    def get_fire_alert_level(self, fire_id: str) -> AlertLevel:
        """Get the current alert level for a specific fire."""
        state = self.fire_states.get(fire_id)
        return state.alert_level if state else AlertLevel.MONITOR

    def get_emergency_fires(self) -> list[str]:
        """Get list of fire_ids at EMERGENCY level."""
        return [
            fid for fid, state in self.fire_states.items()
            if state.alert_level == AlertLevel.EMERGENCY
        ]

    def record_action(self, action: dict):
        """Record an agent action for stability tracking (C3)."""
        self.action_history.append({**action, "timestamp": time.time()})

    def to_dict(self) -> dict:
        """Serialize current governance state for API/dashboard."""
        latest = self._prev_snapshot
        if not latest:
            return {
                "viability_index": 1.0,
                "c1_safety": 1.0,
                "c2_fairness": 1.0,
                "c3_stability": 1.0,
                "t_star": None,
                "active_fires": 0,
                "total_acres": 0,
                "alert_levels": {},
                "vi_history": [],
            }

        return {
            "viability_index": latest.viability_index,
            "c1_safety": latest.c1_safety,
            "c2_fairness": latest.c2_fairness,
            "c3_stability": latest.c3_stability,
            "t_star": latest.t_star,
            "active_fires": latest.active_fires,
            "total_acres": latest.total_acres,
            "alert_levels": latest.alert_levels,
            "vi_history": [
                {"timestamp": t, "vi": v}
                for t, v in list(self.vi_history)[-50:]
            ],
        }
