-- Sequence for fact_fire_hotspots auto-increment ID
CREATE SEQUENCE IF NOT EXISTS seq_fact_fire_hotspots;

-- Dimension Tables
CREATE TABLE IF NOT EXISTS dim_grid (
    grid_id VARCHAR PRIMARY KEY,
    centroid_lat DOUBLE,
    centroid_lon DOUBLE,
    province VARCHAR,
    is_land BOOLEAN
);
COMMENT ON TABLE dim_grid IS 'Spatial grid definitions for Borneo (0.02 deg resolution)';

CREATE TABLE IF NOT EXISTS dim_sensor (
    sensor_id VARCHAR PRIMARY KEY,
    platform VARCHAR,
    orbit_type VARCHAR,
    resolution_m INTEGER,
    operational_start DATE,
    operational_end DATE NULL
);
COMMENT ON TABLE dim_sensor IS 'Satellite sensors used for thermal and hotspot data';

CREATE TABLE IF NOT EXISTS dim_adm4 (
    adm4_code VARCHAR PRIMARY KEY,
    provinsi VARCHAR,
    kabupaten_kota VARCHAR,
    kecamatan VARCHAR,
    desa_kelurahan VARCHAR,
    lat DOUBLE,
    lon DOUBLE,
    nearest_grid_id VARCHAR REFERENCES dim_grid(grid_id)
);
COMMENT ON TABLE dim_adm4 IS 'Level 4 Administrative boundaries (Desa/Kelurahan)';

-- Fact Tables
CREATE TABLE IF NOT EXISTS fact_fire_hotspots (
    id INTEGER PRIMARY KEY DEFAULT nextval('seq_fact_fire_hotspots'),
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    datetime_utc TIMESTAMP,
    lat DOUBLE,
    lon DOUBLE,
    bright_ti4_k DOUBLE,
    bright_ti5_k DOUBLE,
    delta_bt_k DOUBLE,
    frp_mw DOUBLE,
    confidence VARCHAR,
    daynight VARCHAR,
    sensor_id VARCHAR REFERENCES dim_sensor(sensor_id),
    year INTEGER,
    month INTEGER
);
COMMENT ON TABLE fact_fire_hotspots IS 'Active fire hotspot detections';

-- Unique natural key index for idempotency
CREATE UNIQUE INDEX IF NOT EXISTS uq_hotspots_natural 
ON fact_fire_hotspots (sensor_id, datetime_utc, lat, lon);

CREATE TABLE IF NOT EXISTS fact_thermal_grid (
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    datetime_utc TIMESTAMP,
    sensor_id VARCHAR REFERENCES dim_sensor(sensor_id),
    bt_b07_k DOUBLE,
    is_cloudy BOOLEAN,
    valid_pixel_pct DOUBLE,
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (grid_id, datetime_utc)
);
COMMENT ON TABLE fact_thermal_grid IS 'Raw thermal observations gridded to 0.02 deg';

CREATE TABLE IF NOT EXISTS fact_weather_daily (
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    date_utc DATE,
    t2m_mean_c DOUBLE,
    t2m_max_c DOUBLE,
    t2m_min_c DOUBLE,
    dewpoint_c DOUBLE,
    rh_mean_pct DOUBLE,
    rh_min_pct DOUBLE,
    precip_mm DOUBLE,
    wind_speed_kmh DOUBLE,
    wind_dir_deg DOUBLE,
    surface_pressure_hpa DOUBLE,
    soil_moisture_0_7cm DOUBLE,
    soil_moisture_rootzone DOUBLE,
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (grid_id, date_utc)
);
COMMENT ON TABLE fact_weather_daily IS 'Daily weather summaries per grid cell (ECMWF/ERA5)';

