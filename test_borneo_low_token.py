"""Backward-compatible facade delegating to tests/integration/test_borneo_low_token.py."""
import sys
import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent / "tests" / "integration" / "test_borneo_low_token.py"

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, str(_SCRIPT)] + sys.argv[1:]))
