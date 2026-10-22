#!/usr/bin/env python3
"""
OBOR — Entry Point

Autonomous Multi-Agent Peatland & Wildfire Intelligence System for
Kalimantan (Borneo), Indonesia. Features Agent Viability Framework (AVF)
runtime governance, DuckDB geospatial data warehouse, Jev AI supervisor,
and automated Manggala Agni dispatch dispatching.

Based on: "Governing What You Cannot Observe: Adaptive Runtime
Governance for Autonomous AI Agents" (Marín & Chaudhary, 2026)

Usage:
    python main.py              # Normal mode (live satellite data)
    DEMO_MODE=true python main.py   # Demo mode (simulated data)
"""

import logging
import sys
import uvicorn

from src.config import config

# ─── Logging Setup ────────────────────────────────────────────────────────────

def setup_logging():
    """Configure rich logging for the application."""
    log_format = (
        "%(asctime)s │ %(name)-20s │ %(levelname)-7s │ %(message)s"
    )
    date_format = "%H:%M:%S"

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    setup_logging()
    logger = logging.getLogger("obor.main")

    logger.info("=" * 60)
    logger.info("  🔥 OBOR — Autonomous Peatland & Wildfire AI")
    logger.info("=" * 60)
    logger.info("")

    # Display configuration
    warnings = config.validate()
    if warnings:
        for w in warnings:
            logger.warning(f"  ⚠️  {w}")
    else:
        logger.info("  ✅ Configuration valid")

    logger.info(f"  📡 Data source: {'DEMO (simulated)' if config.DEMO_MODE else 'NIFC WFIGS (live)'}")
    logger.info(f"  🤖 AI engine:   {'Tokito/OpenAI (' + config.OPENAI_MODEL + ' @ ' + config.OPENAI_BASE_URL + ')' if config.OPENAI_API_KEY else 'Rule-based (no API key)'}")
    logger.info(f"  ⏱️  Poll interval: {config.POLL_INTERVAL}s")
    logger.info(f"  🌐 Dashboard:   http://{config.HOST}:{config.PORT}")
    logger.info("")
    logger.info("=" * 60)

    # Run the FastAPI server
    uvicorn.run(
        "src.api.app:app",
        host=config.HOST,
        port=config.PORT,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
