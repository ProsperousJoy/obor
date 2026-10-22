# VIIRS Active Fire Data Validation Report

**Project:** AI Wildfire / Land Fire Risk Prediction — Kalimantan (Borneo)  
**Role:** Data Mining / Data Acquisition  
**Date of Validation:** 2026-09-20  
**Sample Analyzed:** NOAA-20 VIIRS 375m Active Fire (Collection 2 NRT)  

---

## Executive Summary

Validasi ini dilakukan untuk mengevaluasi kelayakan data **VIIRS (Visible Infrared Imaging Radiometer Suite) Active Fire** sebagai sumber data deteksi titik panas (hotspot) historis yang nantinya diintegrasikan dengan data satelit geostasioner **Himawari-9 AHI B07** serta data cuaca/lingkungan lainnya (BMKG, curah hujan, vegetasi, tanah gambut) untuk memprediksi **risiko kebakaran masa depan** di Kalimantan.

Sample nyata 24 jam (7.764 rekaman Asia Tenggara, 5.122 rekaman di Kalimantan) berhasil diunduh langsung dari repositori resmi **NASA FIRMS (Fire Information for Resource Management System)**, diuji skema datanya, divalidasi kualitas dan integritas fisiknya, dipetakan secara geospasial, serta diuji coba join spasial-temporal awal (*prototype join*) dengan citra Himawari-9 B07.

---

## 1. Data Source

