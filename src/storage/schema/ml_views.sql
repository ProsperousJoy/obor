-- =====================================================================
-- Analytical Views for Machine Learning & Operational Inference
-- Scientific Anti-Leakage Compliant (Strictly T or T-1d)
-- =====================================================================

-- View for Machine Learning Training Dataset
CREATE OR REPLACE VIEW vw_training_dataset AS
SELECT
    -- Base identifiers & split metadata
    sp.sample_id,
    sp.grid_id,
    sp.target_datetime,
    sp.split,
    sp.year,
    sp.month,
    
    -- Static features
    dg.centroid_lat,
    dg.centroid_lon,
    dg.province,
    dg.is_land,
    
    -- Antecedent weather (strictly T-1 day to guarantee zero same-day leakage)
    ROUND(
        gw.w_kalbar * w_kb.t2m_max_c + 
        gw.w_kalteng * w_kt.t2m_max_c + 
        gw.w_kalsel * w_ks.t2m_max_c + 
        gw.w_kaltim * w_ki.t2m_max_c + 
        gw.w_kaltara * w_ku.t2m_max_c, 2
    )::DOUBLE AS prev_day_t2m_max_c,
    
    ROUND(
        gw.w_kalbar * w_kb.rh_min_pct + 
        gw.w_kalteng * w_kt.rh_min_pct + 
        gw.w_kalsel * w_ks.rh_min_pct + 
        gw.w_kaltim * w_ki.rh_min_pct + 
        gw.w_kaltara * w_ku.rh_min_pct, 1
    )::DOUBLE AS prev_day_rh_min_pct,
    
    ROUND(
        gw.w_kalbar * w_kb.precip_mm + 
        gw.w_kalteng * w_kt.precip_mm + 
        gw.w_kalsel * w_ks.precip_mm + 
        gw.w_kaltim * w_ki.precip_mm + 
        gw.w_kaltara * w_ku.precip_mm, 2
    )::DOUBLE AS prev_day_precip_mm,
    
    ROUND(
        gw.w_kalbar * w_kb.wind_speed_kmh + 
        gw.w_kalteng * w_kt.wind_speed_kmh + 
        gw.w_kalsel * w_ks.wind_speed_kmh + 
        gw.w_kaltim * w_ki.wind_speed_kmh + 
        gw.w_kaltara * w_ku.wind_speed_kmh, 2
    )::DOUBLE AS prev_day_wind_speed_kmh,
    
    ROUND(
        gw.w_kalbar * w_kb.soil_moisture_0_7cm + 
        gw.w_kalteng * w_kt.soil_moisture_0_7cm + 
        gw.w_kalsel * w_ks.soil_moisture_0_7cm + 
        gw.w_kaltim * w_ki.soil_moisture_0_7cm + 
        gw.w_kaltara * w_ku.soil_moisture_0_7cm, 3
    )::DOUBLE AS prev_day_soil_moisture,
    
    -- Antecedent rolling weather (at T-1 day)
    ROUND(
        gw.w_kalbar * r_kb.rain_accum_7d_mm + 
        gw.w_kalteng * r_kt.rain_accum_7d_mm + 
        gw.w_kalsel * r_ks.rain_accum_7d_mm + 
        gw.w_kaltim * r_ki.rain_accum_7d_mm + 
        gw.w_kaltara * r_ku.rain_accum_7d_mm, 2
    )::DOUBLE AS rain_accum_7d_mm,
    
    ROUND(
        gw.w_kalbar * r_kb.rain_accum_30d_mm + 
        gw.w_kalteng * r_kt.rain_accum_30d_mm + 
        gw.w_kalsel * r_ks.rain_accum_30d_mm + 
        gw.w_kaltim * r_ki.rain_accum_30d_mm + 
        gw.w_kaltara * r_ku.rain_accum_30d_mm, 2
    )::DOUBLE AS rain_accum_30d_mm,
    
    ROUND(
        gw.w_kalbar * r_kb.consecutive_dry_days + 
        gw.w_kalteng * r_kt.consecutive_dry_days + 
        gw.w_kalsel * r_ks.consecutive_dry_days + 
        gw.w_kaltim * r_ki.consecutive_dry_days + 
        gw.w_kaltara * r_ku.consecutive_dry_days
    )::INTEGER AS consecutive_dry_days,
    
    ROUND(
        gw.w_kalbar * r_kb.t2m_anomaly_vs_30d_mean + 
        gw.w_kalteng * r_kt.t2m_anomaly_vs_30d_mean + 
        gw.w_kalsel * r_ks.t2m_anomaly_vs_30d_mean + 
        gw.w_kaltim * r_ki.t2m_anomaly_vs_30d_mean + 
        gw.w_kaltara * r_ku.t2m_anomaly_vs_30d_mean, 2
    )::DOUBLE AS t2m_anomaly_vs_30d_mean,
    
    -- Antecedent fire history (strictly < T, zero-defaulted)
    COALESCE(afh.hotspot_count_prev_24h, 0)::INTEGER AS hotspot_count_prev_24h,
    COALESCE(afh.hotspot_count_prev_7d, 0)::INTEGER AS hotspot_count_prev_7d,
    COALESCE(afh.max_frp_prev_7d, 0.0)::DOUBLE AS max_frp_prev_7d,
    COALESCE(afh.has_recent_fire_7d, FALSE)::BOOLEAN AS has_recent_fire_7d,
    
    -- Satellite thermal features (available when Himawari observation exists at T, clean NULL otherwise)
    ath.bt_mean_k AS th_bt_mean_k,
    ath.bt_max_k AS th_bt_max_k,
    ath.bt_min_k AS th_bt_min_k,
    ath.bt_std_k AS th_bt_std_k,
    ath.thermal_anomaly_count AS th_anomaly_count,
    ath.cloud_fraction AS th_cloud_fraction,
    ath.bt_change_max_1h AS th_bt_change_1h,
    
    -- Previous day completed thermal summary (strictly T-1 day, no future leakage)
    atd.bt_mean_k AS prev_day_bt_mean_k,
    atd.bt_max_k AS prev_day_bt_max_k,
    atd.daily_thermal_persistence AS prev_day_thermal_persistence,
    
    -- QUARANTINED: Synthetic fuel features excluded from production training features
    CAST(NULL AS DOUBLE) AS fuel_ndvi,
    CAST(NULL AS DOUBLE) AS fuel_evi,
    CAST(NULL AS DOUBLE) AS fuel_ndmi,
    CAST(NULL AS INTEGER) AS fuel_days_since_update,
    
    -- TARGETS: Precomputed future 24h fire activity strictly in (T, T+24h]
    COALESCE(tgt.fire_count_24h, 0)::INTEGER AS target_fire_count_24h,
    COALESCE(tgt.has_fire_24h, FALSE)::BOOLEAN AS target_has_fire_24h,
    COALESCE(tgt.max_frp_24h, 0.0)::DOUBLE AS target_fire_intensity_24h

