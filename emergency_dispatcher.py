"""Root compatibility facade for EmergencyDispatcher.
Re-exports from src.agents.dispatcher.
"""

from src.agents.dispatcher import (
    haversine_km,
    MANGGALA_AGNI_DAOPS,
    STRATEGIC_WATER_SOURCES,
    RESOURCE_TYPES,
    DispatchReport,
    EmergencyDispatcher,
)

__all__ = [
    "haversine_km",
    "MANGGALA_AGNI_DAOPS",
    "STRATEGIC_WATER_SOURCES",
    "RESOURCE_TYPES",
    "DispatchReport",
    "EmergencyDispatcher",
]
