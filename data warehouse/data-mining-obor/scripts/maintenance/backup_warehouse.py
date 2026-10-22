"""
Warehouse Backup and Pre-Remediation Snapshot
---------------------------------------------
Backs up wildfire.duckdb and generates pre-remediation row count checksums.
"""

import shutil
import json
import logging
from pathlib import Path
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("warehouse_backup")

DB_PATH = Path("data/warehouse/wildfire.duckdb")
BACKUP_PATH = Path("data/warehouse/backup_wildfire_pre_remediation.duckdb")
CHECKSUM_FILE = Path("outputs/validation/pre_remediation_checksums.json")

def backup_database():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database {DB_PATH} not found.")
    
    logger.info(f"Creating cold backup: {DB_PATH} -> {BACKUP_PATH}")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    logger.info(f"Backup created successfully: {BACKUP_PATH.stat().st_size / (1024*1024):.2f} MB")

def snapshot_metrics():
    logger.info("Snapshooting pre-remediation table metrics...")
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    
    tables = conn.execute("""
        SELECT table_name, table_type 
        FROM information_schema.tables 
        WHERE table_schema = 'main'
        ORDER BY table_type, table_name
    """).fetchall()
    
    metrics = {"tables": {}, "views": {}}
    for name, t_type in tables:
        cnt = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        category = "tables" if t_type == "BASE TABLE" else "views"
        metrics[category][name] = cnt
        logger.info(f"  {category:6} | {name:25}: {cnt:10,d}")
        
    conn.close()
    
    CHECKSUM_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKSUM_FILE, "w") as f:
        json.dump(metrics, f, indent=2)
    logger.info(f"Metrics saved to {CHECKSUM_FILE}")

if __name__ == "__main__":
    backup_database()
    snapshot_metrics()
