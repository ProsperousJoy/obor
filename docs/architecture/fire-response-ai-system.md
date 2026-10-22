```text
[VIIRS] [Himawari] [Cuaca] [Environment]
              │
              ▼
┌─────────────────────────┐
│ 1. Fire Prediction      │──▶ Prediction (prob, lokasi, intensitas, luas, tren)
└─────────────────────────┘
              │
              ▼
┌─────────────────────────┐
│ 2. Trust Supervisor     │──▶ Trust (evidence, reliability, health, overall)
└─────────────────────────┘
              │
              ▼
┌─────────────────────────┐
│ 3. Impact Assessment    │──▶ Impact (skor, populasi, prioritas)
└─────────────────────────┘
              │
    ┌─────────┴─────────┐
    ▼                   ▼
┌──────────────┐  ┌──────────────┐
│ 4. Water     │  │ 5. Resource  │──▶ Rekomendasi air + pasukan terdekat
│    Agent     │  │    Agent     │
└──────────────┘  └──────────────┘
    │                   │
    └─────────┬─────────┘
              ▼
┌─────────────────────────┐
│ 6. Planning Agent       │──▶ Plan (aksi, dispatch, rute, steps, fallback)
└─────────────────────────┘
              │
              ▼
┌─────────────────────────┐
│ 7. Execution Agent      │──▶ Eksekusi sesuai authorization level
└─────────────────────────┘
              │
              ▼
┌─────────────────────────┐
│ 8. Monitoring/Replanning│──▶ Continue / Modify / Cancel / Escalate
└─────────────────────────┘
              │
              ▼ (incident selesai)
┌─────────────────────────┐
│ 9. Feedback/Learning    │──▶ Update kalibrasi, reliabilitas, retraining
└─────────────────────────┘
```



## Daftar Isi

