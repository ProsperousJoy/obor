"""Data ingestion and spatial analysis package."""

from src.data.spatial import (
    PROVINCE_REGIONS,
    resolve_location,
    assign_grid_id,
    cluster_hotspots,
)
from src.data.fetcher import (
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
