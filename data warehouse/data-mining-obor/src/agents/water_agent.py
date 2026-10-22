"""Forwarding shim to src.agents.water_agent."""
from src.agents.water_agent import WaterResourceAgent, haversine_km, _resolve_default_db_path

__all__ = ["WaterResourceAgent", "haversine_km", "_resolve_default_db_path"]