FROM fact_training_spine sp
LEFT JOIN dim_grid dg ON sp.grid_id = dg.grid_id
JOIN dim_grid_weather_weights gw ON sp.grid_id = gw.grid_id

-- Precomputed leak-free 24-hour future fire targets
LEFT JOIN fact_fire_targets_24h tgt 
    ON sp.grid_id = tgt.grid_id 
    AND sp.target_datetime = tgt.target_datetime

-- 5 provincial station daily weather at T-1 day
LEFT JOIN fact_weather_daily w_kb ON w_kb.grid_id = 'G0249_0067' AND w_kb.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE
LEFT JOIN fact_weather_daily w_kt ON w_kt.grid_id = 'G0140_0296' AND w_kt.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE
LEFT JOIN fact_weather_daily w_ks ON w_ks.grid_id = 'G0084_0330' AND w_ks.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE
LEFT JOIN fact_weather_daily w_ki ON w_ki.grid_id = 'G0225_0458' AND w_ki.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE
LEFT JOIN fact_weather_daily w_ku ON w_ku.grid_id = 'G0392_0469' AND w_ku.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE

-- 5 provincial station rolling weather at T-1 day
LEFT JOIN agg_weather_rolling r_kb ON r_kb.grid_id = 'G0249_0067' AND r_kb.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE
LEFT JOIN agg_weather_rolling r_kt ON r_kt.grid_id = 'G0140_0296' AND r_kt.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE
LEFT JOIN agg_weather_rolling r_ks ON r_ks.grid_id = 'G0084_0330' AND r_ks.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE
LEFT JOIN agg_weather_rolling r_ki ON r_ki.grid_id = 'G0225_0458' AND r_ki.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE
LEFT JOIN agg_weather_rolling r_ku ON r_ku.grid_id = 'G0392_0469' AND r_ku.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE

