"""Backward-compatible facade delegating to tests/integration/test_api_endpoints.py."""
import sys
import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent / "tests" / "integration" / "test_api_endpoints.py"

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, str(_SCRIPT)] + sys.argv[1:]))