- [1. Ringkasan Eksekutif](#1-ringkasan-eksekutif)
- [2. Arsitektur Sistem](#2-arsitektur-sistem)
- [3. Modul 1 — Model Prediksi Api (Fire Prediction Model)](#3-modul-1--model-prediksi-api-fire-prediction-model)
- [4. Modul 2 — Model Supervisor (Trust Supervisor)](#4-modul-2--model-supervisor-trust-supervisor)
- [5. Modul 3 — Model Dampak (Impact Assessment Model)](#5-modul-3--model-dampak-impact-assessment-model)
- [6. Modul 4 — Water Resource Agent](#6-modul-4--water-resource-agent)
- [7. Modul 5 — Resource Agent](#7-modul-5--resource-agent)
- [8. Modul 6 — Agent Planning](#8-modul-6--agent-planning)
- [9. Modul 7 — Execution Agent](#9-modul-7--execution-agent)
- [10. Modul 8 — Monitoring / Replanning Agent](#10-modul-8--monitoring--replanning-agent)
- [11. Modul 9 — Feedback / Learning Agent](#11-modul-9--feedback--learning-agent)
- [12. Referensi Enum & Kontrak Data](#12-referensi-enum--kontrak-data)
- [13. Contoh Alur End-to-End](#13-contoh-alur-end-to-end)
- [14. Langkah Implementasi Berikutnya](#14-langkah-implementasi-berikutnya)

---

---

## 3. Modul 1 — Model Prediksi Api (Fire Prediction Model)

### 3.1 Tujuan

Menentukan **kemungkinan ada api aktif** dan **lokasi kejadian**.

### 3.2 Input Parameter

#### 3.2.1 Identitas Observasi

| Field | Tipe | Contoh | Keterangan |
|-------|------|--------|------------|
| `hotspot_lat` | `float` | `-3.421` | Koordinat hotspot |
| `hotspot_lon` | `float` | `104.823` | Koordinat hotspot |
| `observation_time` | `string (ISO 8601)` | `"2026-09-20T14:30:00+07:00"` | Waktu observasi |

#### 3.2.2 Fitur VIIRS

| Field                       | Tipe                | Keterangan                     |
| --------------------------- | ------------------- | ------------------------------ |
| `confidence`                | `enum: l \| n \| h` | Confidence VIIRS               |
| `frp`                       | `float (MW)`        | Fire Radiative Power           |
| `brightness_temperature`    | `float (K)`         | Brightness temperature         |
| `delta_bt`                  | `float (K)`         | Selisih brightness temperature |
| `nearby_hotspot_count`      | `integer`           | Jumlah hotspot sekitar         |
| `detecting_satellite_count` | `integer`           | Jumlah satelit yang mendeteksi |

#### 3.2.3 Fitur Himawari

| Field | Tipe | Keterangan |
|-------|------|------------|
| `thermal_anomaly` | `boolean` | Anomali termal terdeteksi |
| `persistence_30m` | `boolean` | Persisten selama 30 menit |
| `persistence_1h` | `boolean` | Persisten selama 1 jam |
| `thermal_trend` | `enum` | `INCREASING \| STABLE \| DECREASING` |
| `cloud_coverage` | `float (0–1)` | Tutupan awan |

#### 3.2.4 Fitur Cuaca

| Field | Tipe | Keterangan |
|-------|------|------------|
| `temperature_c` | `float` | Temperatur (°C) |
| `humidity_pct` | `float` | Kelembapan (%) |
| `wind_speed_kph` | `float` | Kecepatan angin |
| `wind_direction_deg` | `float` | Arah angin (derajat) |
| `rainfall_24h_mm` | `float` | Curah hujan 24 jam |
| `rainfall_7d_mm` | `float` | Curah hujan 7 hari |

#### 3.2.5 Fitur Environment

| Field | Tipe | Keterangan |
|-------|------|------------|
| `is_peatland` | `boolean` | Lahan gambut / non-gambut |
| `land_cover` | `string` | Kelas tutupan lahan |
| `inarisk_fire_hazard` | `enum` | Tingkat bahaya InaRISK |

### 3.3 Process

```text
Feature Engineering
        ↓
Fire Classification Model
        ↓
Spatio-Temporal Clustering
```

Catatan implementasi:

- Feature engineering menggabungkan lintas sensor (VIIRS + Himawari + cuaca + environment).
- Clustering spasio-temporal mengelompokkan hotspot berdekatan menjadi satu `incident_id`.

### 3.4 Output Parameter

| Field | Tipe | Keterangan |
|-------|------|------------|
| `incident_id` | `string` | ID insiden, contoh `OKI-1029` |
| `lat` | `float` | Prediksi latitude |
| `lon` | `float` | Prediksi longitude |
| `prediction_time` | `string (ISO 8601)` | Waktu prediksi |
| `fire_probability` | `float (0–1)` | Probabilitas kebakaran |
| `fire_status` | `enum` | `UNVERIFIED \| SUSPECTED \| PROBABLE \| CONFIRMED` |
| `fire_intensity` | `enum` | `LOW \| MEDIUM \| HIGH` |
| `estimated_area_ha` | `float` | Estimasi luas (hektare) |
| `trend` | `enum` | `INCREASING \| STABLE \| DECREASING` |
| `model_version` | `string` | Versi model prediksi |

### 3.5 Contoh

```json
{
  "incident_id": "OKI-1029",
  "lat": -3.421,
  "lon": 104.823,
  "prediction_time": "2026-09-20T14:30:00+07:00",
  "fire_probability": 0.91,
  "fire_status": "PROBABLE",
  "fire_intensity": "HIGH",
  "estimated_area_ha": 12.4,
  "trend": "INCREASING",
  "model_version": "fire-clf-v1.2.0"
}
```

---

## 4. Modul 2 — Model Supervisor (Trust Supervisor)

### 4.1 Tujuan

Komponen terpenting dari tema **Autonomous & Adaptive AI**.

Supervisor tidak bertanya:

> Apakah ada api?

Tetapi:

> Apakah saya dapat mempercayai prediksi model api ini?

### 4.2 Input Parameter

#### Current Prediction

```json
{
  "fire_probability": 0.91,
  "predicted_lat": -3.421,
  "predicted_lon": 104.823,
  "prediction_time": "2026-09-20T14:30:00+07:00"
}
```

#### Evidence

| Field | Tipe |
|-------|------|
| `viirs_result` | `object` |
| `himawari_result` | `object` |
| `weather_result` | `object` |
| `field_report` | `object \| null` |

#### Data Quality

| Field | Tipe | Keterangan |
|-------|------|------------|
| `data_freshness_minutes` | `integer` | Umur data (menit) |
| `missing_data` | `string[]` | Daftar field yang hilang |
| `cloud_coverage` | `float (0–1)` | Tutupan awan |
| `independent_source_count` | `integer` | Jumlah sumber independen |

#### Historical

| Field | Tipe |
|-------|------|
| `prediction_history` | `object[]` |
| `previous_fire_probability` | `float \| null` |
| `previous_trust_score` | `float \| null` |

#### Ground Truth / Outcome

| Field | Tipe |
|-------|------|
| `real_fire_confirmed` | `boolean \| null` |
| `real_fire_lat` | `float \| null` |
| `real_fire_lon` | `float \| null` |
| `actual_burn_area_ha` | `float \| null` |
| `field_verified` | `boolean` |

#### Model Information

| Field | Tipe |
|-------|------|
| `historical_accuracy` | `float (0–1)` |
| `calibration_error` | `float` |
| `false_positive_rate` | `float` |
| `false_negative_rate` | `float` |
| `ood_score` | `float` |

### 4.3 Process

```text
Current Prediction
        +
Historical Performance
        +
Cross Sensor Agreement
        +
Data Quality
        +
Ground Truth Feedback
        ↓
Trust / Reliability Assessment
```

### 4.4 Output Parameter

| Field | Tipe | Keterangan |
|-------|------|------------|
| `evidence_trust` | `float (0–1)` | Kepercayaan bukti lintas sensor |
| `model_reliability` | `float (0–1)` | Reliabilitas model |
| `data_health` | `float (0–1)` | Kesehatan data |
| `overall_trust` | `float (0–1)` | Skor kepercayaan gabungan |
| `evidence_agreement` | `string` | Ringkasan kesepakatan sensor |
| `prediction_error_estimate` | `float \| null` | Estimasi error prediksi |
| `ood_status` | `enum` | `IN_DISTRIBUTION \| OOD_SUSPECTED \| OOD_CONFIRMED` |
| `trust_level` | `enum` | `LOW \| MEDIUM \| HIGH` |
| `autonomous_action_allowed` | `boolean` | Boleh aksi otonom? |
| `human_verification_required` | `boolean` | Butuh verifikasi manusia? |
| `reason` | `string[]` | Alasan yang dapat dibaca manusia |

### 4.5 Contoh

```json
{
  "incident_id": "OKI-1029",
  "evidence_trust": 0.88,
  "model_reliability": 0.84,
  "data_health": 0.95,
  "overall_trust": 0.89,
  "evidence_agreement": "VIIRS and Himawari agree",
  "prediction_error_estimate": 0.07,
  "ood_status": "IN_DISTRIBUTION",
  "trust_level": "HIGH",
  "autonomous_action_allowed": true,
  "human_verification_required": false,
  "reason": [
    "VIIRS and Himawari agree",
    "Thermal anomaly persisted for 50 minutes",
    "Data freshness < 15 minutes"
  ]
}
```

---

## 5. Modul 3 — Model Dampak (Impact Assessment Model)

### 5.1 Tujuan

Menjawab:

> Kalau api ini benar, seberapa berbahaya?

### 5.2 Input Parameter

#### Fire

| Field | Tipe |
|-------|------|
| `fire_lat` | `float` |
| `fire_lon` | `float` |
| `fire_probability` | `float (0–1)` |
| `fire_intensity` | `enum: LOW \| MEDIUM \| HIGH` |
| `estimated_area_ha` | `float` |
| `growth_trend` | `enum: INCREASING \| STABLE \| DECREASING` |

#### Population

| Field             | Tipe      |
| ----------------- | --------- |
| `population_1km`  | `integer` |
| `population_5km`  | `integer` |
| `population_10km` | `integer` |

#### Infrastructure

| Field | Tipe |
|-------|------|
| `distance_to_settlement_km` | `float` |
| `distance_to_school_km` | `float` |
| `distance_to_hospital_km` | `float` |
| `distance_to_road_km` | `float` |
| `distance_to_critical_infra_km` | `float` |

#### Environment

| Field | Tipe |
|-------|------|
| `is_peatland` | `boolean` |
| `is_protected_area` | `boolean` |
| `is_forest_area` | `boolean` |

#### Weather

| Field | Tipe |
|-------|------|
| `wind_speed_kph` | `float` |
| `wind_direction_deg` | `float` |

### 5.3 Output Parameter

| Field | Tipe | Keterangan |
|-------|------|------------|
| `impact_score` | `integer (0–100)` | Skor dampak gabungan |
| `population_at_risk` | `integer` | Populasi berisiko |
| `infrastructure_at_risk` | `string[]` | Infrastruktur berisiko |
| `ecosystem_risk` | `enum` | `LOW \| MEDIUM \| HIGH \| CRITICAL` |
| `smoke_exposure_risk` | `enum` | `LOW \| MEDIUM \| HIGH \| CRITICAL` |
| `settlement_distance_km` | `float` | Jarak ke permukiman |
| `wind_toward_population` | `boolean` | Angin menuju populasi? |
| `priority` | `enum` | `LOW \| MEDIUM \| HIGH \| CRITICAL` |

### 5.4 Contoh

```json
{
  "incident_id": "OKI-1029",
  "impact_score": 91,
  "population_at_risk": 12400,
  "infrastructure_at_risk": ["school_1.8km", "hospital_4.2km"],
  "ecosystem_risk": "HIGH",
  "smoke_exposure_risk": "HIGH",
  "settlement_distance_km": 2.1,
  "wind_toward_population": true,
  "priority": "CRITICAL"
}
```

---

## 6. Modul 4 — Water Resource Agent

### 6.1 Tujuan

Menjawab:

> Jika kita harus memadamkan api, dari mana air terbaik dapat diambil?

### 6.2 Input Parameter

#### Fire

```json
{
  "fire_lat": -3.421,
  "fire_lon": 104.823
}
```

#### Water Sources (per kandidat)

| Field | Tipe | Contoh |
|-------|------|--------|
| `source_id` | `string` | `"EMBUNG-OKI-12"` |
| `source_lat` | `float` | `-3.435` |
| `source_lon` | `float` | `104.801` |
| `water_type` | `enum` | `RIVER \| LAKE \| EMBUNG \| CANAL \| WELL` |
| `capacity_m3` | `float` | Kapasitas (m³) |
| `surface_area_m2` | `float` | Luas permukaan |
| `current_water_detection` | `boolean` | Air terdeteksi saat ini? |
| `historical_water_permanence` | `float (0–1)` | Permanensi historis |

#### Accessibility

| Field | Tipe |
|-------|------|
| `road_network` | `object` |
| `route_distance_km` | `float` |
| `terrain` | `string` |
| `elevation_m` | `float` |
| `slope_deg` | `float` |

#### Field

| Field | Tipe |
|-------|------|
| `water_confirmed` | `boolean \| null` |
| `pump_access` | `boolean \| null` |

### 6.3 Process

```text
Untuk setiap kandidat:

Distance
  +
Water Availability
  +
Accessibility
  +
Pump Feasibility
  +
Data Trust
  ↓
Water Suitability Score
```

### 6.4 Output Parameter

| Field | Tipe |
|-------|------|
| `recommended_water_source` | `string` |
| `lat` | `float` |
| `lon` | `float` |
| `water_type` | `enum` |
| `distance_km` | `float` |
| `route_distance_km` | `float` |
| `estimated_travel_time_min` | `integer` |
| `estimated_capacity_m3` | `float` |
| `water_availability` | `float (0–1)` |
| `accessibility` | `float (0–1)` |
| `pump_feasibility` | `float (0–1)` |
| `water_suitability` | `float (0–1)` |
| `backup_water_sources` | `object[]` |

### 6.5 Contoh

```json
{
  "incident_id": "OKI-1029",
  "recommended_water_source": "Embung OKI-12",
  "lat": -3.435,
  "lon": 104.801,
  "water_type": "EMBUNG",
  "distance_km": 1.8,
  "route_distance_km": 2.4,
  "estimated_travel_time_min": 12,
  "estimated_capacity_m3": 4500,
  "water_availability": 0.93,
  "accessibility": 0.87,
  "pump_feasibility": 0.91,
  "water_suitability": 0.89,
  "backup_water_sources": [
    {
      "name": "Sungai Komering-A",
      "distance_km": 3.1,
      "water_suitability": 0.78
    }
  ]
}
```

---

## 7. Modul 5 — Resource Agent

### 7.1 Tujuan

Menjawab:

> Siapa yang tersedia untuk menangani kebakaran?

### 7.2 Input Parameter

#### Incident

| Field | Tipe |
|-------|------|
| `fire_lat` | `float` |
| `fire_lon` | `float` |
| `priority` | `enum: LOW \| MEDIUM \| HIGH \| CRITICAL` |
| `fire_size_ha` | `float` |
| `fire_intensity` | `enum: LOW \| MEDIUM \| HIGH` |

#### Firefighter HQ (per kandidat)

| Field | Tipe |
|-------|------|
| `hq_id` | `string` |
| `hq_name` | `string` |
| `hq_lat` | `float` |
| `hq_lon` | `float` |

#### Personnel

| Field | Tipe |
|-------|------|
| `crew_available` | `integer` |
| `crew_on_duty` | `integer` |
| `crew_skills` | `string[]` |

#### Equipment

| Field | Tipe |
|-------|------|
| `fire_truck` | `integer` |
| `pump` | `integer` |
| `hose_m` | `integer` |
| `water_tanker` | `integer` |
| `drone` | `integer` |
| `helicopter_available` | `boolean` |

#### Operational

| Field | Tipe |
|-------|------|
| `current_crew_assignment` | `string[]` |
| `crew_status` | `enum` |
| `vehicle_status` | `enum` |

#### Communication

| Field | Tipe |
|-------|------|
| `hq_contact` | `string` |
| `radio_channel` | `string` |
| `phone` | `string` |

### 7.3 Output Parameter

| Field | Tipe |
|-------|------|
| `hq` | `string` |
| `hq_lat` | `float` |
| `hq_lon` | `float` |
| `distance_km` | `float` |
| `eta_minutes` | `integer` |
| `available_crew` | `integer` |
| `recommended_crew` | `integer` |
| `equipment` | `object` |
| `missing_equipment` | `string[]` |
| `hq_contact` | `string` |
| `readiness_score` | `float (0–1)` |

### 7.4 Contoh

```json
{
  "incident_id": "OKI-1029",
  "hq": "Manggala Agni Daops Banyuasin",
  "hq_lat": -3.31,
  "hq_lon": 104.9,
  "distance_km": 12.4,
  "eta_minutes": 27,
  "available_crew": 12,
  "recommended_crew": 8,
  "equipment": {
    "vehicle": 2,
    "portable_pump": 4,
    "water_tanker": 1,
    "drone": 1
  },
  "missing_equipment": ["helicopter"],
  "hq_contact": "+62-812-xxxx-xxxx",
  "readiness_score": 0.86
}
```

---

## 8. Modul 6 — Agent Planning

### 8.1 Tujuan

Planning Agent **tidak memprediksi api sendiri**. Ia menerima output dari agent-agent sebelumnya dan menghasilkan **PLAN**.

### 8.2 Input Parameter

#### FIRE

| Field | Sumber |
|-------|--------|
| `predicted_fire_lat/lon` | Modul 1 |
| `fire_probability` | Modul 1 |
| `fire_area_ha` | Modul 1 |
| `fire_trend` | Modul 1 |

#### TRUST

| Field | Sumber |
|-------|--------|
| `trust_score` | Modul 2 |
| `autonomous_action_allowed` | Modul 2 |
| `human_verification_required` | Modul 2 |

#### IMPACT

| Field | Sumber |
|-------|--------|
| `impact_score` | Modul 3 |
| `priority` | Modul 3 |
| `population_at_risk` | Modul 3 |

#### WATER

| Field | Sumber |
|-------|--------|
| `recommended_water_source` | Modul 4 |
| `water_lat/lon` | Modul 4 |
| `water_distance_km` | Modul 4 |
| `water_suitability` | Modul 4 |

#### RESOURCE

| Field | Sumber |
|-------|--------|
| `nearest_hq` | Modul 5 |
| `available_crew` | Modul 5 |
| `equipment` | Modul 5 |
| `eta_minutes` | Modul 5 |
| `hq_contact` | Modul 5 |

#### ROUTE

| Field | Tipe |
|-------|------|
| `road_network` | `object` |
| `fire_access_route` | `object` |
| `water_access_route` | `object` |

#### RULES

| Field | Tipe | Contoh |
|-------|------|--------|
| `safety_sop` | `string` | `"SOP-KARHUTLA-v3"` |
| `minimum_crew` | `integer` | `6` |
| `maximum_travel_distance_km` | `float` | `50.0` |
| `human_approval_policy` | `string` | `"CRITICAL always requires approval"` |

### 8.3 Output: PLAN

| Field | Tipe |
|-------|------|
| `plan_id` | `string` |
| `priority` | `enum` |
| `action` | `enum: MONITOR \| GROUND_RESPONSE \| AIR_RESPONSE \| EVACUATION_SUPPORT` |
| `dispatch` | `object` |
| `water_source` | `object` |
| `eta_minutes` | `integer` |
| `steps` | `string[]` |
| `communication_target` | `string[]` |
| `human_approval_required` | `boolean` |
| `fallback_plan` | `object` |
| `replan_conditions` | `string[]` |

### 8.4 Contoh

```json
{
  "plan_id": "PLAN-OKI-1029-001",
  "incident_id": "OKI-1029",
  "priority": "CRITICAL",
  "action": "GROUND_RESPONSE",
  "dispatch": {
    "hq": "Manggala Agni Banyuasin",
    "crew": 8,
    "equipment": [
      "2 portable pumps",
      "1 tanker",
      "300m hose",
      "1 drone"
    ]
  },
  "water_source": {
    "name": "Embung OKI-12",
    "distance_from_fire_km": 1.8
  },
  "route": {
    "hq_to_fire": "western access road",
    "fire_to_water": "2.4km via plantation track"
  },
  "eta_minutes": 27,
  "steps": [
    "Contact HQ",
    "Dispatch verification drone",
    "Send 8-person ground team",
    "Approach from western access road",
    "Establish water supply from Embung OKI-12",
    "Protect settlement southeast of incident"
  ],
  "communication_target": ["command_center", "hq_banyuasin"],
  "human_approval_required": true,
  "fallback_plan": {
    "condition": "Embung OKI-12 inaccessible",
    "action": "Switch to Sungai Komering-A"
  },
  "replan_conditions": [
    "wind shift > 45 degrees",
    "water source unavailable",
    "crew reassigned"
  ]
}
```

---

## 9. Modul 7 — Execution Agent

### 9.1 Tujuan

Planning menghasilkan:

> Apa yang seharusnya dilakukan?

Execution Agent menentukan:

> Apa yang boleh saya lakukan sekarang?

### 9.2 Input Parameter

| Field | Tipe | Keterangan |
|-------|------|------------|
| `plan` | `object` | Output Modul 6 |
| `trust_score` | `float` | Output Modul 2 |
| `authorization_level` | `enum` | `AUTO_LOW \| AUTO_MEDIUM \| MANUAL_ONLY` |
| `current_incident_state` | `enum` | `NEW \| VERIFIED \| RESPONDING \| CONTAINED \| RESOLVED` |
| `hq_contact` | `string` | Kontak HQ |
| `api_availability` | `object` | Ketersediaan API / komunikasi |

### 9.3 Output Parameter

| Field | Tipe |
|-------|------|
| `alert_sent` | `boolean` |
| `hq_contacted` | `boolean` |
| `ground_verification_requested` | `boolean` |
| `operator_approval_requested` | `boolean` |
| `action_execution_status` | `enum: PENDING \| EXECUTING \| COMPLETED \| FAILED` |
| `executed_actions` | `string[]` |
| `blocked_actions` | `string[]` |

### 9.4 Matriks Otorisasi (Contoh: Trust = HIGH)

Boleh otomatis:

- [x] Notify command center
- [x] Request field verification
- [x] Notify nearby HQ
- [x] Generate route

Tidak boleh otomatis:

- [ ] Deploy helicopter
- [ ] Evacuation
- [ ] Large resource deployment

### 9.5 Contoh

```json
{
  "incident_id": "OKI-1029",
  "plan_id": "PLAN-OKI-1029-001",
  "action_execution_status": "EXECUTING",
  "alert_sent": true,
  "hq_contacted": true,
  "ground_verification_requested": true,
  "operator_approval_requested": true,
  "executed_actions": [
    "notify_command_center",
    "request_field_verification",
    "notify_nearby_hq",
    "generate_route"
  ],
  "blocked_actions": [
    "deploy_helicopter",
    "evacuation",
    "large_resource_deployment"
  ]
}
```

---

## 10. Modul 8 — Monitoring / Replanning Agent

### 10.1 Tujuan

Membuat sistem benar-benar **Adaptive**. Setelah plan dibuat

Contoh kronologi:

```text
15:00 — fire_probability = 81%
15:10 — wind berubah
15:20 — fire growing
15:25 — embung ternyata inaccessible
15:30 — crew A dipakai insiden lain
```

→ Agent harus melakukan replan.

### 10.2 Input Parameter

| Field                 | Sumber           |
| --------------------- | ---------------- |
| `previous_plan`       | Modul 6          |
| `new_fire_prediction` | Modul 1          |
| `new_weather`         | Sensor cuaca     |
| `new_himawari`        | Himawari         |
| `new_viirs`           | VIIRS            |
| `crew_status`         | Modul 5          |
| `water_source_status` | Modul 4\         |
| `road_status`         | Jaringan jalan   |
| `field_report`        | Laporan lapangan |
| `execution_status`    | Modul 7          |

### 10.3 Output Parameter

| Field | Tipe |
|-------|------|
| `decision` | `enum: CONTINUE \| MODIFY \| CANCEL \| ESCALATE` |
| `replan` | `boolean` |
| `reason` | `string[]` |
| `old_priority` | `enum` |
| `new_priority` | `enum` |
| `old_water_source` | `string \| null` |
| `new_water_source` | `string \| null` |
| `new_crew` | `integer \| null` |
| `new_route` | `object \| null` |
| `new_eta_minutes` | `integer \| null` |

### 10.4 Contoh

```json
{
  "incident_id": "OKI-1029",
  "decision": "MODIFY",
  "replan": true,
  "reason": [
    "Wind shifted toward settlement",
    "Primary water source unavailable"
  ],
  "old_priority": "HIGH",
  "new_priority": "CRITICAL",
  "old_water_source": "River A",
  "new_water_source": "Embung B",
  "new_crew": 10,
  "new_route": {
    "hq_to_fire": "eastern access road"
  },
  "new_eta_minutes": 34
}
```

---

## 11. Modul 9 — Feedback / Learning Agent

### 11.1 Tujuan

Bagian **Adaptive AI jangka panjang**. Memberi poin besar untuk hackathon karena sistem belajar setelah insiden selesai.

### 11.2 Input Parameter

#### Prediction

| Field | Tipe |
|-------|------|
| `predicted_fire_probability` | `float` |
| `predicted_lat/lon` | `float` |
| `predicted_area_ha` | `float` |
| `predicted_impact` | `object` |

#### Plan

| Field | Tipe |
|-------|------|
| `recommended_resources` | `object` |
| `recommended_water_source` | `string` |
| `predicted_eta_minutes` | `integer` |

#### Actual Outcome

| Field | Tipe |
|-------|------|
| `fire_confirmed` | `boolean` |
| `actual_lat/lon` | `float` |
| `actual_burn_area_ha` | `float` |
| `actual_resources_used` | `object` |
| `actual_water_source_used` | `string` |
| `actual_response_time_min` | `integer` |
| `fire_controlled_time` | `string (ISO 8601)` |

### 11.3 Output Parameter

| Field | Tipe |
|-------|------|
| `prediction_error` | `float` |
| `location_error_km` | `float` |
| `area_prediction_error_ha` | `float` |
| `plan_success_score` | `float (0–1)` |
| `water_recommendation_accuracy` | `float (0–1)` |
| `resource_recommendation_accuracy` | `float (0–1)` |
| `updated_source_reliability` | `object` |
| `updated_model_performance` | `object` |
| `retraining_candidate` | `boolean` |

### 11.4 Contoh Loop Belajar

```text
Prediction:
  90% fire probability

Outcome:
  No fire
    ↓
False positive
    ↓
Supervisor updates calibration
```

```text
Recommended:
  River A

Field outcome:
  River A dry
    ↓
Water source reliability reduced
```

### 11.5 Contoh JSON

```json
{
  "incident_id": "OKI-1029",
  "prediction_error": 0.9,
  "location_error_km": 0.4,
  "area_prediction_error_ha": 3.2,
  "plan_success_score": 0.72,
  "water_recommendation_accuracy": 0.0,
  "resource_recommendation_accuracy": 0.85,
  "updated_source_reliability": {
    "River A": 0.42,
    "Embung OKI-12": 0.91
  },
  "updated_model_performance": {
    "fire-clf-v1.2.0": {
      "accuracy": 0.83,
      "calibration_error": 0.11
    }
  },
  "retraining_candidate": true
}
```

---

## 12. Referensi Enum & Kontrak Data

### 12.1 Enum Terpusat

```typescript
// Fire
type FireStatus = 'UNVERIFIED' | 'SUSPECTED' | 'PROBABLE' | 'CONFIRMED';
type FireIntensity = 'LOW' | 'MEDIUM' | 'HIGH';
type FireTrend = 'INCREASING' | 'STABLE' | 'DECREASING';

// Trust
type TrustLevel = 'LOW' | 'MEDIUM' | 'HIGH';
type OodStatus = 'IN_DISTRIBUTION' | 'OOD_SUSPECTED' | 'OOD_CONFIRMED';

// Impact
type Priority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

// Water
type WaterType = 'RIVER' | 'LAKE' | 'EMBUNG' | 'CANAL' | 'WELL';

// Planning
type ResponseAction = 'MONITOR' | 'GROUND_RESPONSE' | 'AIR_RESPONSE' | 'EVACUATION_SUPPORT';

// Execution
type ExecutionStatus = 'PENDING' | 'EXECUTING' | 'COMPLETED' | 'FAILED';

// Replanning
type ReplanDecision = 'CONTINUE' | 'MODIFY' | 'CANCEL' | 'ESCALATE';
```

### 12.2 Aturan Kontrak

1. Semua waktu memakai **ISO 8601 dengan timezone**, contoh: `"2026-09-20T14:30:00+07:00"`.
2. Semua koordinat memakai **WSG84 decimal degrees**.
3. Semua skor `0–1` memakai `float`; skor dampak `0–100` memakai `integer`.
4. Setiap output modul wajib membawa `incident_id`.
5. Setiap model wajib membawa `model_version`, contoh: `"fire-clf-v1.2.0"`.

---

## 13. Contoh Alur End-to-End

```json
{
  "incident_id": "OKI-1029",
  "fire_prediction": {
    "fire_probability": 0.91,
    "fire_status": "PROBABLE"
  },
  "trust": {
    "overall_trust": 0.89,
    "trust_level": "HIGH",
    "autonomous_action_allowed": true
  },
  "impact": {
    "impact_score": 91,
    "priority": "CRITICAL"
  },
  "plan": {
    "plan_id": "PLAN-OKI-1029-001",
    "action": "GROUND_RESPONSE"
  },
  "execution": {
    "action_execution_status": "EXECUTING"
  }
}
```

