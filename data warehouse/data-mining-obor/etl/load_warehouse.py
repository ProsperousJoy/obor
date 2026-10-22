import logging
import duckdb
import pandas as pd
from pathlib import Path
from typing import Dict, Tuple, Any, Optional

from config.settings import WAREHOUSE_CONFIG, BORNEO_BBOX

logger = logging.getLogger(__name__)

_conn: Optional[duckdb.DuckDBPyConnection] = None

def get_connection(db_path: str = None) -> duckdb.DuckDBPyConnection:
    """
    Get DuckDB connection (singleton pattern).
    """
    global _conn
    if _conn is None:
        path = str(db_path or WAREHOUSE_CONFIG.get('db_path', 'warehouse.duckdb'))
        _conn = duckdb.connect(database=path, read_only=False)
        logger.info(f"Connected to DuckDB at {path}")
    return _conn

def close_connection() -> None:
    """
    Close singleton DuckDB connection.
    """
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
        logger.info("DuckDB connection closed.")

def load_dataframe(df: pd.DataFrame, table_name: str, mode: str = 'append') -> None:
    """
    Insert pandas/pyarrow DataFrame into DuckDB table with transactional protection.
    Mode: 'append' or 'replace'.
    """
    conn = get_connection()
    if mode == 'replace':
        try:
            conn.execute("BEGIN TRANSACTION")
            conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df")
            conn.execute("COMMIT")
            logger.info(f"Replaced table {table_name} with {len(df)} rows.")
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"Transaction failed during replace of {table_name}: {e}")
            raise e
    elif mode == 'append':
        # Ensure table exists first or create it if not
        tables = conn.execute("SHOW TABLES").df()
        if table_name not in tables['name'].values:
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
                conn.execute("COMMIT")
                logger.info(f"Created table {table_name} with {len(df)} rows.")
            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error(f"Transaction failed creating {table_name}: {e}")
                raise e
        else:
            table_cols = conn.execute(f"DESCRIBE {table_name}").df()['column_name'].tolist()
            common_cols = [c for c in table_cols if c in df.columns]
            if not common_cols:
                raise ValueError(f"No common columns between DataFrame and {table_name}")
            cols_str = ", ".join(common_cols)
            try:
                conn.execute("BEGIN TRANSACTION")
                try:
                    conn.execute(f"INSERT OR IGNORE INTO {table_name} ({cols_str}) SELECT {cols_str} FROM df")
                except duckdb.BinderException:
                    conn.execute(f"INSERT INTO {table_name} ({cols_str}) SELECT {cols_str} FROM df")
                conn.execute("COMMIT")
                logger.info(f"Appended {len(df)} rows to {table_name} ({len(common_cols)} columns).")
            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error(f"Transaction failed during append to {table_name}: {e}")
                raise e
    else:
        raise ValueError("mode must be 'append' or 'replace'")

def export_to_parquet(table_name: str, parquet_base_dir: str = None) -> None:
    """
    Export a DuckDB table to partitioned Parquet (year/month).
    """
    conn = get_connection()
    base_dir = str(parquet_base_dir or WAREHOUSE_CONFIG.get('parquet_dir', 'data/parquet'))
    out_path = Path(base_dir) / table_name
    out_path.mkdir(parents=True, exist_ok=True)
    
    cols = [c[0].lower() for c in conn.execute(f"DESCRIBE {table_name}").fetchall()]
    if 'year' in cols and 'month' in cols:
        query = f"""
            COPY {table_name} TO '{str(out_path).replace(chr(92), "/")}' 
            (FORMAT PARQUET, PARTITION_BY (year, month), OVERWRITE_OR_IGNORE 1)
        """
    elif 'target_datetime' in cols:
        query = f"""
            COPY (
                SELECT *, 
                       EXTRACT(YEAR FROM target_datetime)::INTEGER AS year,
                       EXTRACT(MONTH FROM target_datetime)::INTEGER AS month 
                FROM {table_name}
            ) TO '{str(out_path).replace(chr(92), "/")}' 
            (FORMAT PARQUET, PARTITION_BY (year, month), OVERWRITE_OR_IGNORE 1)
        """
    elif 'datetime_utc' in cols:
        query = f"""
            COPY (
                SELECT *, 
                       EXTRACT(YEAR FROM datetime_utc)::INTEGER AS year,
                       EXTRACT(MONTH FROM datetime_utc)::INTEGER AS month 
                FROM {table_name}
            ) TO '{str(out_path).replace(chr(92), "/")}' 
            (FORMAT PARQUET, PARTITION_BY (year, month), OVERWRITE_OR_IGNORE 1)
        """
    else:
        file_out = (out_path / "data.parquet").resolve()
        query = f"""
            COPY {table_name} TO '{str(file_out).replace(chr(92), "/")}' 
            (FORMAT PARQUET)
        """
        
    conn.execute(query)
    logger.info(f"Exported {table_name} to parquet at {out_path}")