* **Provider:** NASA LANCE (Land, Atmosphere Near real-time Capability for EOS) / FIRMS (Fire Information for Resource Management System).
* **Affiliated Agency:** NASA EOSDIS (Earth Observing System Data and Information System) bekerjasama dengan NOAA.
* **Official URL Portal:** [https://firms.modaps.eosdis.nasa.gov/](https://firms.modaps.eosdis.nasa.gov/)
* **License & Access Policy:** 
  * Open Data Policy: Gratis dan terbuka penuh untuk penelitian akademis, operasional, maupun komersial.
  * Atribusi resmi: *"We acknowledge the use of data and imagery from LANCE FIRMS operated by NASA's ESDIS."*
  * Penggunaan data NRT (Near Real-Time) disarankan dengan pemahaman bahwa data diproses secara otomatis sebelum melalui siklus kontrol kualitas sains akhir (*Standard Processing / Science Quality*).

---

## 2. Product Identification

* **Sensor:** VIIRS (Visible Infrared Imaging Radiometer Suite).
* **Satellites Carrying VIIRS:**
  1. **NOAA-20 (JPSS-1):** Diluncurkan Nov 2017, orbit polar sun-synchronous (~13:30 LT ascending node). Produk: `VJ114IMGTDL_NRT` / `VIIRS_NOAA20_NRT`.
  2. **Suomi NPP (S-NPP):** Diluncurkan Okt 2011, produk: `VNP14IMGTDL_NRT` (**Catatan:** pengiriman data S-NPP dijadwalkan dihentikan per 1 November 2026 oleh NASA).
  3. **NOAA-21 (JPSS-2):** Diluncurkan Nov 2022, produk: `VIIRS_NOAA21_NRT`.
* **Product Collection:** Collection 2 (C2).
* **Spatial Resolution:** **~375 m** (menggunakan saluran resolusi tinggi *Imagery Band* I-4 dan I-5).
  * Di titik nadir: 375 m × 375 m.
  * Di tepi sapuan (*swath edge*): melebar hingga ~750–800 m akibat distorsi optik off-nadir (diperhitungkan via kolom `scan` dan `track`).
* **Temporal Resolution:** Satelit orbit polar (LEO), melintas di atas Kalimantan **1–2 kali per 24 jam per satelit** (1 kali overpass siang hari ~12:30–13:30 WIB / 05:30–06:30 UTC, dan 1 kali overpass malam hari ~00:30–01:30 WIB / 17:30–18:30 UTC).

---

## 3. Access Method

Tersedia 3 jalur akses resmi yang telah diverifikasi:

1. **Direct Public NRT Feeds (HTTP open access — tanpa token):**
   * Feed teks CSV 24 jam / 48 jam / 7 hari per kawasan:
     `https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_SouthEast_Asia_24h.csv`
     `https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_SouthEast_Asia_7d.csv`
   * Sangat andal untuk pengambilan data operasional harian atau rolling window tanpa registrasi token.
2. **FIRMS REST API (Area CSV endpoint — memerlukan free `MAP_KEY`):**
   * Endpoint format:
     `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_NOAA20_NRT/{west,south,east,north}/{dayrange}/{date}`
   * Limitasi: Maksimal rentang 1–5 hari per request, kuota 5.000 transaksi per 10 menit.
3. **NASA LANCE / Earthdata Archive (Bulk Historical Download):**
   * Arsip historis multi-tahun di `https://nrt3.modaps.eosdis.nasa.gov/archive/FIRMS/` membutuhkan akun NASA Earthdata Login gratis (via HTTP Basic Auth / `.netrc`).

---

## 4. Sample Dataset Description

* **File Mentah (Raw):** `data/viirs/raw/J1_VIIRS_C2_SouthEast_Asia_24h.csv` (1,2 MB).
* **Total Baris Raw (Asia Tenggara):** 7.764 rekaman.
* **Wilayah Target:** Bounding Box Kalimantan (`lon: [108.0, 119.0]`, `lat: [-5.0, 7.0]`).
* **Rekaman Kalimantan Terdeteksi:** **5.122 titik hotspot**.
* **File Olahan Bersih:** `data/viirs/processed/viirs_noaa20_kalimantan_sample.csv`.
* **Rentang Tanggal Akuisisi:** `2026-09-19`.
* **Rentang Jam Akuisisi (UTC):** `05:46` s.d. `18:28` UTC (terdiri dari 2 siklus orbit: siang ~05:46 UTC / 12:46 WIB dan malam ~16:45–18:28 UTC / 23:45–01:28 WIB).

---

## 5. Schema / Field Verification

Seluruh 13 field standar NASA FIRMS VIIRS 375m teridentifikasi dan tervalidasi dengan tepat:

| No | Nama Kolom Asli | Tipe Data | Satuan | Deskripsi & Interpretasi | Tingkat Kepentingan |
|---|---|---|---|---|---|
| 1 | `latitude` | `float64` | degree | Garis lintang titik pusat (centroid) piksel deteksi api | Kritis (Spatial Key) |
| 2 | `longitude` | `float64` | degree | Garis bujur titik pusat (centroid) piksel deteksi api | Kritis (Spatial Key) |
| 3 | `bright_ti4` | `float64` | Kelvin | Suhu kecerahan (BT) kanal I-4 (~3.75–4.05 µm SWIR/MWIR) | Kritis (Thermal Fire) |
| 4 | `scan` | `float64` | km | Resolusi spasial piksel searah pemindaian optik (*along-scan*) | Kualitas Spasial |
| 5 | `track` | `float64` | km | Resolusi spasial piksel searah lintasan satelit (*along-track*) | Kualitas Spasial |
| 6 | `acq_date` | `string` | YYYY-MM-DD | Tanggal pengamatan instrumen (UTC) | Kritis (Temporal Key) |
| 7 | `acq_time` | `int/string`| HHMM (UTC)| Waktu pengamatan instrumen (UTC) | Kritis (Temporal Key) |
| 8 | `satellite` | `string` | kategori | Kode satelit (`N20` = NOAA-20 / JPSS-1) | Provenance / Tracking |
| 9 | `confidence` | `string` | kategori | Tingkat keyakinan deteksi algoritma: `low`, `nominal`, `high` | Kualitas Label |
| 10 | `version` | `string` | string | Versi pemrosesan (misal `2.0NRT`) | Meta / Versioning |
| 11 | `bright_ti5` | `float64` | Kelvin | Suhu kecerahan (BT) kanal I-5 (~10.5–12.4 µm TIR background) | Konteks Termal |
| 12 | `frp` | `float64` | Megawatt | *Fire Radiative Power* (estimasi daya pancaran panas api) | Kritis (Intensitas Api) |
| 13 | `daynight` | `string` | flag | Status iluminasi matahari saat melintas (`D` = Siang, `N` = Malam) | Stratifikasi Koreksi |

> **Catatan Tambahan:** Pada pipeline pra-pemrosesan ditambahkan kolom turunan `datetime_utc` (format ISO-8601 `YYYY-MM-DD HH:MM:SS+00:00`) tanpa menghapus `raw_acq_date` dan `raw_acq_time`.

---

## 6. Data Quality & Statistical Sanity

Hasil pengujian integritas numerik dan statistik terhadap 7.764 rekaman:

* **Missing Values:** **0** pada seluruh kolom.
* **Duplikasi Baris:** **0** duplikat identik.
* **Pemeriksaan Batas Geografis:**
  * Latitude: `[-11.99°, 30.45°]` → Semua berada dalam rentang valid `[-90°, 90°]`.
  * Longitude: `[88.13°, 153.05°]` → Semua berada dalam rentang valid `[-180°, 180°]` (tidak ada anomali lon-360).
* **Pemeriksaan Batas Fisik Termal:**
  * `bright_ti4` (I-4): Min **286.70 K**, Median **331.89 K**, Mean **327.47 K**, Max **367.00 K**.
    *(Nilai maksimum tepat 367.00 K mencerminkan batas saturasi sensor kanal I-4 VIIRS, sesuai desain instrumen).*
  * `bright_ti5` (I-5): Min **252.85 K**, Median **291.93 K**, Mean **293.13 K**, Max **368.92 K**.
  * `frp`: Min **0.00 MW**, Median **4.00 MW**, P90 **17.12 MW**, Max **687.80 MW**. Rata-rata 8.50 MW. Nilai non-negatif dan konsisten dengan sebaran kebakaran vegetasi tropis.
  * `scan` & `track`: Berkisar antara 0.32 km s.d. 0.79 km (rata-rata ~0.45 km), mengonfirmasi resolusi kelas 375m.

---

## 7. Geolocation Validation

* **Validitas Sistem Koordinat:** Menggunakan koordinat geodetik WGS84 (EPSG:4326), desimal derajat.
* **Bounding Box Kalimantan:**
  * Dari 7.764 titik deteksi Asia Tenggara, **5.122 titik (66,0%)** jatuh tepat di dalam kotak bounding box studi Kalimantan (`lon: 108.0–119.0`, `lat: -5.0–7.0`).
* **Verifikasi Landmark & Kota:**
  Titik-titik hotspot terdistribusi di sekitar wilayah pedalaman dan perkebunan/hutan sekunder di sekitar:
  * Koridor barat Kalimantan (antara Pontianak dan Ketapang)
  * Koridor tengah Kalimantan (utara Palangkaraya hingga batas Kalimantan Timur)
  * Koridor timur Kalimantan (barat Samarinda / Kutai Kartanegara)
* Tidak ditemukan koordinat fiktif, koordinat di luar atmosfer, atau nilai latitude/longitude terbalik.
* Peta visualisasi `outputs/validation/viirs_kalimantan_map.png` mengonfirmasi bahwa sebaran titik secara visual mengikuti kontur daratan pulau Kalimantan.

---

## 8. Timestamp Validation

* **Format Asli:**
  * `acq_date`: `2026-09-19` (String ISO).
  * `acq_time`: `0546`, `0548`, `1645`, `1828` (Integer/String 4 digit waktu 24 jam).
* **Timezone:** **UTC murni** (dikonfirmasi dari dokumentasi NASA LANCE).
* **Konversi ke Waktu Lokal (WIB / UTC+7):**
  * Siang: `05:46 UTC` = `12:46 WIB` (kondisi siang terik, puncak bahaya api).
  * Malam: `16:48 UTC` = `23:48 WIB` dan `18:28 UTC` = `01:28 WIB`.
* **Integritas Waktu:** Seluruh baris waktu valid, tidak ada jam > 2400 atau menit > 59. Kolom kanonikal `datetime_utc` berhasil di-generate secara deterministik.

---

## 9. Fire Detection Semantics (Bukan "Ground Truth Absolute")

> [!WARNING]
> **PENTING UNTUK PEMODELAN AI:** Titik hotspot VIIRS **TIDAK BISA** diperlakukan sebagai *absolute ground truth* dari seluruh kebakaran yang terjadi. Data ini merepresentasikan **anomali termal sub-piksel terdeteksi**.

### Prinsip Deteksi Fisika:
Algoritma VIIRS mendeteksi kontras radiasi antara kanal inframerah gelombang menengah (I-4 pada ~3.9 µm) dan inframerah termal gelombang panjang (I-5 pada ~11.0 µm).
* Hukum Perpindahan Wien dan Hukum Planck menyatakan bahwa objek bertemperatur tinggi (api ~600–1200 K) memancarkan energi berlipat ganda pada panjang gelombang 3.9 µm dibanding 11 µm.
* Pada sample Kalimantan, perbedaan suhu kecerahan:
  $$\Delta BT = BT_{I4} - BT_{I5}$$
  memiliki **rata-rata +34.02 K** dan **maksimum +99.80 K**. Nilai positif yang tinggi ini secara fisik membuktikan adanya emisi anomali termal yang jauh lebih panas daripada suhu latar belakang tanah sekitarnya.

### Keterbatasan Deteksi (Potensi Bias):
1. **Missed Detections (False Negatives):**
   * **Awan Tebal:** Satelit optik/termal tidak dapat menembus tutupan awan kumulonimbus/hujan. Jika kebakaran terjadi di bawah awan lebat, VIIRS tidak akan mencatat titik tersebut.
   * **Understory / Peat Fire (Kebakaran Bawah Tanah/Gambut):** Kebakaran lahan gambut yang membara di bawah lapisan tanah tanpa nyala terbuka (*smoldering peat fires*) menghasilkan tanda termal permukaan yang redup sehingga berpotensi lolos dari deteksi.
   * **Kebakaran Singkat di Luar Waktu Overpass:** Api yang menyala pada pagi hari (09:00 WIB) dan padam sebelum waktu lintasan satelit (12:46 WIB) tidak akan terekam.
2. **False Positives:**
   * Pantulan sinar matahari (*solar reflection/glint*) dari permukaan air, atap seng industri, atau tanah tandus terbuka saat siang hari.
   * Cerobong industri / kilang minyak (*gas flaring*) di pesisir Kalimantan Timur.

---

## 10. Confidence & FRP Analysis

### Analisis Kategori Confidence:
* **`nominal` (87.6%):** Tingkat deteksi standar yang andal, diperoleh pada kondisi atmosfer cerah bebas dari glint matahari yang signifikan.
* **`low` (10.3%):** Deteksi pada kondisi marginal (misalnya pantulan sudut matahari rendah, tepi awan, atau sinyal termal sangat lemah). Memiliki risiko false positive lebih tinggi.
* **`high` (2.1%):** Deteksi dengan intensitas anomali termal sangat ekstrem, di mana saluran I-4 sering mengalami saturasi ($BT_{I4} \ge 367.0\text{ K}$). Nilai rata-rata FRP pada kelas ini mencapai **52.64 MW**. Hampir 100% dipastikan kebakaran nyata berskala besar.

### Analisis Fire Radiative Power (FRP):
* Satuan: Megawatt (MW).
* Mengukur daya pembebasan energi panas radiatif secara langsung dari api aktif.
* Sebaran di Kalimantan:
  * Median: 4.22 MW
  * P90: 17.12 MW
  * Maksimum: 687.80 MW (kebakaran biomassa masif)
* **Pemanfaatan untuk ML:** FRP dapat digunakan untuk membedakan antara titik api kecil/insidental dengan kebakaran besar tak terkendali yang membutuhkan respon darurat tinggi.

---

## 11. Spatial Join Readiness with Himawari-9

| Parameter | VIIRS 375m | Himawari-9 AHI B07 | Implikasi Integrasi Spasial |
|---|---|---|---|
| **Platform** | LEO (Polar Sun-synchronous) | GEO (Geostasioner ~140.7°E) | Geometri pengamatan berbeda |
| **Grid / Format** | Point Vector (Centroid lon/lat) | 2D Raster Grid (GEOS projection) | Perlu pemetaan titik ke piksel |
| **Resolusi Spasial** | ~375 m (0.375 km) | ~2.000 m (2.0 km) | **1 piksel Himawari memuat ~25–30 piksel VIIRS** |

### Hasil Uji Coba Spatial Join Prototype:
* Menggunakan `scipy.spatial.cKDTree` untuk memetakan koordinat titik VIIRS ke pusat piksel grid Himawari-9 B07 terdekat:
  * Pada area Kalimantan yang ter-cover oleh segmen S0510 (Kalimantan Utara, sebagian Kalimantan Barat/Timur), jarak spasial antara titik VIIRS ke pusat piksel Himawari adalah **0.7 s.d. 1.1 km** (< 1 ukuran piksel Himawari 2 km).
  * Pada Kalimantan bagian selatan, jarak melonjak karena segmen S0510 berhenti di sekitar ekuator. Ini mengonfirmasi ulang bahwa **segmen S0610 wajib diakuisisi untuk menutupi seluruh Kalimantan**.
* **Rekomendasi Strategi Spasial:**
  * **Pendekatan Grid Canonical (Direkomendasikan):** Jadikan grid Himawari 2 km sebagai grid referensi standar. Agregasikan titik-titik VIIRS yang jatuh ke dalam setiap sel grid 2 km menjadi metrik agregat:
    - `count_hotspots` (jumlah titik api per grid cell)
    - `max_frp` (intensitas panas tertinggi per grid cell)
    - `sum_frp` (total pelepasan energi panas per grid cell)
    - `has_fire_binary` (0 atau 1)

---

## 12. Temporal Join Readiness with Himawari-9

| Parameter | VIIRS | Himawari-9 | Implikasi Integrasi Temporal |
|---|---|---|---|
| **Frekuensi Observasi** | 1–2 kali per 24 jam | Setiap 10 menit (kontinu) | Frekuensi Himawari ~144× lebih rapat |
| **Waktu Melintas (Overpass)** | Siang (~05:45 UTC) & Malam (~17:00 UTC) | 00:00, 00:10, 00:20, ... (setiap 10m) | Harus matching pada slot overpass |

### Hasil Uji Coba Temporal Matching:
* Pada sample yang diuji, observasi Himawari kita adalah `2026-09-20 00:00 UTC`.
* Overpass VIIRS 24h terjadi pada `2026-09-19 05:46 UTC` dan `2026-09-19 18:28 UTC`.
* Selisih waktu delta berkisar antara 5.5 hingga 18.2 jam.
* **Rekomendasi Aturan Jendela Waktu (Time Windowing):**
  * Ketika Himawari digunakan untuk mengamati kondisi lingkungan pada saat VIIRS melintas, gunakan slot waktu Himawari dengan jendela toleransi **$\pm 10\text{ menit}$ s.d. $\pm 30\text{ menit}$** dari `acq_time` VIIRS.

---

## 13. Limitations Summary

1. **Resolusi Temporal Terbatas (Polar Gap):** VIIRS hanya memberikan potret 2 kali sehari. Perubahan kondisi kebakaran antara siang dan malam tidak terekam oleh VIIRS (tetapi dapat dijembatani oleh Himawari).
2. **Ketergantungan pada Cuaca (Cloud Obscuration):** Area dengan curah hujan tinggi atau kabut asap pekat tidak dapat diamati secara optik.
3. **Sunset Suomi-NPP (Nov 2026):** Penggunaan sensor harus diprioritaskan pada **NOAA-20** dan **NOAA-21** untuk menjamin keberlanjutan pipeline.
4. **Ukuran Piksel Melebar di Tepi Swath:** Nilai `scan` dan `track` naik dari 0.37 km di nadir menjadi 0.79 km di tepi orbit, sedikit menurunkan ketelitian lokalisasi api di pinggiran lintasan.

---

## 14. Potential Data Leakage Risks (PENTING untuk Model Prediksi Risiko)

Karena tujuan project adalah memprediksi **risiko terjadinya kebakaran di masa depan** ($T + \Delta t$), bukan sekadar mendeteksi kebakaran yang sedang menyala ($T$), maka pembagian peran VIIRS harus diatur secara ketat:

> [!CAUTION]
> **Risiko Kebocoran Data (Data Leakage):**
> Jika model ditugaskan memprediksi kebakaran pada jam $T$, maka deteksi aktif VIIRS pada jam $T$ **HARUS MENJADI LABEL (TARGET $y$)**, dan **TIDAK BOLEH** dimasukkan ke dalam feature input $X$.

### Skenario Konseptual Integrasi yang Benar:
* **Feature Window (Masa Lalu / Input $X$):**
  * Data Himawari B07 pada rentang waktu $[T - 24\text{h}, T]$.
  * Riwayat titik api VIIRS masa lalu (misal: agregat hotspot 7 hari sebelumnya sebagai proksi akumulasi bahan bakar terbakar / aktivitas manusia).
  * Data cuaca BMKG pada rentang $[T - 24\text{h}, T]$.
* **Target / Label Window (Masa Depan / Output $y$):**
  * Keberadaan titik api aktif VIIRS pada rentang waktu $[T, T + 6\text{h}]$ atau $[T, T + 24\text{h}]$ dengan filter `confidence in ['nominal', 'high']`.

---

## 15. Recommendation for Next Step

1. **Jadikan VIIRS NOAA-20 375m sebagai komponen Target Label & Historical Feature:**
   * Skema telah tervalidasi 100%, koordinat akurat, dan nilai FRP/dBT memiliki basis fisika yang kokoh.
2. **Standardisasi Format Penyimpanan Data Mining:**
   * Simpan data VIIRS regional Kalimantan dalam format **Parquet** (terkompresi Snappy) per bulan/tahun dengan indeks temporal UTC, agar query spasio-temporal berjalan cepat.
3. **Pengadaan Himawari Segmen S0610:**
   * Melengkapi segmen S0610 agar join spasial dengan VIIRS di Kalimantan Tengah dan Kalimantan Selatan dapat dilakukan tanpa celah *out-of-bound*.
4. **Siapkan Modul Aggregator Spasial:**
   * Bangun fungsi utilitas untuk melakukan spatial binning (mengelompokkan titik VIIRS 375m ke dalam grid Himawari 2 km).

---

## Visualisasi Tersedia

Hasil visualisasi validasi telah disimpan di `outputs/validation/`:
1. `outputs/validation/viirs_kalimantan_map.png` — Peta sebaran titik api VIIRS di Kalimantan dengan garis pantai dan kota acuan.
2. `outputs/validation/viirs_distributions.png` — Histogram 4 panel (Brightness Temp I-4, FRP log-scale, distribusi confidence, dan proporsi Day/Night).
3. `outputs/validation/viirs_himawari_overlay.png` — Visualisasi overlay titik api VIIRS di atas grid termal Himawari-9 B07.

---
*Laporan dibuat secara otomatis dan telah diverifikasi oleh tim Data Acquisition.*
