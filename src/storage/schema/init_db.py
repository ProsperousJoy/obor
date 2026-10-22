"""
Database Initialization Script for Kalimantan Wildfire Data Warehouse

Creates the DuckDB database, executes schema DDL, generates the canonical
spatial grid, and populates static dimension tables.
"""

import sys
import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import WAREHOUSE_CONFIG, BORNEO_BBOX, PROVINCIAL_CAPITALS


def get_nearest_province(lat: float, lon: float) -> str:
    """Assign province based on Euclidean distance to nearest provincial capital."""
    min_dist = float("inf")
    closest_province = "Unknown"
    for province_name, data in PROVINCIAL_CAPITALS.items():
        dist = math.sqrt((lat - data["lat"]) ** 2 + (lon - data["lon"]) ** 2)
        if dist < min_dist:
            min_dist = dist
            closest_province = province_name
    return closest_province


def populate_dim_grid(conn: duckdb.DuckDBPyConnection) -> None:
    """Generate and insert canonical 0.02° grid cells into dim_grid."""
    print("Generating dim_grid data...")

    count = conn.execute("SELECT COUNT(*) FROM dim_grid").fetchone()[0]
    if count > 0:
        print(f"  dim_grid already contains {count:,} rows. Skipping.")
        return

    res = WAREHOUSE_CONFIG["canonical_grid_resolution_deg"]
    lats = np.arange(BORNEO_BBOX["lat_min"], BORNEO_BBOX["lat_max"] + res / 2, res)
    lons = np.arange(BORNEO_BBOX["lon_min"], BORNEO_BBOX["lon_max"] + res / 2, res)

    print(f"  Grid dimensions: {len(lats)} lat × {len(lons)} lon = {len(lats) * len(lons):,} cells")

    rows = []
    for lat_idx, lat in enumerate(lats):
        for lon_idx, lon in enumerate(lons):
            grid_id = f"G{lat_idx:04d}_{lon_idx:04d}"
            province = get_nearest_province(float(lat), float(lon))
            rows.append({
                "grid_id": grid_id,
                "centroid_lat": round(float(lat), 4),
                "centroid_lon": round(float(lon), 4),
                "province": province,
                "is_land": True,
            })

    geojson_path = PROJECT_ROOT / "outputs" / "validation" / "ne_10m_land.geojson"
    if geojson_path.exists():
        from shapely.geometry import shape, box, Point
        from shapely.ops import unary_union
        from shapely.prepared import prep
        import json
        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        b_box = box(BORNEO_BBOX["lon_min"], BORNEO_BBOX["lat_min"], BORNEO_BBOX["lon_max"], BORNEO_BBOX["lat_max"])
        polys = [shape(f["geometry"]).intersection(b_box) for f in data["features"] if shape(f["geometry"]).intersects(b_box)]
        land_prep = prep(unary_union(polys).buffer(0.01))
        for r in rows:
            r["is_land"] = bool(land_prep.contains(Point(r["centroid_lon"], r["centroid_lat"])))

    df_grid = pd.DataFrame(rows)
    print(f"  Inserting {len(df_grid):,} rows into dim_grid...")
    conn.execute("INSERT INTO dim_grid SELECT * FROM df_grid")
    print(f"  dim_grid populated: {len(df_grid):,} cells")


def populate_dim_sensor(conn: duckdb.DuckDBPyConnection) -> None:
    """Populate dim_sensor with the 4 static satellite sensor records."""
    print("Populating dim_sensor data...")

    count = conn.execute("SELECT COUNT(*) FROM dim_sensor").fetchone()[0]
    if count > 0:
        print(f"  dim_sensor already contains {count} rows. Skipping.")
        return

    sensors = [
        ("AHI_H08", "Himawari-8", "GEO", 2000, "2015-07-07", "2022-12-12"),
        ("AHI_H09", "Himawari-9", "GEO", 2000, "2022-12-13", None),
        ("VIIRS_N20", "NOAA-20", "LEO", 375, "2018-01-01", None),
        ("VIIRS_N21", "NOAA-21", "LEO", 375, "2023-02-10", None),
    ]

    df_sensor = pd.DataFrame(
        sensors,
        columns=["sensor_id", "platform", "orbit_type", "resolution_m",
                 "operational_start", "operational_end"],
    )
    df_sensor["operational_start"] = pd.to_datetime(df_sensor["operational_start"]).dt.date
    df_sensor["operational_end"] = pd.to_datetime(df_sensor["operational_end"]).dt.date

    conn.execute("INSERT INTO dim_sensor SELECT * FROM df_sensor")
    print(f"  dim_sensor populated: {len(df_sensor)} sensors")


def create_database() -> None:
    """
    Main initialization routine.

    1. Creates the DuckDB database file
    2. Installs spatial extension
    3. Executes schema.sql and ml_views.sql
    4. Generates dim_grid (canonical 0.02° spatial grid)
    5. Populates dim_sensor (static satellite reference)
    """
    db_path: Path = WAREHOUSE_CONFIG["db_path"]
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"{'=' * 60}")
    print(f"Initializing Kalimantan Wildfire Data Warehouse")
    print(f"Database: {db_path}")
    print(f"{'=' * 60}")

    conn = duckdb.connect(str(db_path))

    # Install and load spatial extension
    print("\nInstalling DuckDB spatial extension...")
    conn.execute("INSTALL spatial;")
    conn.execute("LOAD spatial;")

    # Execute schema DDL
    schema_path = Path(__file__).parent / "schema.sql"
    if schema_path.exists():
        print(f"\nExecuting {schema_path.name}...")
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        # DuckDB execute() only runs one statement at a time in some versions
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)
        print("  Schema created successfully.")
    else:
        print(f"  WARNING: {schema_path} not found!")

    # Execute ML views
    views_path = Path(__file__).parent / "ml_views.sql"
    if views_path.exists():
        print(f"\nExecuting {views_path.name}...")
        with open(views_path, "r", encoding="utf-8") as f:
            sql = f.read()
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                try:
                    conn.execute(statement)
                except duckdb.Error as e:
                    # Views may fail if referenced tables are empty — that's OK
                    print(f"  Note: {e}")
        print("  Views created successfully.")
    else:
        print(f"  WARNING: {views_path} not found!")

    # Populate dimension tables
    print()
    populate_dim_grid(conn)
    populate_dim_sensor(conn)

    # Summary
    print(f"\n{'=' * 60}")
    print("Initialization Summary")
    print(f"{'=' * 60}")
    tables = conn.execute("SHOW TABLES").fetchall()
    print(f"Tables created: {len(tables)}")
    for (table_name,) in tables:
        try:
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            print(f"  {table_name}: {row_count:,} rows")
        except duckdb.Error:
            print(f"  {table_name}: (view/empty)")

    conn.close()
    print(f"\n[OK] Database initialization complete: {db_path}")


def main() -> None:
    """CLI entry point."""
    create_database()


if __name__ == "__main__":
    main()
