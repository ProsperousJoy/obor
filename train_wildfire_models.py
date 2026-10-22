"""
Wildfire Model Training Script Facade

Delegates to `scripts/train_wildfire_models.py`.
"""

import sys
import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent / "scripts" / "train_wildfire_models.py"

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, str(_SCRIPT)] + sys.argv[1:]))
