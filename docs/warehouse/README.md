# AI Wildfire & Land Fire Risk Prediction — Kalimantan (Borneo)
## Multi-Source Geospatial Data Warehouse & Autonomous Response Architecture (2021–2025)

An end-to-end analytical geospatial data warehouse and emergency mitigation platform for predicting and responding to forest and land fires (karhutla) across **Kalimantan, Indonesia**.

This repository integrates 5 full years (2021–2025) of multi-sensor satellite remote sensing, global reanalysis weather, and meteorological forecasts into a canonical **0.02° (~2.2 km)** spatial grid. The warehouse is stored in high-performance **DuckDB** and **Apache Parquet**, verified with zero temporal leakage and zero marine negative samples.

---

## 🚀 Quickstart for Team Members (Handoff Guide)

### 1. Untuk Tim Machine Learning (Model Prediksi Kebakaran 24 Jam)
Dataset siap latih sudah tersedia di dalam view analitik **`vw_training_dataset`** dan Parquet:

* **Total Baris:** **906.556 baris** (Rasio seimbang 1 titik api : 3 background non-api).
* **Fitur Siap Pakai:** 16 fitur baseline resmi terdaftar di [`config/ml_features.py`](config/ml_features.py) (suhu, curah hujan rolling 3d/7d/14d/30d, kelembapan `rh_min_pct`, riwayat titik api masa lalu).
* **Anti-Leakage Split Berbasis Waktu:**
  * `TRAIN` (2021–2023): **552.880 baris**
  * `VAL` (2024): **186.292 baris**
  * `TEST` (2025): **167.384 baris**

#### Cara Membaca Data Pelatihan di Python:
```python
import duckdb
import pandas as pd

# Koneksi ke DuckDB Warehouse (read-only)
con = duckdb.connect("data/warehouse/wildfire.duckdb", read_only=True)

# 1. Load data training (2021-2023)
df_train = con.sql("""
    SELECT * 
    FROM vw_training_dataset 
    WHERE split = 'TRAIN'
""").df()

# 2. Atau baca langsung via Apache Parquet (Pandas / Polars)
df_spine = pd.read_parquet("data/warehouse/parquet/fact_training_spine.parquet")
print(f"Dataset berhasil dimuat: {df_train.shape}")
```

#### Kalibrasi Probabilitas:
Gunakan fungsi `recalibrate_probability(p_hat)` di [`config/ml_features.py`](config/ml_features.py) untuk mengembalikan probabilitas model dari rasio sampel 1:3 ke prevalensi alami dunia nyata (base-rate ~0.046%).

---

### 2. Untuk Tim Agen Respons & Alokasi Pemadam (Modules 3–9)
Warehouse telah menyediakan dimensi spasial operasional penanggulangan karhutla:

* **`dim_responder_hq`**: 12 Posko Daops Manggala Agni (koordinat, kapasitas regu damkar, armada tangki, pompa).
* **`dim_water_sources`**: 17 sumber air strategis (sungai, danau, embung gambut) dengan estimasi kapasitas $\text{m}^3$.
* **`dim_vulnerable_assets`**: Kawasan konservasi (Taman Nasional Tanjung Puting, Sebangau, Betung Kerihun) dan permukiman padat.
* **`fact_incident_records` & `fact_incident_feedback`**: Pencatatan log dispatch dan feedback lapangan.

#### Contoh Query Sumber Air & Posko Terdekat:
```sql
SELECT hq_name, city_regency, total_personnel, latitude, longitude 
FROM dim_responder_hq 
WHERE province = 'Kalimantan Tengah';
```

---

## 🏛️ Arsitektur Data Warehouse

Data warehouse dirancang menggunakan skema konstelasi fakta-dimensi (*Fact-Constellation Schema*) yang dioptimalkan untuk beban kerja analitik spasial-temporal (OLAP):

