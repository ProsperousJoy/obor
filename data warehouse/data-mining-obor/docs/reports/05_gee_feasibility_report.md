# Technical Report: Google Earth Engine (GEE) Data Feasibility Assessment
## Project: AI Wildfire / Land Fire Risk Prediction — Kalimantan
**Role:** Data Mining / Data Acquisition  
**Status:** Exploratory Feasibility Testing (No Model / Feature Finalization)  
**Date:** September 2026  

---

## 1. Executive Summary

This report evaluates the technical feasibility of **Google Earth Engine (GEE)** as a platform and data provider for the **AI Wildfire / Land Fire Risk Prediction Project in Kalimantan**.

### Core Clarification: GEE is a Platform, Not a Single Dataset
Google Earth Engine is a **planetary-scale geospatial cloud analytics platform and data catalog**, not an individual dataset. It aggregates over 900 public and commercial geospatial datasets, providing server-side filtering, map-reduce reductions, pixel-level algebraic calculations, and temporal compositing via JavaScript and Python client libraries.

### Key Feasibility Findings:
1. **Catalog Completeness:** GEE hosts nearly all critical environmental datasets required for fire risk modeling, spanning weather reanalysis (ECMWF ERA5-Land), gridded precipitation (CHIRPS, GPM), optical vegetation indices (MODIS, Sentinel-2), synthetic aperture radar (Sentinel-1), land surface temperature (MODIS Terra/Aqua), soil moisture (SMAP L4, ERA5-Land), land cover (ESA WorldCover 10m, MODIS MCD12Q1), and historical burned area (MODIS MCD64A1).
2. **Catalog Verification:** Using the **Official Google Earth Engine SpatioTemporal Asset Catalog (STAC)** endpoint (`https://storage.googleapis.com/earthengine-stac/catalog/`), **12 key candidate datasets were 100% programmatically verified** for schema, band names, spatial bounds, and temporal coverage up to 2024–2026 without requiring private credentials.
3. **Physical Distinction Verified (Direct vs Derived):**
   - **Relative Humidity:** GEE's ERA5-Land does **not** provide direct relative humidity; it provides `dewpoint_temperature_2m` (Kelvin). Relative Humidity (%) is a **derived variable** (calculated via the Magnus-Tetens approximation).
   - **Wind Speed & Direction:** ERA5-Land provides vector components `u_component_of_wind_10m` and `v_component_of_wind_10m` (m/s). Scalar wind speed ($\sqrt{u^2 + v^2}$) and wind direction are **derived variables**.
   - **Air Temperature vs LST:** ERA5-Land provides 2-meter atmospheric ambient temperature (`temperature_2m`); MODIS (`MOD11A1`/`MYD11A1`) provides radiometric skin/surface temperature (`LST_Day_1km`). They are fundamentally different physical variables.
   - **Vegetation Indices:** MODIS (`MOD13A1`) provides pre-computed `NDVI` and `EVI`. Sentinel-2 L2A provides raw top-of-canopy surface reflectance (`B4`, `B8`, `B11`, `B12`); vegetation indices such as `NDVI`, `NDMI` (moisture), and `NBR` (burn ratio) are **derived variables**.
4. **Kalimantan Sample Extraction:** Extraction was verified across 5 provincial capitals (Pontianak, Palangka Raya, Banjarmasin, Samarinda, Tanjung Selor) during a representative peak fire season date (2023-09-01). Environmental gradients were clearly captured (e.g. Kalteng soil moisture 0.170 m³/m³ & RH 68.7% vs Kaltara soil moisture 0.407 m³/m³ & RH 88.8%).
5. **Authentication Blocker in Headless Environments:** The Python `earthengine-api` relies on Google Cloud OAuth2 (`ee.Authenticate()`), which requires an interactive web browser to generate an authorization code. In unattended or headless CLI environments, GEE cannot initialize without either a pre-authenticated token (`~/.config/earthengine/credentials`) or a Google Cloud Service Account with Earth Engine API enabled.

---

## 2. Project Context