def deduplicate_table(table_name: str, key_columns: list) -> None:
    """
    Remove duplicate rows based on key columns in a DuckDB table.
    Uses DELETE + INSERT to preserve foreign key constraints.
    """
    conn = get_connection()
    keys_str = ", ".join(key_columns)
    
    # Check if duplicates exist
    check_query = f"""
        SELECT COUNT(*) FROM (
            SELECT {keys_str}, COUNT(*) 
            FROM {table_name} 
            GROUP BY {keys_str} 
            HAVING COUNT(*) > 1
        )
    """
    dups = conn.execute(check_query).fetchone()[0]
    if dups == 0:
        return
        
    temp_table = f"{table_name}_dedup_temp"
    conn.execute(f"""
        CREATE OR REPLACE TEMPORARY TABLE {temp_table} AS 
        SELECT * FROM (
            SELECT *, ROW_NUMBER() OVER(PARTITION BY {keys_str}) as _rn 
            FROM {table_name}
        )
        WHERE _rn = 1
    """)
    conn.execute(f"ALTER TABLE {temp_table} DROP COLUMN _rn")
    conn.execute(f"DELETE FROM {table_name}")
    
    table_cols = conn.execute(f"DESCRIBE {table_name}").df()['column_name'].tolist()
    cols_str = ", ".join(table_cols)
    conn.execute(f"INSERT INTO {table_name} ({cols_str}) SELECT {cols_str} FROM {temp_table}")
    conn.execute(f"DROP TABLE {temp_table}")
    logger.info(f"Deduplicated {table_name} on columns {key_columns}")

def validate_ranges(df: pd.DataFrame, validations: Dict[str, Tuple[float, float]]) -> bool:
    """
    Validate column values are in expected ranges.
    validations format: {'column': (min, max)}
    """
    is_valid = True
    for col, (min_val, max_val) in validations.items():
        if col in df.columns:
            out_of_bounds = df[(df[col] < min_val) | (df[col] > max_val)]
            if not out_of_bounds.empty:
                logger.warning(f"Validation failed for {col}: {len(out_of_bounds)} rows out of bounds ({min_val}, {max_val})")
                is_valid = False
    return is_valid

def get_table_stats(table_name: str) -> Dict[str, Any]:
    """
    Return dict with row_count, column_count, etc.
    """
    conn = get_connection()
    row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    columns = conn.execute(f"DESCRIBE {table_name}").df()
    
    return {
        'row_count': row_count,
        'column_count': len(columns),
        'columns': columns['column_name'].tolist()
    }

def assign_grid_id(lat: float, lon: float, resolution: float = 0.02) -> str:
    """
    Compute canonical grid_id from lat/lon with bounds clamping and precision protection.
    Grid ID format: 'G{lat_idx:04d}_{lon_idx:04d}' 
    where lat_idx = round((lat - lat_min) / resolution)
    """
    lat_min = BORNEO_BBOX['lat_min']
    lat_max = BORNEO_BBOX['lat_max']
    lon_min = BORNEO_BBOX['lon_min']
    lon_max = BORNEO_BBOX['lon_max']
    
    # Clamp to bounding box
    clamped_lat = max(lat_min, min(lat, lat_max))
    clamped_lon = max(lon_min, min(lon, lon_max))
    
    # Epsilon protection against floating point rounding anomalies
    lat_idx = int(round((clamped_lat - lat_min + 1e-9) / resolution))
    lon_idx = int(round((clamped_lon - lon_min + 1e-9) / resolution))
    
    return f"G{lat_idx:04d}_{lon_idx:04d}"
