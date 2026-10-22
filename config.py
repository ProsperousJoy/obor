"""Root compatibility facade for configuration management.
Re-exports from src.config.
"""

from src.config import Config, config, PROJECT_ROOT

__all__ = ["Config", "config", "PROJECT_ROOT"]