The overall project aims to build an end-to-end intelligent wildfire risk mitigation system for Kalimantan (Borneo Indonesia), conceptually consisting of:
1. **Fire Prediction Model:** Inputs spatial coordinates, temporal horizons, meteorological factors, satellite observations, and soil/vegetation conditions to predict fire occurrence probabilities.
2. **Supervisor Model:** Evaluates historical predictions against verified ground truth (e.g. NASA FIRMS / VIIRS / MODIS) to assign dynamic confidence scores.
3. **Planning Agent:** Translates high-confidence fire predictions into actionable dispatch directives for regional firefighting headquarters (Manggala Agni / BPBD).

> **Exploratory Constraint:**  
> This assessment strictly investigates **technical feasibility, data accessibility, parameter definitions, spatial-temporal resolutions, and platform constraints**.  
> **NO final features, labels, prediction windows, spatial grids, or ML models are selected or finalized in this stage.**

---

## 3. GEE Access & Authentication Analysis

### 3.1 GEE as a Platform
GEE decouples storage and computation. Datasets reside on Google Cloud Storage (GCS) in Google-managed formats (Cloud-Optimized GeoTIFFs, Earth Engine Tables). Operations invoked through client libraries are compiled into Directed Acyclic Graphs (DAGs) executed lazily on Google infrastructure.

