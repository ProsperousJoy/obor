-- ======================================================================
-- Response System Extensions Schema
-- Modules 3 through 9 Support for Autonomous Wildfire Response System
-- ======================================================================

-- 1. Modul 3: Vulnerable Assets & Infrastructure (Impact Assessment)
CREATE TABLE IF NOT EXISTS dim_vulnerable_assets (
    asset_id VARCHAR PRIMARY KEY,
    asset_name VARCHAR NOT NULL,
    asset_type VARCHAR NOT NULL, -- 'SETTLEMENT', 'HOSPITAL', 'SCHOOL', 'PROTECTED_FOREST', 'CRITICAL_INFRA'
    province VARCHAR NOT NULL,
    kabupaten VARCHAR NOT NULL,
    lat DOUBLE NOT NULL,
    lon DOUBLE NOT NULL,
    nearest_grid_id VARCHAR REFERENCES dim_grid(grid_id),
    estimated_population INTEGER DEFAULT 0,
    is_peatland BOOLEAN DEFAULT FALSE,
    is_protected_area BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE dim_vulnerable_assets IS 'Settlements, facilities, and environmental assets for impact scoring';

-- 2. Modul 4: Water Sources Directory (Water Resource Agent)
CREATE TABLE IF NOT EXISTS dim_water_sources (
    source_id VARCHAR PRIMARY KEY,
    source_name VARCHAR NOT NULL,
    water_type VARCHAR NOT NULL, -- 'RIVER', 'LAKE', 'EMBUNG', 'CANAL', 'WELL'
    province VARCHAR NOT NULL,
    kabupaten VARCHAR NOT NULL,
    lat DOUBLE NOT NULL,
    lon DOUBLE NOT NULL,
    nearest_grid_id VARCHAR REFERENCES dim_grid(grid_id),
    capacity_m3 DOUBLE NOT NULL,
    surface_area_m2 DOUBLE NOT NULL,
    historical_permanence_score DOUBLE DEFAULT 0.85, -- 0.0 (seasonal) to 1.0 (perennial)
    pump_accessible BOOLEAN DEFAULT TRUE,
    terrain_difficulty VARCHAR DEFAULT 'MODERATE' -- 'EASY', 'MODERATE', 'DIFFICULT'
);
COMMENT ON TABLE dim_water_sources IS 'Available water sources for firefighting with capacity and accessibility';

-- 3. Modul 5: Responder Stations & Logistics (Resource Agent)
CREATE TABLE IF NOT EXISTS dim_responder_hq (
    hq_id VARCHAR PRIMARY KEY,
    hq_name VARCHAR NOT NULL,
    agency VARCHAR NOT NULL, -- 'MANGGALA_AGNI', 'BPBD', 'DAMKAR'
    province VARCHAR NOT NULL,
    kabupaten VARCHAR NOT NULL,
    lat DOUBLE NOT NULL,
    lon DOUBLE NOT NULL,
    nearest_grid_id VARCHAR REFERENCES dim_grid(grid_id),
    crew_available INTEGER DEFAULT 10,
    crew_on_duty INTEGER DEFAULT 6,
    fire_trucks INTEGER DEFAULT 2,
    portable_pumps INTEGER DEFAULT 4,
    water_tankers INTEGER DEFAULT 1,
    drones INTEGER DEFAULT 1,
    helicopter_available BOOLEAN DEFAULT FALSE,
    radio_channel VARCHAR DEFAULT 'VHF-142.500MHz',
    phone_contact VARCHAR NOT NULL
);
COMMENT ON TABLE dim_responder_hq IS 'Operational command posts, equipment, and contact registries';

-- 4. Moduls 6, 7, 8: Incident Action Plans & Execution Records
CREATE TABLE IF NOT EXISTS fact_incident_records (
    incident_id VARCHAR PRIMARY KEY,
    plan_id VARCHAR NOT NULL,
    target_datetime TIMESTAMP NOT NULL,
    grid_id VARCHAR REFERENCES dim_grid(grid_id),
    fire_probability DOUBLE NOT NULL,
    fire_intensity VARCHAR NOT NULL, -- 'LOW', 'MEDIUM', 'HIGH'
    impact_score INTEGER NOT NULL,   -- 0 - 100
    priority VARCHAR NOT NULL,       -- 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    recommended_action VARCHAR NOT NULL, -- 'MONITOR', 'GROUND_RESPONSE', 'AIR_RESPONSE', 'EVACUATION_SUPPORT'
    assigned_hq_id VARCHAR REFERENCES dim_responder_hq(hq_id),
    assigned_water_id VARCHAR REFERENCES dim_water_sources(source_id),
    eta_minutes INTEGER NOT NULL,
    steps_json VARCHAR,
    authorization_level VARCHAR NOT NULL, -- 'AUTO_LOW', 'AUTO_MEDIUM', 'MANUAL_ONLY'
    execution_status VARCHAR NOT NULL,    -- 'PENDING', 'EXECUTING', 'COMPLETED', 'FAILED'
    replan_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE fact_incident_records IS 'Incident action plans, dispatched resources, and execution states';

-- 5. Modul 9: Feedback & Post-Incident Evaluations
CREATE TABLE IF NOT EXISTS fact_incident_feedback (
    feedback_id VARCHAR PRIMARY KEY,
    incident_id VARCHAR REFERENCES fact_incident_records(incident_id),
    real_fire_confirmed BOOLEAN NOT NULL,
    actual_lat DOUBLE,
    actual_lon DOUBLE,
    actual_burn_area_ha DOUBLE,
    actual_response_time_min INTEGER,
    actual_water_source_used VARCHAR,
    prediction_error DOUBLE,
    plan_success_score DOUBLE, -- 0.0 - 1.0
    water_accuracy_score DOUBLE, -- 0.0 - 1.0
    retraining_candidate BOOLEAN DEFAULT FALSE,
    feedback_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE fact_incident_feedback IS 'Post-incident field verification and model accuracy feedback logs';
