"""Root compatibility facade for WildfireAgent.
Re-exports from src.agents.orchestrator.
"""

from src.agents.orchestrator import (
    WildfireAgent,
    SYSTEM_PROMPT,
)

__all__ = ["WildfireAgent", "SYSTEM_PROMPT"]