-- Antecedent fire history (represents state strictly < T)
LEFT JOIN agg_fire_history afh 
    ON sp.grid_id = afh.grid_id 
    AND afh.date_utc = CAST(sp.target_datetime AS DATE)

-- Thermal observations at T (if available in warehouse)
LEFT JOIN agg_thermal_hourly ath 
    ON sp.grid_id = ath.grid_id 
    AND sp.target_datetime = ath.datetime_hour_utc

-- Previous day completed thermal summary (strictly T-1 day, no future leakage)
LEFT JOIN agg_thermal_daily atd 
    ON sp.grid_id = atd.grid_id 
    AND atd.date_utc = (sp.target_datetime - INTERVAL 1 DAY)::DATE
;


-- View for Inference Input (Operational forecasting for latest timestamp)
CREATE OR REPLACE VIEW vw_inference_input AS
WITH latest_thermal AS (
    SELECT grid_id, MAX(datetime_hour_utc) AS last_obs_time
    FROM agg_thermal_hourly
    GROUP BY grid_id
),
grid_forecasts AS (
    -- Pre-aggregate to nearest_grid_id to eliminate ADM4 spatial duplication fan-out
    SELECT 
        adm.nearest_grid_id AS grid_id,
        AVG(ff3.temp_c)::DOUBLE AS forecast_temp_c,
        AVG(ff3.humidity_pct)::DOUBLE AS forecast_humidity_pct,
        AVG(ff3.precip_mm)::DOUBLE AS forecast_precip_mm,
        AVG(ff3.wind_speed_kmh)::DOUBLE AS forecast_wind_speed_kmh,
        AVG(ff3.cloud_cover_pct)::DOUBLE AS forecast_cloud_cover_pct
    FROM (
        SELECT adm4_code, temp_c, humidity_pct, precip_mm, wind_speed_kmh, cloud_cover_pct,
               ROW_NUMBER() OVER(PARTITION BY adm4_code ORDER BY analysis_datetime_utc DESC, forecast_datetime_utc ASC) as rn
        FROM fact_forecast_3h
    ) ff3
    JOIN dim_adm4 adm ON ff3.adm4_code = adm.adm4_code AND ff3.rn = 1
    GROUP BY adm.nearest_grid_id
)
SELECT
    -- Base identifiers
    ath.grid_id,
    ath.datetime_hour_utc AS inference_datetime,
    EXTRACT(YEAR FROM ath.datetime_hour_utc)::INTEGER AS year,
    EXTRACT(MONTH FROM ath.datetime_hour_utc)::INTEGER AS month,
    
    -- Static features
    dg.centroid_lat,
    dg.centroid_lon,
    dg.province,
    dg.is_land,
    
    -- Temporal features (T = latest observation)
    ath.bt_mean_k AS th_bt_mean_k,
    ath.bt_max_k AS th_bt_max_k,
    ath.bt_min_k AS th_bt_min_k,
    ath.bt_std_k AS th_bt_std_k,
    ath.thermal_anomaly_count AS th_anomaly_count,
    ath.cloud_fraction AS th_cloud_fraction,
    ath.bt_change_max_1h AS th_bt_change_1h,
    
    -- Daily thermal running stats (previous completed day T-1 to prevent leakage)
    atd.bt_mean_k AS prev_day_bt_mean_k,
    atd.bt_max_k AS prev_day_bt_max_k,
    atd.daily_thermal_persistence AS prev_day_thermal_persistence,
    
    -- Antecedent weather (interpolated at T-1 day)
    ROUND(
        gw.w_kalbar * w_kb.t2m_max_c + 
        gw.w_kalteng * w_kt.t2m_max_c + 
        gw.w_kalsel * w_ks.t2m_max_c + 
        gw.w_kaltim * w_ki.t2m_max_c + 
        gw.w_kaltara * w_ku.t2m_max_c, 2
    )::DOUBLE AS prev_day_t2m_max_c,
    
    ROUND(
        gw.w_kalbar * w_kb.rh_min_pct + 
        gw.w_kalteng * w_kt.rh_min_pct + 
        gw.w_kalsel * w_ks.rh_min_pct + 
        gw.w_kaltim * w_ki.rh_min_pct + 
        gw.w_kaltara * w_ku.rh_min_pct, 1
    )::DOUBLE AS prev_day_rh_min_pct,
    
    ROUND(
        gw.w_kalbar * w_kb.precip_mm + 
        gw.w_kalteng * w_kt.precip_mm + 
        gw.w_kalsel * w_ks.precip_mm + 
        gw.w_kaltim * w_ki.precip_mm + 
        gw.w_kaltara * w_ku.precip_mm, 2
    )::DOUBLE AS prev_day_precip_mm,
    
    ROUND(
        gw.w_kalbar * w_kb.wind_speed_kmh + 
        gw.w_kalteng * w_kt.wind_speed_kmh + 
        gw.w_kalsel * w_ks.wind_speed_kmh + 
        gw.w_kaltim * w_ki.wind_speed_kmh + 
        gw.w_kaltara * w_ku.wind_speed_kmh, 2
    )::DOUBLE AS prev_day_wind_speed_kmh,
    
    ROUND(
        gw.w_kalbar * w_kb.soil_moisture_0_7cm + 
        gw.w_kalteng * w_kt.soil_moisture_0_7cm + 
        gw.w_kalsel * w_ks.soil_moisture_0_7cm + 
        gw.w_kaltim * w_ki.soil_moisture_0_7cm + 
        gw.w_kaltara * w_ku.soil_moisture_0_7cm, 3
    )::DOUBLE AS prev_day_soil_moisture,
    
    -- Rolling antecedent weather (T-1 day)
    ROUND(
        gw.w_kalbar * r_kb.rain_accum_7d_mm + 
        gw.w_kalteng * r_kt.rain_accum_7d_mm + 
        gw.w_kalsel * r_ks.rain_accum_7d_mm + 
        gw.w_kaltim * r_ki.rain_accum_7d_mm + 
        gw.w_kaltara * r_ku.rain_accum_7d_mm, 2
    )::DOUBLE AS rain_accum_7d_mm,
    
    ROUND(
        gw.w_kalbar * r_kb.rain_accum_30d_mm + 
        gw.w_kalteng * r_kt.rain_accum_30d_mm + 
        gw.w_kalsel * r_ks.rain_accum_30d_mm + 
        gw.w_kaltim * r_ki.rain_accum_30d_mm + 
        gw.w_kaltara * r_ku.rain_accum_30d_mm, 2
    )::DOUBLE AS rain_accum_30d_mm,
    
    ROUND(
        gw.w_kalbar * r_kb.consecutive_dry_days + 
        gw.w_kalteng * r_kt.consecutive_dry_days + 
        gw.w_kalsel * r_ks.consecutive_dry_days + 
        gw.w_kaltim * r_ki.consecutive_dry_days + 
        gw.w_kaltara * r_ku.consecutive_dry_days
    )::INTEGER AS consecutive_dry_days,
    
    ROUND(
        gw.w_kalbar * r_kb.t2m_anomaly_vs_30d_mean + 
        gw.w_kalteng * r_kt.t2m_anomaly_vs_30d_mean + 
        gw.w_kalsel * r_ks.t2m_anomaly_vs_30d_mean + 
        gw.w_kaltim * r_ki.t2m_anomaly_vs_30d_mean + 
        gw.w_kaltara * r_ku.t2m_anomaly_vs_30d_mean, 2
    )::DOUBLE AS t2m_anomaly_vs_30d_mean,
    
    -- Antecedent fire history (strictly < T)
    COALESCE(afh.hotspot_count_prev_24h, 0)::INTEGER AS hotspot_count_prev_24h,
    COALESCE(afh.hotspot_count_prev_7d, 0)::INTEGER AS hotspot_count_prev_7d,
    COALESCE(afh.max_frp_prev_7d, 0.0)::DOUBLE AS max_frp_prev_7d,
    COALESCE(afh.has_recent_fire_7d, FALSE)::BOOLEAN AS has_recent_fire_7d,
    
    -- QUARANTINED: Synthetic fuel features
    CAST(NULL AS DOUBLE) AS fuel_ndvi,
    CAST(NULL AS DOUBLE) AS fuel_evi,
    CAST(NULL AS DOUBLE) AS fuel_ndmi,
    CAST(NULL AS INTEGER) AS fuel_days_since_update,
    
    -- Forecasted Weather (BMKG) joined 1:1 without ADM4 fan-out
    gf.forecast_temp_c,
    gf.forecast_humidity_pct,
    gf.forecast_precip_mm,
    gf.forecast_wind_speed_kmh,
    gf.forecast_cloud_cover_pct

