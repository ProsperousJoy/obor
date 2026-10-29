"""Configuration management for the Wildfire Monitoring Agent.
Loads settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Points to repository root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # Project paths
    PROJECT_ROOT: Path = PROJECT_ROOT

    # OpenAI / Tokito API
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.tokito.xyz/v1")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "auto")

    # Jev AI Supervisor (TypeSafe SystemOne API)
    JEV_API_KEY: str = os.getenv("JEV_API_KEY", "")
    JEV_API_URL: str = os.getenv("JEV_API_URL", "https://api.typesafe.ai/v1/systemone")
    JEV_MODEL: str = os.getenv("JEV_MODEL", "jev-latest")
    JEV_OVERRIDE_THRESHOLD: float = float(os.getenv("JEV_OVERRIDE_THRESHOLD", "0.85"))

    # Polling
    POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "60"))

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Database (SQLite Operational Store)
    DB_PATH: str = os.getenv(
        "DB_PATH",
        str(PROJECT_ROOT / "data" / "operational" / "wildfire.db")
        if (PROJECT_ROOT / "data" / "operational" / "wildfire.db").exists()
        else str(PROJECT_ROOT / "wildfire_agent.db")
    )

    # Demo mode — when True, generates simulated fire data
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")

    # Demo incident seed data — fetched from GitHub (any http(s) or file:// URL)
    DEMO_INCIDENTS_URL: str = os.getenv(
        "DEMO_INCIDENTS_URL",
        "https://raw.githubusercontent.com/ProsperousJoy/obor/main/data/demo_incidents.json",
    )

    # DuckDB Data Warehouse (Analytical OLAP Store)
    WAREHOUSE_DB_PATH: str = os.getenv(
        "WAREHOUSE_DB_PATH",
        str(PROJECT_ROOT / "data" / "warehouse" / "wildfire.duckdb")
        if (PROJECT_ROOT / "data" / "warehouse" / "wildfire.duckdb").exists()
        else str(PROJECT_ROOT / "data warehouse" / "data-mining-obor" / "data" / "warehouse" / "wildfire.duckdb")
    )

    # Warehouse Sync Interval (Default: 3600s = 1 hour)
    WAREHOUSE_SYNC_INTERVAL_SECONDS: int = int(os.getenv("WAREHOUSE_SYNC_INTERVAL_SECONDS", "3600"))

    # Borneo Bounding Box (Kalimantan Barat, Tengah, Selatan, Timur, Utara)
    BORNEO_BBOX: dict = {
        "lon_min": 108.0,
        "lon_max": 119.0,
        "lat_min": -5.0,
        "lat_max": 7.0,
    }

    # Real-Time Data Ingestion Sources
    FIRMS_VIIRS_URL: str = os.getenv(
        "FIRMS_VIIRS_URL",
        "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_SouthEast_Asia_24h.csv"
    )
    BMKG_API_BASE_URL: str = os.getenv(
        "BMKG_API_BASE_URL",
        "https://api.bmkg.go.id/publik/prakiraan-cuaca"
    )

    # Map Settings
    MAP_DEFAULT_CENTER: list = [-1.5, 114.0]
    MAP_DEFAULT_ZOOM: int = 6

    # Governance thresholds
    VI_MONITOR_THRESHOLD: float = 0.5    # VI > 0.5 → MONITOR
    VI_WATCH_THRESHOLD: float = 0.0      # 0.0 < VI ≤ 0.5 → WATCH
    VI_WARNING_THRESHOLD: float = -0.5   # -0.5 < VI ≤ 0.0 → WARNING
    # VI ≤ -0.5 → EMERGENCY

    # Fire risk thresholds
    HA_CRITICAL: float = 2000.0          # Fire over 2000 hectares (~5000 acres) is critical
    ACRES_CRITICAL: float = 5000.0       # Fire over 5000 acres is critical
    CONTAINMENT_LOW: float = 20.0        # Below 20% containment is dangerous
    GROWTH_RATE_HIGH: float = 200.0      # Growing > 200 ha/hr is alarming

    # Emergency dispatch cooldown (seconds)
    DISPATCH_COOLDOWN: int = 1800  # 30 minutes

    # On-demand Supervisor trigger thresholds
    SUPERVISOR_TRIGGER_ON_NEW: bool = True
    SUPERVISOR_TRIGGER_ON_ESCALATION: bool = True
    SUPERVISOR_TRIGGER_HEARTBEAT_CYCLES: int = 10

    # AVF rolling window size for t* prediction
    AVF_WINDOW_SIZE: int = 20

    @classmethod
    def validate(cls) -> list[str]:
        """Return a list of configuration warnings."""
        warnings = []
        if not cls.OPENAI_API_KEY:
            warnings.append(
                "OPENAI_API_KEY not set — agent will use rule-based predictions instead of AI"
            )
        if cls.DEMO_MODE:
            warnings.append("DEMO_MODE is enabled — using simulated fire data")
        return warnings


config = Config()
