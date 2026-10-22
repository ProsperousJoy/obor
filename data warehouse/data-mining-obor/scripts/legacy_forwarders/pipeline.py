"""
scripts/pipeline.py
===================
Himawari-9 data pipeline backwards-compatible entry point.
Forwards CLI execution to scripts.himawari.pipeline.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.himawari.pipeline import main, run_pipeline

if __name__ == "__main__":
    main()
