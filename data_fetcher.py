"""Root compatibility facade for WildfireDataFetcher.
Re-exports from src.data.
"""

from src.data import (
    PROVINCE_REGIONS,
    resolve_location,
    assign_grid_id,
    cluster_hotspots,
    WildfireDataFetcher,
    BORNEO_DEMO_FIRES,
    _evolve_demo_fire,
)

__all__ = [
    "PROVINCE_REGIONS",
    "resolve_location",
    "assign_grid_id",
    "cluster_hotspots",
    "WildfireDataFetcher",
    "BORNEO_DEMO_FIRES",
    "_evolve_demo_fire",
]