```text
                                  +-----------------------+
                                  |       dim_grid        |
                                  | (331k cells, 152k land|
                                  +-----------------------+
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
        +-----------------------+ +-----------------------+ +-----------------------+
        |  fact_fire_hotspots   | |   fact_weather_daily  | |   fact_thermal_grid   |
        |  (512,301 hotspots)   | |     (9,130 rows)      | |  (177,995 observations|
        |  NASA VIIRS 375m      | |    ECMWF ERA5-Land    | |     Himawari-8/9      |
        +-----------------------+ +-----------------------+ +-----------------------+
                    │                         │
                    └────────────┬────────────┘
                                 ▼
                    +--------------------------+
                    |    fact_training_spine   |  <── 906,556 samples
                    |  (1:3 Presence-Backgr.)  |  <── 0 Ocean Negative Samples
                    +--------------------------+
                                 │
                                 ▼
                    +--------------------------+
                    |   fact_fire_targets_24h  |  <── Strictly (T, T+24h]
                    +--------------------------+
                                 │
                                 ▼
                    +--------------------------+
                    |   vw_training_dataset    |  <── ML Feature Store View
                    +--------------------------+
```

---

## 🛡️ Jaminan Kualitas Data & Audit Forensik

1. **Zero Temporal Leakage:** Seluruh fitur lingkungan (suhu, curah hujan, angin, riwayat hotspot) strictly ditarik dari hari kemarin ($T - 1\text{ hari}$), sedangkan target kebakaran dihitung murni dalam jendela $(T, T + 24\text{ jam}]$.
2. **Real Land Masking (FIX-02):** Sel grid difilter menggunakan poligon daratan *Natural Earth 10m*. Tidak ada sampel negatif yang jatuh di Laut Jawa atau Selat Karimata (0 marine negative samples), dan anjungan gas lepas pantai berhasil disaring.
3. **Kelengkapan Fitur Cuaca (FIX-01):** Kolom kelembapan minimum `rh_min_pct` dan suhu harian terisi penuh di daratan Kalimantan via interpolasi spasial *Inverse Distance Weighting* (IDW).
4. **Paritas DuckDB & Parquet 100%:** Seluruh 11 tabel inti dan 5 tabel operasional memiliki jumlah baris identik antara database DuckDB dan file Parquet.

---

## 📁 Struktur Direktori Repositori

```text
data-mining-borneo/
├── config/                             # Konfigurasi proyek
│   ├── settings.py                     # Bounding box Kalimantan, konstanta grid 0.02°
│   └── ml_features.py                  # 16 fitur aktif ML & fungsi kalibrasi log-odds
│
├── database/                           # Skema DDL & Analytical Views
│   ├── schema.sql                      # Skema relasional inti DuckDB
│   ├── schema_response_system.sql      # Skema posko damkar, sumber air, & insiden
│   ├── ml_views.sql                    # Definisi vw_training_dataset anti-leakage
│   └── init_db.py                      # Skrip inisialisasi basis data
│
├── etl/                                # Pipeline Produksi ETL
│   ├── run_etl.py                      # Orchestrator pipeline lengkap
│   ├── load_warehouse.py               # Loader data ke DuckDB & Parquet
│   ├── build_training_spine.py         # Generator sampel 1:3 presence-background
│   ├── build_targets.py                # Kalkulator target kebakaran 24 jam ke depan
│   ├── interpolate_weather.py          # IDW spatial interpolation cuaca
│   ├── extract_transform_viirs.py      # Preprocessing 512k hotspot NASA FIRMS
│   ├── extract_transform_era5.py       # Preprocessing reanalisis cuaca harian
│   ├── extract_transform_himawari.py   # NetCDF bounding-box spatial slicer
│   ├── seed_response_dimensions.py     # Ingestion posko Daops, sumber air, & aset
│   └── validate_warehouse.py           # Automated 22-table data quality test
│
├── data/
│   └── warehouse/                      # Penyimpanan data utama
│       ├── wildfire.duckdb             # Database DuckDB analitik (219 MB)
│       └── parquet/                    # Partitioned Parquet tables
│
├── docs/                               # Dokumentasi & Panduan
│   ├── reports/                        # Laporan kelayakan teknis satelit & BMKG
│   ├── archive/                        # Arsip catatan perencanaan awal
│   └── PANDUAN_PRESENTASI_WAREHOUSE.md # Skrip presentasi & jawaban pertanyaan ujian
│
├── src/
│   └── agents/                         # Prototipe Modul Multi-Agent Karhutla
│       ├── trust_agent.py              # Verifikasi anomali termal multi-sensor
│       ├── impact_agent.py             # Penilaian dampak risiko populasi & aset
│       ├── water_agent.py              # Rekomendasi sumber air & rute intake
│       ├── resource_agent.py           # Alokasi unit Daops Manggala Agni
│       ├── planning_agent.py           # Penyusun Incident Action Plan (IAP)
│       ├── execution_agent.py          # Eksekusi dispatch & audit human-in-the-loop
│       └── orchestrator.py             # Pipeline orchestrator
│
├── scripts/                            # Skrip pendukung terorganisir per modul
├── tests/                              # Automated integration tests
│   └── test_response_system.py         # End-to-end response system test
├── requirements.txt                    # Dependensi Python teruji
└── fire-response-ai-system.md          # Spesifikasi sistem respon AI lengkap
```