FROM latest_thermal lt
JOIN agg_thermal_hourly ath 
    ON lt.grid_id = ath.grid_id 
    AND lt.last_obs_time = ath.datetime_hour_utc
LEFT JOIN dim_grid dg ON ath.grid_id = dg.grid_id
JOIN dim_grid_weather_weights gw ON ath.grid_id = gw.grid_id

-- Previous completed day thermal stats (T-1)
LEFT JOIN agg_thermal_daily atd 
    ON ath.grid_id = atd.grid_id 
    AND atd.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE

-- 5 provincial station daily weather at T-1 day
LEFT JOIN fact_weather_daily w_kb ON w_kb.grid_id = 'G0249_0067' AND w_kb.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE
LEFT JOIN fact_weather_daily w_kt ON w_kt.grid_id = 'G0140_0296' AND w_kt.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE
LEFT JOIN fact_weather_daily w_ks ON w_ks.grid_id = 'G0084_0330' AND w_ks.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE
LEFT JOIN fact_weather_daily w_ki ON w_ki.grid_id = 'G0225_0458' AND w_ki.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE
LEFT JOIN fact_weather_daily w_ku ON w_ku.grid_id = 'G0392_0469' AND w_ku.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE

-- 5 provincial station rolling weather at T-1 day
LEFT JOIN agg_weather_rolling r_kb ON r_kb.grid_id = 'G0249_0067' AND r_kb.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE
LEFT JOIN agg_weather_rolling r_kt ON r_kt.grid_id = 'G0140_0296' AND r_kt.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE
LEFT JOIN agg_weather_rolling r_ks ON r_ks.grid_id = 'G0084_0330' AND r_ks.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE
LEFT JOIN agg_weather_rolling r_ki ON r_ki.grid_id = 'G0225_0458' AND r_ki.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE
LEFT JOIN agg_weather_rolling r_ku ON r_ku.grid_id = 'G0392_0469' AND r_ku.date_utc = (ath.datetime_hour_utc - INTERVAL 1 DAY)::DATE

-- Antecedent fire history (strictly < T)
LEFT JOIN agg_fire_history afh 
    ON ath.grid_id = afh.grid_id 
    AND afh.date_utc = CAST(ath.datetime_hour_utc AS DATE)

-- 1:1 aggregated forecast
LEFT JOIN grid_forecasts gf ON gf.grid_id = ath.grid_id
;
