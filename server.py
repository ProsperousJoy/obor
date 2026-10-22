"""
Wildfire Sentinel — Server Facade

Backward-compatible facade delegating to `src.api.app`.
Preserves imports and uvicorn entrypoint `server:app`.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.api.app import app, agent, _broadcast_event, _sse_queues, _monitoring_loop, STATIC_DIR

__all__ = ["app", "agent", "_broadcast_event", "_sse_queues", "_monitoring_loop", "STATIC_DIR"]

if __name__ == "__main__":
    import uvicorn
    from src.config import config
    uvicorn.run("server:app", host=config.HOST, port=config.PORT, reload=True)
