"""Forwarding shim to src.agents.impact_agent."""
from src.agents.impact_agent import ImpactAgent, haversine_km, _resolve_default_db_path

__all__ = ["ImpactAgent", "haversine_km", "_resolve_default_db_path"]
