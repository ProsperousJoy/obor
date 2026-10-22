"""Forwarding shim to src.agents.execution_agent."""
from src.agents.execution_agent import ExecutionAgent, _resolve_default_db_path

__all__ = ["ExecutionAgent", "_resolve_default_db_path"]
