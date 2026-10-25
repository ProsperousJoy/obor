"""DuckDB analytical data warehouse integration layer.
Manages connections and queries to Kalimantan / Borneo spatial and ML views.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional
import duckdb

from src.config import config


def get_warehouse_db_path() -> str:
    """Return the absolute path to the DuckDB warehouse file."""
    return config.WAREHOUSE_DB_PATH


@contextmanager
def get_warehouse_connection(read_only: bool = False) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """
    Context manager providing a managed DuckDB connection.
    Uses unified connection configuration to prevent concurrency mismatch errors.
    """
    db_path = get_warehouse_db_path()
    conn = duckdb.connect(db_path, read_only=False)
    try:
        yield conn
        if not read_only:
            conn.commit()
    finally:
        conn.close()