CREATE TABLE IF NOT EXISTS fact_forecast_3h (
    adm4_code VARCHAR REFERENCES dim_adm4(adm4_code),
    forecast_datetime_utc TIMESTAMP,
    analysis_datetime_utc TIMESTAMP,
    temp_c DOUBLE,
    humidity_pct DOUBLE,
    precip_mm DOUBLE,
    wind_speed_kmh DOUBLE,
    cloud_cover_pct DOUBLE,
    weather_code INTEGER,
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (adm4_code, forecast_datetime_utc)
);
COMMENT ON TABLE fact_forecast_3h IS 'BMKG 3-hourly weather forecasts at ADM4 level';

CREATE TABLE IF NOT EXISTS fact_fuel_condition (
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    date_utc DATE,
    ndvi DOUBLE,
    evi DOUBLE,
    ndmi DOUBLE,
    is_synthetic BOOLEAN DEFAULT FALSE,
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (grid_id, date_utc)
);
COMMENT ON TABLE fact_fuel_condition IS 'Vegetation indices for fuel load estimation (Phase 2)';

-- ML Training & Target Tables
CREATE TABLE IF NOT EXISTS fact_training_spine (
    sample_id BIGINT PRIMARY KEY,
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    target_datetime TIMESTAMP,
    is_fire_stratum BOOLEAN,
    split VARCHAR, -- 'TRAIN', 'VAL', 'TEST'
    year INTEGER,
    month INTEGER
);
COMMENT ON TABLE fact_training_spine IS 'Stratified presence-background spatiotemporal training spine';

CREATE TABLE IF NOT EXISTS fact_fire_targets_24h (
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    target_datetime TIMESTAMP,
    fire_count_24h INTEGER,
    max_frp_24h DOUBLE,
    has_fire_24h BOOLEAN,
    PRIMARY KEY (grid_id, target_datetime)
);
COMMENT ON TABLE fact_fire_targets_24h IS 'Precomputed leak-free 24-hour future fire targets strictly in (T, T+24h]';

-- Aggregation Tables
CREATE TABLE IF NOT EXISTS agg_thermal_hourly (
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    datetime_hour_utc TIMESTAMP,
    bt_mean_k DOUBLE,
    bt_max_k DOUBLE,
    bt_min_k DOUBLE,
    bt_std_k DOUBLE,
    thermal_anomaly_count INTEGER,
    cloud_fraction DOUBLE,
    bt_change_max_10m DOUBLE,
    bt_change_max_30m DOUBLE,
    bt_change_max_1h DOUBLE,
    observation_count INTEGER,
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (grid_id, datetime_hour_utc)
);
COMMENT ON TABLE agg_thermal_hourly IS 'Hourly aggregated thermal features';

CREATE TABLE IF NOT EXISTS agg_thermal_daily (
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    date_utc DATE,
    bt_mean_k DOUBLE,
    bt_max_k DOUBLE,
    bt_min_k DOUBLE,
    bt_std_k DOUBLE,
    thermal_anomaly_count INTEGER,
    cloud_fraction DOUBLE,
    daily_thermal_persistence DOUBLE,
    observation_count INTEGER,
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (grid_id, date_utc)
);
COMMENT ON TABLE agg_thermal_daily IS 'Daily aggregated thermal features';

CREATE TABLE IF NOT EXISTS agg_fire_history (
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    date_utc DATE,
    hotspot_count_prev_24h INTEGER,
    hotspot_count_prev_7d INTEGER,
    max_frp_prev_7d DOUBLE,
    sum_frp_prev_7d DOUBLE,
    has_recent_fire_7d BOOLEAN,
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (grid_id, date_utc)
);
COMMENT ON TABLE agg_fire_history IS 'Historical fire activity statistics per grid cell';

CREATE TABLE IF NOT EXISTS agg_weather_rolling (
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    date_utc DATE,
    rain_accum_7d_mm DOUBLE,
    rain_accum_30d_mm DOUBLE,
    consecutive_dry_days INTEGER,
    t2m_anomaly_vs_30d_mean DOUBLE,
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (grid_id, date_utc)
);
COMMENT ON TABLE agg_weather_rolling IS 'Rolling weather statistics for antecedent conditions';