---

## ⚙️ Instalasi & Menjalankan Uji Coba

### 1. Setup Environment
```powershell
# Buat dan aktifkan virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependensi
pip install -r requirements.txt
```

### 2. Validasi Integritas Data Warehouse
Untuk memeriksa kesehatan 22 tabel, referential integrity, dan ketiadaan kebocoran data:
```powershell
python etl/validate_warehouse.py
```
*(Hasil diharapkan: `OVERALL STATUS: PASS`)*

### 3. Menguji Integrasi Multi-Agent Response System
Untuk menjalankan simulasi respons deteksi api $\to$ rekomendasi air $\to$ alokasi armada damkar:
```powershell
python tests/test_response_system.py
```
*(Hasil diharapkan: `ALL 9 MODULES SUCCESSFULLY VERIFIED AND INTEGRATED!`)*

---

## 📊 Ringkasan Statistik Data Warehouse

| Nama Tabel / View | Sumber Data | Jumlah Baris | Deskripsi Singkat |
| :--- | :--- | :---: | :--- |
| **`fact_fire_hotspots`** | NASA VIIRS 375m | **512.301** | Titik api aktif 5 tahun (2021–2025) di Kalimantan |
| **`fact_training_spine`** | Spatiotemporal Grid | **906.556** | Sampel latih rasio 1:3 dengan pembagian waktu bersih |
| **`fact_fire_targets_24h`**| Forward 24h Window | **906.556** | Label ground truth apakah ada api dalam 24 jam ke depan |
| **`vw_training_dataset`** | Analytical ML View | **906.556** | View siap latih berisi 16 fitur cuaca & riwayat kebakaran |
| **`fact_weather_daily`** | ECMWF ERA5-Land | **9.130** | Cuaca harian (suhu, curah hujan, angin, kelembapan) |
| **`agg_fire_history`** | VIIRS Aggregations | **1.350.470** | Riwayat kebakaran historis per sel grid (3d, 7d, 30d, 1y) |
| **`dim_grid`** | BBOX 0.02° | **331.151** | Sel grid kanonikal (152.837 daratan, 178.314 laut) |
| **`dim_responder_hq`** | KLHK Manggala Agni | **12** | Posko Daops penanggulangan karhutla Kalimantan |
| **`dim_water_sources`** | Peta Hidrologi | **17** | Sumber air pemadaman (sungai besar & embung) |
| **`dim_vulnerable_assets`**| Konservasi / BPS | **17** | Kawasan konservasi & permukiman rentan karhutla |