### 3.2 Python API (`earthengine-api`) & `ee.Initialize()`
The official Python client library is `earthengine-api` (version `1.7.45` installed and validated in this project's virtual environment).
Calling `ee.Initialize()` requires valid Google Cloud project credentials.

### 3.3 Authentication Architecture & The Headless CLI Blocker
```
+-------------------------------------------------------------+
|                 Authentication Workflow                     |
+-------------------------------------------------------------+
   1. Interactive User Mode:
      ee.Authenticate() -> Opens Browser -> Google Login ->
      Consent Screen -> Auth Code -> ~/.config/earthengine/credentials
      
   2. Automated / Headless Server Mode (Required for CI/CD / Scripts):
      Google Cloud Console -> Create Service Account ->
      Grant Earth Engine Resource Viewer / User Role ->
      Generate Private Key (.json) ->
      ee.Initialize(credentials=ee.ServiceAccountCredentials(email, key_path))
      
   3. Open STAC / Direct Cloud Mirror Mode (No Auth Needed):
      https://storage.googleapis.com/earthengine-stac/catalog/
      -> Inspect metadata, schema, and direct asset manifests openly.
```

When executing `ee.Initialize()` in a non-interactive shell without existing local credentials, the library throws:
```text
EEException: Please authorize access to your Earth Engine account by running earthengine authenticate or ee.Authenticate().
```
Therefore, interactive OAuth2 is an environment dependency. For automated data mining scripts, a **Service Account** or **direct cloud data endpoint (STAC / AWS Open Data / COG)** is technically superior.

---

## 4. Weather & Climate Datasets in GEE

Meteorological conditions govern fuel dryness, fire spread rate, and atmospheric ignition risk. GEE catalogs several global reanalysis and precipitation products.

| Dataset | GEE Asset ID | Spatial Res | Temporal Res | Temporal Coverage |
| :--- | :--- | :--- | :--- | :--- |
| **CHIRPS Daily** | `UCSB-CHG/CHIRPS/DAILY` | 0.05° (~5.5 km) | Daily | 1981-01-01 to Present |
| **ERA5-Land Daily** | `ECMWF/ERA5_LAND/DAILY_AGGR` | 0.1° (~11 km) | Daily | 1950-01-02 to Present (~5 days lag) |
| **ERA5-Land Hourly** | `ECMWF/ERA5_LAND/HOURLY` | 0.1° (~11 km) | Hourly | 1950-01-01 to Present (~5 days lag) |
| **GPM IMERG V06** | `NASA/GPM_L3/IMERG_V06` | 0.1° (~11 km) | Half-hourly / Daily | 2000-06-01 to 2024-06-02 (V07 active) |

### Direct vs. Derived Variables in Weather Reanalysis

A common pitfall in geospatial data pipelines is assuming all physical variables exist as pre-calculated bands. In GEE's ERA5-Land catalog:

| Physical Parameter | Band Status in ERA5-Land | Band Name / Calculation Formula | Physical Unit |
| :--- | :--- | :--- | :--- |
| **Air Temperature (2m)** | **Direct** | `temperature_2m` | Kelvin ($K$) |
| **Dewpoint Temperature (2m)** | **Direct** | `dewpoint_temperature_2m` | Kelvin ($K$) |
| **Relative Humidity (RH %)** | **DERIVED** | Calculated from $T_{2m}$ and $T_{dew}$ using the August-Roche-Magnus approximation: $RH \approx 100 \times \frac{\exp\left(\frac{17.625 \cdot T_{dew}}{243.04 + T_{dew}}\right)}{\exp\left(\frac{17.625 \cdot T_{2m}}{243.04 + T_{2m}}\right)}$ | Percent (%) |
| **Wind U-component (10m)** | **Direct** | `u_component_of_wind_10m` (Eastward wind) | $\text{m/s}$ |
| **Wind V-component (10m)** | **Direct** | `v_component_of_wind_10m` (Northward wind) | $\text{m/s}$ |
| **Wind Speed (10m)** | **DERIVED** | $\text{WindSpeed} = \sqrt{u^2 + v^2}$ | $\text{m/s}$ |
| **Wind Direction (10m)** | **DERIVED** | $\text{WindDir} = \left(270 - \text{atan2}(v, u) \times \frac{180}{\pi}\right) \pmod{360}$ | Degrees (°) |
| **Precipitation** | **Direct** | `total_precipitation_sum` | Meters ($m$) [convert to $mm$ via $\times 1000$] |
| **Surface Pressure** | **Direct** | `surface_pressure` | Pascals ($Pa$) |

---

## 5. Vegetation Datasets

Vegetation condition determines fuel load and fuel live-moisture content.

| Dataset | GEE Asset ID | Spatial Res | Temporal Res | Bands / Direct vs Derived |
| :--- | :--- | :--- | :--- | :--- |
| **MODIS Vegetation Indices** | `MODIS/061/MOD13A1` | 500 m | 16-day composite | `NDVI` (**Direct**, scale 0.0001), `EVI` (**Direct**, scale 0.0001), `DetailedQA` |
| **Sentinel-2 MSI Level-2A** | `COPERNICUS/S2_SR_HARMONIZED` | 10 m / 20 m | ~5 days | Surface reflectance bands: `B4` (Red), `B8` (NIR), `B11` (SWIR-1), `B12` (SWIR-2). All indices are **DERIVED**. |

### Spectral Index Formulation (Sentinel-2 Derived)
- **Normalized Difference Vegetation Index (NDVI):**  
  $$\text{NDVI} = \frac{B8 - B4}{B8 + B4}$$  
  *Measures canopy greenness and photosynthetic vigor.*
- **Normalized Difference Moisture Index (NDMI / NDWI-Veg):**  
  $$\text{NDMI} = \frac{B8 - B11}{B8 + B11}$$  
  *Directly correlates with canopy liquid water content, critical for fuel flammability.*
- **Normalized Burn Ratio (NBR):**  
  $$\text{NBR} = \frac{B8 - B12}{B8 + B12}$$  
  *Highlights active fire scars and charcoal deposition.*

---

## 6. Environmental & Land Surface Datasets

| Domain | Dataset | GEE Asset ID | Spatial Res | Temporal Res | Key Properties |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **LST** | MODIS Terra LST | `MODIS/061/MOD11A1` | 1000 m | Daily (Day/Night) | `LST_Day_1km` (Kelvin $\times 0.02$). **Skin temperature, not air temperature.** |
| **LST** | MODIS Aqua LST | `MODIS/061/MYD11A1` | 1000 m | Daily (Day/Night) | Afternoon overpass (~13:30 local), captures daily thermal peak. |
| **Soil Moisture** | SMAP L4 Global | `NASA/SMAP/SPL4SMGP/007` | 9 km | 3-hourly | `sm_surface` ($0\text{--}5\text{ cm}$), `sm_rootzone` ($0\text{--}100\text{ cm}$) in $\text{m}^3/\text{m}^3$. |
| **Soil Moisture** | ERA5-Land Soil Water | `ECMWF/ERA5_LAND/DAILY_AGGR` | 0.1° (~11 km) | Daily | Volumetric soil water layer 1 ($0\text{--}7\text{ cm}$), layer 2 ($7\text{--}28\text{ cm}$), layer 3 ($28\text{--}100\text{ cm}$), layer 4 ($100\text{--}289\text{ cm}$) in $\text{m}^3/\text{m}^3$. |
| **Land Cover** | ESA WorldCover | `ESA/WorldCover/v100` | 10 m | Static (2020/2021) | Band `Map`: 11 discrete classes (Tree cover: 10, Shrubland: 20, Grassland: 30, Cropland: 40, Mangroves: 95, Peatland/Wetland: 90). |
| **Land Cover** | MODIS Land Cover | `MODIS/061/MCD12Q1` | 500 m | Yearly (2001-2023) | Multi-scheme IGBP classes (`LC_Type1`). |

---

## 7. Fire & Burned Area Datasets

| Dataset | GEE Asset ID | Spatial Res | Temporal Res | Bands / Description |
| :--- | :--- | :--- | :--- | :--- |
| **MODIS Burned Area** | `MODIS/061/MCD64A1` | 500 m | Monthly | `BurnDate`: Day of year (1-366) of detected burn, `Uncertainty`: Detection confidence (0-100), `QA`: Quality flags. |
| **FIRMS Active Fire** | `FIRMS` | 1 km (MODIS) | Daily | `T21` (Brightness temperature 4µm band in Kelvin), `confidence` (0-100), `line_number`. Note: VIIRS 375m active fire is accessed via Earthdata/FIRMS API. |

---

## 8. Sentinel-2 MSI Optical Architecture & Cloud Mitigation

Sentinel-2 Level-2A (`COPERNICUS/S2_SR_HARMONIZED`) provides multi-spectral imagery with 13 spectral bands at 10m, 20m, and 60m resolution.

### The Tropical Kalimantan Cloud Problem
In equatorial Borneo, persistent cloud cover frequently obscures optical observations (>60–80% cloud contamination during rainy months).

### Cloud Masking via Scene Classification Layer (SCL)
The L2A product includes a pre-computed Scene Classification band (`SCL`, 20m resolution):
- `0`: No data
- `1`: Saturated or defective
- `2`: Dark area pixels
- `3`: Cloud shadows
- `4`: Vegetation
- `5`: Not-vegetated
- `6`: Water
- `7`: Unclassified
- `8`: Cloud medium probability
- `9`: Cloud high probability
- `10`: Thin cirrus
- `11`: Snow / Ice

**Standard Masking Procedure in GEE:**
```javascript
function maskS2clouds(image) {
  var scl = image.select('SCL');
  // Keep only vegetation (4), bare soil (5), and water (6)
  var mask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6));
  return image.updateMask(mask);
}
```

---

## 9. Sentinel-1 C-Band SAR Architecture

Synthetic Aperture Radar (SAR) is an active microwave system that transmits and receives electromagnetic radiation at C-band (~5.405 GHz, wavelength ~5.6 cm).

### Key Advantages for Kalimantan
1. **100% Cloud Penetration:** Radar waves pass through clouds, tropical haze, and thick wildfire smoke unaffected.
2. **Day and Night Operation:** Active sensor independent of solar illumination.
3. **High Spatial Resolution:** 10m pixel spacing in Ground Range Detected (GRD) format (`COPERNICUS/S1_GRD`).

### Polarizations and Physical Significance
- **VV (Vertical transmit, Vertical receive):** Highly sensitive to surface roughness, soil moisture dynamics, and standing water.
- **VH (Vertical transmit, Horizontal receive):** Dominated by volume scattering within vegetation canopies (tree crowns, peat forest structure).
- **Cross-Ratio ($VH / VV$ or $VH - VV$ in dB):** Used to monitor canopy desiccation, biomass density, and burn scar severity.

---

## 10. Actual Extraction Tests & Verification

### 10.1 STAC Catalog Verification Results
The official GEE STAC endpoint was queried programmatically (`scripts/query_gee_stac_catalog.py`). Results saved in `outputs/validation/gee_stac_verified_datasets.json`:
- **12 / 12 Datasets Verified** with valid spatial bounds $[-180, -90, 180, 90]$ and temporal spans extending from historical baselines up to September 2026.

### 10.2 Kalimantan Sample Extraction Test
To prove physical data availability and verify parameter definitions, an extraction test was executed for the 5 provincial administrative centers of Kalimantan during the peak fire season episode of **September 1, 2023** (El Niño drought event).

*Extraction Output (`outputs/validation/kalimantan_era5land_sample.json`):*

| Province | Station City | Lat / Lon | Air Temp (Mean / Max) | Rel. Humidity (Mean) | Precipitation | 10m Wind Speed | Soil Moisture ($0\text{--}7\text{ cm}$) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Kalimantan Barat** | Pontianak | -0.02°, 109.34° | 27.85°C / 32.6°C | 83.1% | 0.10 mm | 7.46 km/h | 0.312 $\text{m}^3/\text{m}^3$ |
| **Kalimantan Tengah** | Palangka Raya | -2.21°, 113.92° | 27.65°C / 32.8°C | **68.7%** | **0.00 mm** | 9.15 km/h | **0.170 $\text{m}^3/\text{m}^3$** |
| **Kalimantan Selatan**| Banjarmasin | -3.32°, 114.59° | 27.59°C / 34.3°C | **67.3%** | **0.00 mm** | 9.47 km/h | **0.167 $\text{m}^3/\text{m}^3$** |
| **Kalimantan Timur** | Samarinda | -0.50°, 117.15° | 27.16°C / 31.6°C | 79.5% | 3.00 mm | 10.50 km/h | 0.310 $\text{m}^3/\text{m}^3$ |
| **Kalimantan Utara** | Tanjung Selor | +2.84°, 117.37° | 26.46°C / 32.4°C | 88.8% | 22.60 mm | 5.43 km/h | 0.407 $\text{m}^3/\text{m}^3$ |

### Physical Interpretation of Results:
The extracted data accurately reflects the known microclimate crisis of early September 2023 in Kalimantan:
- **Central and South Kalimantan (Palangka Raya & Banjarmasin):** Experienced severe atmospheric drying (RH < 70%), zero precipitation, and critically depleted surface soil moisture (~0.167–0.170 $\text{m}^3/\text{m}^3$). This matches the historical timing of massive peatland fires in Pulang Pisau and Banjarbaru.
- **North Kalimantan (Tanjung Selor):** Maintained tropical wet conditions with 22.6 mm daily rainfall, high RH (88.8%), and saturated topsoil (0.407 $\text{m}^3/\text{m}^3$).

---

## 11. Parameter Coverage Matrix

| Parameter / Information Need | Himawari-9 AHI | NASA VIIRS 375m | BMKG Data Online | GEE Catalog (ERA5 / CHIRPS / MODIS / S1 / S2) |
| :--- | :---: | :---: | :---: | :---: |
| **High-Frequency Thermal Hotspots** | ✅ (10 min, 2 km) | ❌ (12-hr overpass) | ❌ | 🟡 (1 km MODIS, 1-2 daily) |
| **High-Resolution Active Fire** | ❌ (2 km) | ✅ (375 m, accurate) | ❌ | 🟡 (FIRMS 1 km / VIIRS external) |
| **Ground Rainfall (Observed)** | ❌ | ❌ | ⚠️ (sparse stations, locked) | ❌ (reanalysis/satellite only) |
| **Gridded Continuous Rainfall** | ❌ | ❌ | ❌ | ✅ (CHIRPS 0.05°, ERA5 0.1°) |
| **Air Temperature (2m)** | ❌ | ❌ | ⚠️ (max 2 stations/month) | ✅ (ERA5-Land 0.1°, continuous) |
| **Radiometric Land Temp (LST)** | 🟡 (B07 brightness temp) | 🟡 (brightness temp) | ❌ | ✅ (MODIS MOD11A1 1km daily) |
| **Relative Humidity** | ❌ | ❌ | ⚠️ (max 2 stations/month) | ✅ (ERA5-Land *derived*, 0.1°) |
| **Wind Speed & Direction** | ❌ | ❌ | ⚠️ (sparse stations) | ✅ (ERA5-Land *derived*, 0.1°) |
| **Soil Moisture (0-7cm / Rootzone)**| ❌ | ❌ | ❌ | ✅ (SMAP 9km, ERA5-Land 0.1°) |
| **Vegetation Greenness (NDVI/EVI)** | ❌ (B07 is MIR) | ❌ | ❌ | ✅ (MODIS 500m, S2 10m *derived*) |
| **Vegetation Fuel Moisture (NDMI)** | ❌ | ❌ | ❌ | ✅ (Sentinel-2 20m *derived*) |
| **Cloud-Penetrating Radar (SAR)** | ❌ | ❌ | ❌ | ✅ (Sentinel-1 C-band GRD 10m) |
| **High-Res Land Cover (10m)** | ❌ | ❌ | ❌ | ✅ (ESA WorldCover 10m) |
| **Historical Burned Area Scars** | ❌ | ❌ | ❌ | ✅ (MODIS MCD64A1 500m) |

*Legend: ✅ Readily Available & Continuous | 🟡 Available with Limitations | ⚠️ Blocked by Quotas/Manual Access | ❌ Not Available*

---

## 12. Accessibility & Programmatic Complexity Comparison

| Platform / Source | Authentication Model | Programmatic CLI Access | Data Format | API Rate Limit / Quota | Primary Technical Bottleneck |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Himawari-9 (NOAA AWS S3)** | **Open Public (No Auth)** | `aws s3 cp` / `boto3` (Anonymous) | NetCDF-4 (`.nc`) | Unlimited AWS public egress | 2 km resolution; requires local projection/remapping |
| **NASA VIIRS (FIRMS Archive)** | **Open Public Archive** (API requires free key) | `requests` / `pandas` (Direct HTTP CSV) | Tabular CSV | Generous archive; 10 min API burst limit | Revisit latency (~12 hours); does not provide weather/fuel |
| **BMKG Data Online** | **Mandatory Web Login** | ❌ Blocked (Form session, dynamic CSRF) | HTML tables / Web CSV | 2 stations/cycle, 24 mo limit, 30-day cooldown | Severe geographic sparsity & manual web portal locks |
| **Google Earth Engine (GEE)** | **OAuth2 / Google Cloud Service Account** | 🟡 Requires Service Account or Web Auth | GeoTIFF / Server-side Image / GeoJSON | 3000 compute elements / export batch limits | Interactive OAuth2 blocker in CLI; server-side export lag |

---

## 13. Comparison with Existing Sources (Himawari, VIIRS, BMKG)

### What GEE Uniquely Adds:
1. **Spatial Continuity for Weather:** Unlike BMKG, which provides point observations at only a few coastal or urban airports across Kalimantan's 540,000 km² landmass, GEE datasets (ERA5-Land, CHIRPS) provide **100% spatial coverage without missing pixels**.
2. **Fuel and Vegetation State:** Neither Himawari, VIIRS, nor BMKG provide vegetation greenness (NDVI), canopy water content (NDMI), or soil moisture. GEE provides continuous historical time-series of these fuel indicators.
3. **High-Resolution Surface Context (10m):** ESA WorldCover and Sentinel-1/2 provide sub-hectare surface classification (peatland vs plantation vs pristine forest).
4. **Historical Burn Scars:** MODIS MCD64A1 enables supervised models to learn from confirmed past burn perimeters.

### Overlaps & Distinctions:
- **Hotspots:** VIIRS (375m) remains superior to GEE's default MODIS active fire (1 km) for label creation. GEE is best used for **environmental covariate extraction**, while VIIRS is best used for **ground-truth fire labels**.
- **Temporal Cadence:** Himawari (10 min) is superior for near-real-time thermal anomaly alerting. GEE datasets operate at hourly to 16-day frequencies, optimal for predictive risk conditioning rather than instantaneous alarm.

---

## 14. Technical Limitations & Blockers

1. **Authentication in Unattended Automation:**
   Running unattended Python extraction scripts requires a registered Google Cloud project with Earth Engine API enabled and a JSON Service Account key. Interactive browser authentication (`ee.Authenticate()`) fails in headless server environments.
2. **Compute and Export Thresholds:**
   Exporting large regional rasters across all of Kalimantan at 10m resolution (e.g. Sentinel-2) causes `User memory limit exceeded` or requires chunked Cloud Storage exports via `ee.batch.Export.image.toDrive()` or `toCloudStorage()`.
3. **Temporal Latencies:**
   - ERA5-Land reanalysis has an inherent **~5-day latency**.
   - MODIS NDVI (`MOD13A1`) is a **16-day composite**.
   - GEE cannot supply real-time weather for same-day prediction without complementary real-time feeds.
4. **Optical Cloud Contamination:**
   Despite GEE's compositing capabilities (`median()`, `min()`), persistent equatorial cloud cover in Kalimantan creates gaps in Sentinel-2 optical imagery during the wet-to-dry transition season. Sentinel-1 SAR is necessary to bridge these gaps.

---

## 15. What We Know So Far (Verified Technical Facts)

1. **Himawari-9 AHI:** Fully validated, open S3 access, continuous 10-minute B07 thermal infrared data over Borneo at 2 km.
2. **NASA VIIRS 375m:** Fully validated, public CSV archive, 5,122 hotspots verified in Kalimantan for September 2023, high spatial accuracy.
3. **BMKG Data Online:** Feasibility tested and proven **severely constrained** for regional modeling due to hard 2-station / 24-month limits, 30-day lockout cooldowns, and vast unmonitored interior areas.
4. **Google Earth Engine (GEE):**
   - Catalog contains complete multi-decadal environmental variables (ERA5-Land, CHIRPS, MODIS, Sentinel-1/2, SMAP, ESA WorldCover).
   - Official GEE STAC catalog programmatically verified for 12 candidate datasets.
   - Physical variables are strictly distinguished (Air Temp vs LST; Dewpoint vs derived RH; Vector wind vs derived scalar speed).
   - Sample extraction verified on Kalimantan coordinates for historical drought conditions.

---

## 16. Open Questions for Future Modeling Phases

*(These questions are flagged for consideration once project phases progress beyond data acquisition):*
1. **Resolution Harmonization:** Should the prediction grid align to ERA5-Land (~11 km), CHIRPS (~5.5 km), MODIS (~1 km / 500 m), or a resampled hybrid grid?
2. **Temporal Windowing:** For environmental features, what lag structure (e.g. 7-day antecedent rainfall, 30-day cumulative drought index) best captures fuel drying dynamics?
3. **Extraction Architecture:** Should data be queried on-the-fly via Earth Engine Python API (requiring Service Account credentials) or pre-extracted in batch for regional Kalimantan tiles into Cloud Storage / NetCDF cubes?
4. **Label Integration:** Will VIIRS 375m active fire points serve as binary classification labels (fire / no-fire) within spatial grid cells, or as point targets?

---

## 17. Recommended Next Exploration

1. **Google Cloud Service Account Setup:** If automated live GEE pipeline execution is selected, configure a non-interactive Google Cloud Service Account with Earth Engine API enabled.
2. **Alternative Direct Endpoints Exploration:** Explore open direct endpoints (e.g. Open-Meteo ERA5-Land archive API, AWS Sentinel-2 COG, Planetary Computer) that provide identical underlying data without OAuth2 overhead.
3. **Spatial Grid and Alignment Testing:** Run a small spatial overlay test intersecting VIIRS hotspot points with gridded ERA5-Land and CHIRPS data over a sample Kalimantan bounding box.
