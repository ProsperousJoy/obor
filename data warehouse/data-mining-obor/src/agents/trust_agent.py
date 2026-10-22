"""
Module 2 — Trust Supervisor Agent
---------------------------------
Evaluates prediction reliability, cross-sensor agreement, data health,
and determines if autonomous action is safe or human verification is required.
"""

from typing import Dict, Any, List
import numpy as np

class TrustSupervisor:
    """
    Evaluates: 'Can I trust this fire prediction?'
    Cross-checks sensor inputs (VIIRS, Himawari, Weather) and data quality.
    """
    def __init__(self, high_trust_threshold: float = 0.80, low_trust_threshold: float = 0.50):
        self.high_trust_threshold = high_trust_threshold
        self.low_trust_threshold = low_trust_threshold

    def evaluate_trust(
        self,
        incident_id: str,
        fire_prediction: Dict[str, Any],
        viirs_evidence: Dict[str, Any],
        himawari_evidence: Dict[str, Any] = None,
        weather_evidence: Dict[str, Any] = None,
        data_freshness_minutes: int = 15
    ) -> Dict[str, Any]:
        """
        Assesses cross-sensor agreement, data quality, and model confidence.
        """
        reasons = []
        
        # 1. Evidence Trust (Cross-Sensor Concordance)
        viirs_conf = viirs_evidence.get("confidence", "nominal")
        viirs_frp = float(viirs_evidence.get("frp", 0.0))
        
        # Base evidence score from VIIRS
        if viirs_conf in ["h", "high"]:
            evidence_score = 0.90
            reasons.append("VIIRS detection confidence is HIGH")
        elif viirs_conf in ["n", "nominal"]:
            evidence_score = 0.75
            reasons.append("VIIRS detection confidence is NOMINAL")
        else:
            evidence_score = 0.55
            reasons.append("VIIRS detection confidence is LOW")

        if viirs_frp >= 20.0:
            evidence_score = min(1.0, evidence_score + 0.08)
            reasons.append(f"Significant Fire Radiative Power ({viirs_frp:.1f} MW)")

        # Himawari cross-check
        agreement_desc = "VIIRS detection only"
        if himawari_evidence and himawari_evidence.get("thermal_anomaly"):
            evidence_score = min(1.0, evidence_score + 0.10)
            agreement_desc = "VIIRS and Himawari concordant thermal anomaly"
            reasons.append("Himawari confirmed thermal anomaly")
            if himawari_evidence.get("persistence_1h"):
                reasons.append("Thermal anomaly persisted over 1 hour")

        # 2. Data Health Score
        data_health = 1.0
        if data_freshness_minutes > 60:
            penalty = min(0.35, (data_freshness_minutes - 60) / 180.0)
            data_health -= penalty
            reasons.append(f"Data freshness latency: {data_freshness_minutes}m old")
        else:
            reasons.append(f"Data freshness optimal ({data_freshness_minutes}m old)")

        # 3. Model Reliability
        fire_prob = float(fire_prediction.get("fire_probability", 0.5))
        # Distance from decision boundary uncertainty (0.5)
        certainty = 1.0 - 2.0 * abs(0.5 - fire_prob)
        model_reliability = 0.85 - (0.20 * certainty)

        # 4. Overall Trust Calculation
        overall_trust = round(float(0.45 * evidence_score + 0.30 * data_health + 0.25 * model_reliability), 2)

        # 5. OOD (Out-Of-Distribution) check
        lat = fire_prediction.get("lat", 0.0)
        lon = fire_prediction.get("lon", 0.0)
        is_in_borneo = (-5.0 <= lat <= 7.0) and (108.0 <= lon <= 119.0)
        ood_status = "IN_DISTRIBUTION" if is_in_borneo else "OOD_CONFIRMED"
        if not is_in_borneo:
            overall_trust = min(0.30, overall_trust)
            reasons.append("Coordinates outside Kalimantan operational bounds")

        # Trust Level & Action Permissions
        if overall_trust >= self.high_trust_threshold:
            trust_level = "HIGH"
            autonomous_action_allowed = True
            human_verification_required = False
        elif overall_trust >= self.low_trust_threshold:
            trust_level = "MEDIUM"
            autonomous_action_allowed = False
            human_verification_required = True
        else:
            trust_level = "LOW"
            autonomous_action_allowed = False
            human_verification_required = True

        return {
            "incident_id": incident_id,
            "evidence_trust": round(evidence_score, 2),
            "model_reliability": round(model_reliability, 2),
            "data_health": round(data_health, 2),
            "overall_trust": overall_trust,
            "evidence_agreement": agreement_desc,
            "ood_status": ood_status,
            "trust_level": trust_level,
            "autonomous_action_allowed": autonomous_action_allowed,
            "human_verification_required": human_verification_required,
            "reasons": reasons
        }
