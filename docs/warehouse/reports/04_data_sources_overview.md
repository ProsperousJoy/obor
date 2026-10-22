# Data Sources Exploration Overview — Wildfire Risk Prediction (Kalimantan)

**Project:** AI Wildfire / Land Fire Risk Prediction — Kalimantan (Borneo)  
**Document Type:** Internal Technical Notes / Feasibility Exploration Overview  
**Role:** Data Mining / Data Acquisition  
**Date:** 2026-09-20  
**Project Phase:** Exploratory Data Acquisition / Feasibility Testing  

---

## 1. Context & Scope

Catatan teknis ini menyajikan ringkasan komparatif dari hasil eksplorasi teknis awal terhadap **tiga kandidat sumber data**:
1. **Himawari-9 AHI (Advanced Himawari Imager)**
2. **NASA VIIRS 375m Active Fire (NOAA-20 Collection 2 NRT)**
3. **BMKG Weather & Climate Data (BMKG Data Online & BMKG Open Data API)**

> [!IMPORTANT]
> **STATUS FASE PROYEK:**
> Dokumen ini **BUKAN** merupakan penetapan keputusan final dan **TIDAK** memilih "sumber data pemenang". Pada tahap ini:
> * Belum ada penentuan fitur final (*final features*).
> * Belum ada penentuan label/target akhir (*final labels/targets*).
> * Belum ada penentuan horizon prediksi masa depan (*prediction horizon*).
> * Belum ada penetapan grid spasial kanonikal (*canonical spatial grid*).
> * Belum ada penetapan jendela temporal (*temporal window*).
> * Belum ada pemilihan model machine learning atau arsitektur AI.
>
> Tujuan dokumen ini murni menjawab: **"Dari tiga sumber data yang sudah dieksplorasi secara praktis, apa yang terbukti tersedia, apa yang dapat diakses, parameter apa saja yang ada, bagaimana cakupannya, serta apa kendala dan limitasi teknisnya?"**

---

## 2. Detailed Findings by Candidate Data Source

---

### Source 1: Himawari-9 AHI (Advanced Himawari Imager)

#### Accessibility
* **Platform / Sumber:** NOAA Public AWS S3 Bucket (`s3://noaa-himawari9/`).
* **Sifat Akses:** **100% Public Open Access** via anonymous access (`botocore.UNSIGNED`).
* **Persyaratan Akun:** **Tanpa API key, tanpa registrasi akun, tanpa kredensial AWS**.
* **Hasil Pengujian Unduh & Baca:** **BERHASIL**. Data mentah terkompresi Bzip2 (`.DAT.bz2`) berhasil diunduh, didekompresi, dan dibaca secara programatis.
* **Pustaka Pemroses:** Python `satpy` (pembaca format `ahi_hsd`), `pyresample`, `xarray`, `netCDF4`.
* **Format Data Hasil Baca:** `xarray.DataArray` yang berhasil diekspor ke format NetCDF standar CF-compliant (`outputs/himawari_b07_s0510_borneo.nc`).

#### Available Data / Parameters
* **Kanal yang Diuji Secara Nyata:** **Band B07** (Inframerah Gelombang Menengah / *Shortwave/Midwave Infrared*).
* **Panjang Gelombang Pusat:** $\approx 3.9\text{ }\mu\text{m}$.
* **Besaran / Produk Fisik:** *Brightness Temperature* (Suhu Kecerahan).
* **Satuan Fisik:** **Kelvin (K)**.
* **Resolusi Spasial Nadir:** $\approx 2.0\text{ km}$.
* **Rentang Nilai Teramati pada Sampel:** $196.6\text{ K}$ s.d. $312.4\text{ K}$ (rata-rata $287.9\text{ K}$, konsisten secara fisik dengan suhu atmosfer/permukaan tropis).

#### Spatial Coverage
* **Wilayah Sampel yang Diproses:** Segmen **S0510** (*Full Disk Segment 5 dari 10*).
* **Validasi Geolokasi:** Diverifikasi secara independen menggunakan parameter proyeksi geostasioner (`+proj=geos +lon_0=140.7 +h=35785863`) terhadap 5 kota acuan Kalimantan (Pontianak, Palangka Raya, Banjarmasin, Samarinda, Balikpapan) dengan kesalahan posisi $< 0.01^\circ$ ($< 1\text{ km}$).
* **Keterbatasan Spasial Segmen S0510 (Open Issue):**  
  Segmen S0510 hanya mencakup pita lintang ekuator bagian utara ($\approx 0^\circ \text{ s.d. } 12^\circ\text{N}$). Wilayah Kalimantan bagian selatan (Kalimantan Selatan dan sebagian Kalimantan Tengah pada lintang $-5^\circ \text{ s.d. } 0^\circ\text{N}$) **belum tercakup oleh segmen S0510**.  
  *Kebutuhan teknis yang belum ditutup:* Pengambilan segmen **S0610** diperlukan untuk melengkapi cakupan Kalimantan bagian selatan secara utuh.
* **Masking Wilayah:** Menggunakan *bounding box rectangular* ($\text{Lon } [108^\circ, 119^\circ\text{E}]$, $\text{Lat } [-5^\circ, 7^\circ\text{N}]$), menghasilkan $\approx 43\%$ piksel laut yang nantinya perlu dimasking menggunakan poligon pulau.

#### Temporal Characteristics
* **Frekuensi Pengamatan:** Instrumen AHI melakukan pemindaian *Full Disk* setiap **10 menit** secara kontinu sepanjang hari (24 jam / 144 observasi per hari).
* **Sampel Teruji:** Observasi nominal `2026-09-20 00:00:00 UTC` (waktu observasi aktual sensor untuk S0510: `00:04:04 UTC`).
* **Ketersediaan Historis:** Tersedia secara penuh sejak operasional Himawari-8/9 (2015 s.d. sekarang) di arsip AWS S3.

#### Technical Feasibility Status
* **Status:** **FEASIBLE**
* **Alasan:** Data publik gratis, dapat diunduh tanpa autentikasi, pembacaan pustaka Python stabil, geolokasi presisi terbukti, dan resolusi temporal sangat tinggi (10 menit).

---

### Source 2: NASA VIIRS 375m Active Fire

#### Accessibility
* **Platform / Penyedia:** NASA LANCE (Land, Atmosphere Near real-time Capability for EOS) / FIRMS (Fire Information for Resource Management System).
* **Produk yang Digunakan:** VIIRS 375m I-Band Active Fire (*Collection 2 NRT*, `VJ114IMGTDL_NRT`).
* **Platform Satelit:** **NOAA-20 (JPSS-1)**.
* **Sifat Akses:** **Public Open Access**. Feed CSV regional Asia Tenggara 24h/7d dapat diunduh langsung tanpa API key; REST API area query memerlukan `MAP_KEY` gratis.
* **Hasil Pengujian Unduh & Baca:** **BERHASIL**. Berkas mentah 24 jam (`J1_VIIRS_C2_SouthEast_Asia_24h.csv`, 7.764 baris) berhasil diunduh dan diproses.
* **Format Data:** Teks tabular CSV (*Comma-Separated Values*), UTF-8. Programmatic access sangat mudah via HTTP GET / `curl` / `pandas`.

#### Available Parameters
Semua 13 parameter standar FIRMS berhasil diverifikasi pada sampel nyata:
1. **Komponen Geolokasi:**
   * `latitude`: Garis lintang titik pusat piksel deteksi api (WGS84, derajat).
   * `longitude`: Garis bujur titik pusat piksel deteksi api (WGS84, derajat).
   * `scan`: Resolusi spasial piksel searah pemindaian optik / *along-scan* ($0.32\text{ s.d. } 0.79\text{ km}$).
   * `track`: Resolusi spasial piksel searah lintasan orbit / *along-track* ($0.36\text{ s.d. } 0.78\text{ km}$).
2. **Komponen Waktu (Timestamp):**
   * `acq_date`: Tanggal akuisisi UTC (`YYYY-MM-DD`).
   * `acq_time`: Waktu akuisisi UTC dalam format `HHMM`.
3. **Pengukuran Termal Spektral:**
   * `bright_ti4`: Suhu kecerahan kanal I-4 (~3.75–4.05 $\mu\text{m}$) dalam Kelvin. Nilai sampel: $286.7\text{ K}$ s.d. $367.0\text{ K}$ (saturasi sensor pada $367.0\text{ K}$).
   * `bright_ti5`: Suhu kecerahan kanal latar belakang I-5 (~10.5–12.4 $\mu\text{m}$) dalam Kelvin. Nilai sampel: $252.8\text{ K}$ s.d. $368.9\text{ K}$.
4. **Indikator Kualitas & Keyakinan Deteksi:**
   * `confidence`: Tingkat keyakinan algoritma deteksi (`low`: 10.3%, `nominal`: 87.6%, `high`: 2.1%).
   * `version`: Versi pemrosesan data (misal `2.0NRT`).
   * `daynight`: Indikator iluminasi matahari (`D` = Siang 51.5%, `N` = Malam 48.5%).
5. **Pengukuran Karakteristik Kebakaran:**
   * `frp`: *Fire Radiative Power* (daya pelepasan panas radiatif api) dalam **Megawatt (MW)**. Nilai sampel di Kalimantan: Min $0.0\text{ MW}$, Median $4.22\text{ MW}$, P90 $17.12\text{ MW}$, Max $687.80\text{ MW}$.

#### Spatial Coverage
* **Cakupan Sampel:** Seluruh kawasan Asia Tenggara dengan subset fokus Kalimantan.
* **Jumlah Deteksi di Kalimantan:** **5.122 titik hotspot** terfilter dalam bounding box studi Kalimantan pada periode 24 jam yang diuji.
* **Resolusi Spasial:** Kelas **$\approx 375\text{ m}$** di nadir (melebar hingga ~750–800 m di tepi swath).
* **Validasi Geolokasi:** Nilai koordinat berada strictly dalam batas geodetik valid WGS84 dan sebarannya konsisten mengikuti morfologi daratan Kalimantan.

#### Temporal Characteristics
* **Sifat Orbit:** Satelit orbit kutub (*Low Earth Orbit / Polar Sun-Synchronous*).
* **Frekuensi Observasi:** **1 s.d. 2 kali per 24 jam per satelit**.
* **Waktu Melintas (*Overpass*) di Kalimantan Terverifikasi:**
  * Lintas Siang (Ascending): $\approx 05:46\text{ UTC}$ ($\approx 12:46\text{ WIB}$).
  * Lintas Malam (Descending): $\approx 16:45\text{ s.d. } 18:28\text{ UTC}$ ($\approx 23:45\text{ s.d. } 01:28\text{ WIB}$).
* **Ketersediaan Historis:** Tersedia arsip lengkap sejak peluncuran Suomi-NPP (2012) dan NOAA-20 (2018 s.d. sekarang). *(Catatan: Data Suomi-NPP dijadwalkan dihentikan per Nov 2026, NOAA-20/21 menjadi standar berkelanjutan)*.

#### Fire Detection Semantics & Limitations
* **Bukan "Absolute Ground Truth":** Deteksi aktif VIIRS merepresentasikan **anomali termal sub-piksel**, bukan verifikasi lapangan mutlak atas semua kebakaran.
* **Potensi False Negatives (Missed Fires):** Kebakaran di bawah tutupan awan tebal (*cloud obscuration*), kebakaran gambut bawah tanah (*smoldering peat fires* tanpa nyala api terbuka), atau kebakaran singkat yang padam di luar jendela lintasan satelit tidak akan terdeteksi.
* **Arti Field `confidence`:** Nilai kategorikal (`low`, `nominal`, `high`) menunjukkan tingkat keyakinan algoritma kontekstual terhadap kontras termal terhadap latar belakang dan ketiadaan pantulan matahari/awan, **bukan nilai probabilitas matematis (0–100%)** bahwa api pasti ada di lapangan.

#### Spatial Join Prototype
* **Pengujian Integrasi Awal:** Berhasil dipetakan ke grid Himawari B07 2 km menggunakan algoritma pencarian tetangga terdekat `cKDTree`. Pada Kalimantan bagian utara (wilayah segmen S0510), jarak titik VIIRS ke pusat piksel Himawari terdekat berkisar $0.7\text{ s.d. } 1.1\text{ km}$ ($< 1$ piksel Himawari).
* *Catatan Penting:* Ini adalah demonstrasi kelayakan teknis (*prototype*), **bukan pipeline integrasi final**.

#### Potential Data Leakage Risk (Open Design Issue)
* Ditemukan risiko kebocoran data (*data leakage*) jika peran VIIRS tidak dipisahkan secara ketat secara temporal:
  * Jika target prediksi adalah risiko kebakaran pada waktu $T + \Delta t$, maka observasi VIIRS pada waktu $T + \Delta t$ **hanya boleh dijadikan label target**, dan **tidak boleh** masuk ke dalam feature input.
  * Pemanfaatan VIIRS sebagai fitur hanya sah jika menggunakan riwayat agregat masa lalu ($T - \Delta t$, misal densitas kebakaran 7 hari terakhir). Masalah ini dicatat sebagai **open design issue**.

#### Technical Feasibility Status
* **Status:** **FEASIBLE**
* **Alasan:** Data resmi NASA terbuka, format CSV terstruktur rapi, 13 parameter lengkap, memiliki resolusi spasial tinggi (375 m), dan memuat besaran fisik penting (FRP & BT).

---

### Source 3: BMKG (Badan Meteorologi, Klimatologi, dan Geofisika)

> [!WARNING]
> **PEMISAHAN PENTING DUA JALUR DATA BMKG:**
> Hasil eksplorasi menunjukkan bahwa BMKG memiliki dua jalur data yang berbeda secara mendasar:
> 1. **BMKG Data Online (`dataonline.bmkg.go.id`):** Portal resmi arsip data iklim historis stasiun terukur.
> 2. **BMKG Open Data API (`api.bmkg.go.id`):** API publik prakiraan cuaca 3 hari ke depan tingkat desa/kelurahan.

#### Accessibility
* **1. BMKG Data Online (Historical Climate Data):**
  * **Sifat Akses:** **Restricted Access / Wajib Autentikasi**.
  * **Kebutuhan Akun:** **Wajib registrasi akun resmi dan login**.
  * **Hambatan Teknis:** Form login dan alur query web diproteksi oleh **Google reCAPTCHA v3** dan mekanisme sesi CSRF.
  * **Hasil Pengujian Unduh Otomatis:** **BELUM BERHASIL (BLOCKED)**. Sesuai batasan tugas, mekanisme login dan CAPTCHA tidak dibypass.
* **2. BMKG Open Data API (Forecast / NRT):**
  * **Sifat Akses:** **100% Public Open Access**.
  * **Kebutuhan Akun:** **Tanpa API key, tanpa akun**.
  * **Hasil Pengujian Unduh & Baca:** **BERHASIL**. Data prakiraan 10 lokasi sampel di 5 provinsi Kalimantan berhasil diambil dan ditabulasi secara programatis (186 rekaman cuaca).

#### Available Parameters (Berdasarkan Katalog Resmi BMKG Data Online)
Sepuluh parameter cuaca/iklim permukaan terverifikasi tercantum dalam sistem katalog:
1. `temp_avg`: Temperatur rata-rata harian (°C)
2. `temp_max`: Temperatur maksimum harian (°C)
3. `temp_min`: Temperatur minimum harian (°C)
4. `rainfall`: Curah hujan harian (mm)
5. `hum_avg`: Kelembapan relatif rata-rata harian (%)
6. `sunshine`: Lamanya penyinaran matahari (jam / %)
7. `wind_avg`: Kecepatan angin rata-rata harian (m/s atau knot)
8. `wind_speed`: Kecepatan angin maksimum harian (m/s atau knot)
9. `wind_dir_car`: Arah angin terbanyak harian (*cardinal direction*)
10. `wind_dir`: Arah angin saat kecepatan maksimum harian (derajat)

*(Catatan: Parameter di atas terbukti ada dalam skema dan basis data sistem, namun pengunduhan berkas historis mandiri via script otomatis terhalang autentikasi).*

#### Spatial Coverage
* **Karakteristik Pengamatan:** Pengamatan berbasis titik stasiun fisik (*station-based point observations*).
* **Kerapatan Stasiun di Kalimantan:** **Sangat Jarang (*Sparse*)**.
  * Dari total 199 stasiun UPT BMKG di Indonesia, hanya terdapat sekitar **10–15 stasiun UPT di seluruh Pulau Kalimantan**.
  * Lima stasiun representatif yang terverifikasi di sistem:
    - *Kalimantan Barat:* Stasiun Meteorologi Supadio Pontianak (`96581`)
    - *Kalimantan Tengah:* Stasiun Meteorologi Tjilik Riwut Palangka Raya (`96655`)
    - *Kalimantan Selatan:* Stasiun Meteorologi Syamsudin Noor Banjarbaru/Banjarmasin (`96685`)
    - *Kalimantan Timur:* Stasiun Meteorologi SAMS Sepinggan Balikpapan (`96633`)
    - *Kalimantan Utara:* Stasiun Meteorologi Juwata Tarakan (`96509`)
* **Distribusi Geografis:** Stasiun terpusat di bandar udara kota-kota utama. Wilayah pedalaman hutan lebat dan kubah gambut (*peatland dome*) berjarak 100–300 km dari stasiun terdekat.

#### Temporal Characteristics & Regulatory Constraints
* **Katalog Sistem:** Menampilkan rentang tahun 1970 s.d. 2026.
* **Limitasi Akses Mandiri Publik (*Self-Service Limitation*):**
  * **Peraturan BMKG No. 4 Tahun 2022:** Membatasi akses unduh mandiri via portal web hanya untuk **periode 2 tahun terakhir**.
  * **Batas Volume:** Maksimal **30 hari (1 bulan) per satu kali proses unduh**.
  * **Resolusi:** Data harian (*daily*) dan bulanan (*monthly*) dapat diakses via portal web; data resolusi jam-jaman (*hourly/sub-daily*) **tidak tersedia untuk unduhan mandiri bebas** dan harus melalui permohonan khusus via PTSP BMKG (`ptsp.bmkg.go.id`).

#### SACA / SACA&D Exploration (Separate Alternative)
* **Identifikasi:** *Southeast Asian Climate Assessment & Dataset* (`sacad.bmkg.go.id`), inisiatif kolaborasi BMKG, KNMI (Belanda), dan WMO.
* **Variabel:** Presipitasi harian (RR), Suhu harian (TG, TN, TX), Kecepatan angin (FG), Kelembapan (HU), Tekanan udara (PP) dalam format teks ASCII standar.
* **Limitasi SACA:**
  * **Hanya $\approx 17\%$ data stasiun yang berstatus "Public" / dapat diunduh bebas.**
  * Stasiun berlabel *"non-downloadable"* tidak dapat diunduh via web dan membutuhkan permohonan izin riset tertulis via email ke `sacad@bmkg.go.id`.
  * Portal web dilindungi oleh Cloudflare WAF.

#### Technical Feasibility Status
* **Status:** **PARTIALLY FEASIBLE**
* **Alasan:** Data historis resmi BMKG terbukti ada dan terawat secara terstandarisasi, namun akuisisi historis mandiri via script otomatis terhalang oleh autentikasi akun, Google reCAPTCHA v3, batasan regulasi 2 tahun terakhir, serta batasan kuota unduh 30 hari.

---

## 3. Main Comparison Table

Perbandingan ringkas karakteristik teknis dari ketiga kandidat sumber data:

| Aspek Evaluasi | Himawari-9 AHI | NASA VIIRS 375m | BMKG Data Online (Historical) |
|---|---|---|---|
| **Source Type** | Penginderaan Jauh Geostasioner (*GEO Remote Sensing*) | Penginderaan Jauh Orbit Rendah (*LEO Polar Remote Sensing*) | Pengamatan Stasiun Permukaan Darat (*In-situ Weather Stations*) |
| **Main Data Type** | Grid Raster Citra Satelit (2D Array) | Vektor Titik Anomali Termal (*Point Hotspot Events*) | Deret Waktu Titik Stasiun (*Tabular Time-Series*) |
| **Access Platform** | NOAA Public AWS S3 (`s3://noaa-himawari9/`) | NASA LANCE / FIRMS | BMKG Data Online (`dataonline.bmkg.go.id`) |
| **Account / API Key** | **Tidak Perlu** (Anonymous / Unsigned) | **Tidak Perlu** untuk bulk CSV NRT (Free `MAP_KEY` untuk API area) | **Wajib Akun** (Login + Google reCAPTCHA v3) |
| **Actual Data Obtained** | **Ya** (Segmen B07 terunduh dan diparsing) | **Ya** (7.764 rekaman Asia Tenggara, 5.122 di Kalimantan) | **Belum** untuk historical via automated script; **Ya** untuk feed prakiraan NRT |
| **Main Parameters Verified** | Band B07 Brightness Temperature (~3.9 $\mu\text{m}$, Kelvin) | `bright_ti4`, `bright_ti5`, `frp`, `confidence`, `scan`, `track`, `daynight` | 10 parameter tercatat di katalog (`Tavg`, `Tx`, `Tn`, `RR`, `RH`, `ss`, `ff_avg`, `ff_x`, `ddd_car`, `ddd_x`) |
| **Spatial Resolution** | $\approx 2.0\text{ km}$ (di ekuator/nadir) | $\approx 375\text{ m}$ (di nadir; ~750–800 m di tepi swath) | Titik spesifik koordinat stasiun (*Point representation*) |
| **Spatial Coverage** | Cakupan disk luas; Segmen S0510 meng-cover Kalimantan bagian utara | Seluruh daratan & perairan Kalimantan | $\approx 10\text{–}15$ stasiun UPT di Kalimantan (terpusat di bandara) |
| **Temporal Characteristics** | Tiap **10 menit** kontinu (144 snapshot per hari) | **1–2 kali per 24 jam** (lintas siang ~12:46 WIB, malam ~00:00 WIB) | Resolusi harian (*daily*) & bulanan; resolusi jam-jaman non-publik |
| **Historical Availability** | Tersedia penuh 2015 s.d. sekarang di AWS S3 | Tersedia penuh 2012 s.d. sekarang (NOAA-20 sejak 2018) | Tersedia di katalog >50 tahun; akses web mandiri dibatasi **2 tahun terakhir** |
| **Data Format** | Format biner AHI HSD (.DAT) $\rightarrow$ diekspor ke NetCDF | Berkas teks CSV (*Comma-Separated Values*) | Berkas Microsoft Excel (`.xlsx`) atau CSV |
| **Geolocation Verified** | **Ya** (Proyeksi GEOS, error round-trip $<1\text{ km}$) | **Ya** (WGS84 lat/lon desimal derajat) | **Ya** (Koordinat WGS84 stasiun UPT) |
| **Main Limitation** | Segmen S0510 belum mencakup Kalimantan Selatan (butuh S0610) | Snapshot hanya 2x/hari; tertutup awan; bukan absolute ground truth | Wajib login; reCAPTCHA; limit 2 tahun (Perka 4/2022); limit 30 hari/unduh |
| **Integration Tested** | **Ya** (Prototype spatial join dengan VIIRS berhasil) | **Ya** (Prototype spatial join dengan Himawari berhasil) | **Belum** diuji join dengan satelit |
| **Potential Issue** | Volume penyimpanan tinggi jika multi-band / multi-temporal | Potensi *target leakage* jika VIIRS dipakai tanpa pemisahan temporal ketat | Kerapatan stasiun darat sangat jarang di area hutan/gambut |
| **Feasibility Status** | **FEASIBLE** | **FEASIBLE** | **PARTIALLY FEASIBLE** |

---

## 4. Parameter / Information Coverage Table

Tabel pemetaan ketersediaan kategori informasi yang relevan untuk analisis risiko kebakaran:

> **Keterangan Simbol:**  
> * ✅ *Available / verified:* Tersedia dan terverifikasi pada sampel yang dieksplorasi.  
> * 🟡 *Partially available / indirectly available:* Tersedia sebagian atau dapat diturunkan secara tidak langsung.  
> * ❌ *Not verified / not available:* Belum diverifikasi atau tidak tersedia pada sumber data tersebut.  
> * ⚠️ *Available but with limitation:* Tersedia namun memiliki batasan teknis, frekuensi, atau regulasi yang signifikan.  

| Kategori Informasi | Himawari-9 AHI | NASA VIIRS 375m | BMKG Data Online (Historical) | Catatan / Keterangan Teknis |
|---|:---:|:---:|:---:|---|
| **Suhu / Informasi Termal (*Temperature*)** | ✅ | ✅ | ⚠️ | Himawari: BT B07 (3.9 $\mu\text{m}$); VIIRS: BT I-4 & I-5; BMKG: Suhu harian ($T_{avg}, T_x, T_n$) di katalog, akses mandiri dibatasi 2 tahun. |
| **Curah Hujan (*Rainfall / Precipitation*)** | 🟡 | ❌ | ⚠️ | Himawari: Tidak mengukur langsung (proksi via ketebalan awan); VIIRS: Tidak ada; BMKG: Curah hujan harian ($RR$) di katalog stasiun. |
| **Kelembapan Udara (*Humidity*)** | 🟡 | ❌ | ⚠️ | Himawari: Tersedia via kanal uap air B08/B09/B10 (*not verified* di pipeline ini); VIIRS: Tidak ada; BMKG: $RH_{avg}$ harian di katalog. |
| **Kondisi Angin (*Wind Speed & Direction*)** | ❌ | ❌ | ⚠️ | Himawari: Tidak langsung (butuh pelacakan vektor awan AMV); VIIRS: Tidak ada; BMKG: Kecepatan & arah angin harian ($ff, ddd$) di katalog. |
| **Sinyal Vegetasi / Permukaan Lahan** | 🟡 | ❌ | ❌ | Himawari: Memiliki kanal tampak/NIR (B03/B04 untuk NDVI) (*not verified* di pipeline ini); VIIRS Active Fire: Tidak ada (ada di produk VIIRS Land terpisah); BMKG: Tidak ada. |
| **Titik Panas / Anomali Termal Aktif** | 🟡 | ✅ | ❌ | Himawari: Dapat mendeteksi anomali termal sub-piksel resolusi 2 km; VIIRS: Deteksi aktif resolusi tinggi 375 m dengan nilai FRP; BMKG: Tidak memantau api. |
| **Informasi Tutupan Awan (*Cloud Information*)** | 🟡 | 🟡 | ⚠️ | Himawari: Terdeteksi jelas pada kontras termal/albedo; VIIRS: Mempengaruhi kualitas deteksi (flag kualitas); BMKG: Penyinaran matahari ($ss$) di katalog stasiun. |
| **Lokasi Spasial (*Spatial Coordinates*)** | ✅ | ✅ | ⚠️ | Himawari: Grid 2 km kontinu (proyeksi GEOS); VIIRS: Koordinat titik diskrit 375 m; BMKG: Titik stasiun fisik (sangat jarang/sparse di pedalaman). |
| **Informasi Waktu (*Timestamp*)** | ✅ | ✅ | ⚠️ | Himawari: Tiap 10 menit UTC; VIIRS: Snapshot UTC 1–2 kali per hari; BMKG: Harian/bulanan UTC+7/UTC+8, dibatasi unduh 30 hari/chunk. |

---

## 5. Accessibility & Ease-of-Use Comparison

Perbandingan aspek kemudahan teknis dalam pengoperasian pipeline data (tanpa pemeringkatan atau skor numerik):

| Faktor Aksesibilitas | Himawari-9 AHI | NASA VIIRS 375m | BMKG Data Online (Historical) |
|---|---|---|---|
| **Public Access** | Terbuka penuh tanpa restriksi IP atau registrasi | Terbuka penuh untuk NRT bulk CSV; API area membutuhkan key gratis | Tertutup di balik form registrasi dan verifikasi akun |
| **Authentication** | Tidak memerlukan autentikasi (*anonymous S3*) | Tidak memerlukan token untuk file unduhan langsung; MAP_KEY gratis untuk API | Memerlukan username/password dan terproteksi Google reCAPTCHA v3 |
| **Programmatic Access** | Sangat mudah via AWS SDK (`boto3`) atau HTTP | Sangat mudah via HTTP GET standar (`curl`, `requests`, `urllib`) | Sulit via script otomatis tanpa intervensi browser / session handling |
| **Download Complexity** | Rendah (arsip terstruktur rapi berdasarkan tanggal/jam di S3 bucket) | Sangat rendah (berkas CSV harian/mingguan siap unduh per region) | Tinggi (kuota 30 hari per unduh, membutuhkan form submission interaktif) |
| **Data Format Complexity** | Menengah (format biner satelit AHI HSD membutuhkan pustaka Satpy/pyresample) | Sangat rendah (format CSV tabular standar langsung terbaca oleh Pandas) | Rendah (format Excel/CSV standar setelah berhasil diunduh via web) |
| **Processing Complexity** | Menengah (dekompresi bz2, reproyeksi koordinat GEOS, subsetting grid) | Rendah (filtering bounding box koordinat dan konversi format waktu standar) | Rendah hingga menengah (penanganan missing value berkode `8888`/`9999`) |
| **Geolocation Handling** | Membutuhkan transformasi koordinat proyeksi geostasioner ke lat/lon geodetik | Siap pakai (koordinat centroid lintang/bujur WGS84 sudah tersedia) | Siap pakai untuk titik stasiun (tetapi membutuhkan interpolasi jika ingin ke grid) |
| **Main Blocker** | Tidak ada blocker akses; kendala hanya kelengkapan segmen spasial (S0610) | Tidak ada blocker akses; kendala hanya resolusi temporal orbit polar | **Blocker autentikasi login, Google reCAPTCHA v3, dan regulasi Perka No. 4/2022** |

---

## 6. Current Status Summary

### What We Know So Far (Fakta Terverifikasi)
1. **Akses Himawari-9 Terbukti:** Data AHI L1b Band B07 (~3.9 $\mu\text{m}$) dari AWS S3 publik berhasil diunduh, dibaca dengan Satpy, dan diekspor ke NetCDF CF-compliant tanpa kendala kredensial.
2. **Karakteristik Fisik B07 Terkonfirmasi:** Nilai terkalibrasi langsung dalam satuan Kelvin (Brightness Temperature) dengan resolusi spasial ~2 km dan frekuensi pengamatan 10 menit.
3. **Cakupan Spasial S0510 Terbatas:** Segmen S0510 terbukti hanya mencakup wilayah Kalimantan di utara ekuator ($0^\circ \text{ s.d. } 12^\circ\text{N}$). Wilayah selatan ekuator membutuhkan segmen S0610.
4. **Akses VIIRS 375m Terbukti:** Data NOAA-20 VIIRS Active Fire Collection 2 NRT berhasil diunduh dari NASA FIRMS dalam format CSV terbuka tanpa hambatan autentikasi.
5. **Skema Parameter VIIRS Terverifikasi:** Tiga belas parameter standar FIRMS (termasuk koordinat, `bright_ti4`, `bright_ti5`, `frp`, `confidence`, dan `daynight`) terverifikasi lengkap pada 5.122 deteksi hotspot di Kalimantan.
6. **Semantik VIIRS Dipahami:** Titik panas VIIRS merepresentasikan anomali termal sub-piksel (bukan ground truth mutlak atas seluruh kebakaran), dipengaruhi oleh tutupan awan dan batasan overpass 1–2 kali per hari.
7. **Prototype Integrasi Spasial Berhasil:** Uji coba pemetaan titik VIIRS 375m ke grid Himawari 2 km menggunakan KDTree berhasil mendemonstrasikan jarak spasial $< 1.1\text{ km}$ pada area yang ter-cover.
8. **Katalog Historis BMKG Terverifikasi:** Basis data BMKG Data Online memverifikasi ketersediaan 10 parameter iklim penting pada stasiun-stasiun meteorologi utama di 5 provinsi Kalimantan.
9. **Akses Unduh Historis BMKG Terhambat:** Pengunduhan otomatis data historis BMKG Data Online terhambat oleh form login wajib, proteksi Google reCAPTCHA v3, dan regulasi Perka BMKG No. 4/2022 (akses mandiri terbatas 2 tahun terakhir, 30 hari per unduhan).
10. **Kerapatan Stasiun BMKG Sangat Jarang:** Jaringan stasiun fisik BMKG di Kalimantan sangat sparse (~10–15 stasiun UPT di bandara kota besar), meninggalkan area pedalaman gambut dan hutan tanpa pemantauan in-situ langsung.

---

### Open Questions (Hal yang Belum Diputuskan / Belum Diverifikasi)

* **[OPEN QUESTION 1] Kelengkapan Spasial Himawari:**  
  Kapan dan bagaimana alur pipeline diperluas untuk mengunduh serta menggabungkan segmen **S0610** bersama S0510 agar seluruh daratan Kalimantan (termasuk Kalimantan Selatan dan Tengah) ter-cover penuh?
* **[OPEN QUESTION 2] Strategi Pengadaan Data Cuaca Historis:**  
  Untuk fase pelatihan model historis (*training phase*), apakah tim akan:
  - Mengajukan permohonan data penelitian multi-tahun resmi melalui portal **PTSP BMKG** (`ptsp.bmkg.go.id`), ATAU
  - Menggunakan dataset reanalisis meteorologi global terasimilasi (seperti **ERA5-Land** resolusi ~9 km atau **CHIRPS** untuk curah hujan harian) sebagai *backbone* historis, lalu memanfaatkan **API Publik BMKG (`api.bmkg.go.id`)** untuk fase inferensi operasional masa depan?
* **[OPEN QUESTION 3] Peran VIIRS dalam Desain Model (Target vs Feature):**  
  Bagaimana memposisikan VIIRS secara formal dalam arsitektur waktu:
  - Apakah murni sebagai **label/target biner/kontinu** di masa depan ($T + \Delta t$)?
  - Apakah dapat diformulasikan memiliki peran ganda (sebagai fitur agregat riwayat kebakaran masa lalu $T - 7\text{ hari}$ sekaligus label target masa depan)?
* **[OPEN QUESTION 4] Format Representasi Spasial Integrasi:**  
  Apakah integrasi multi-sumber nantinya akan distandarisasi menggunakan grid raster kanonikal Himawari 2 km (spatial binning titik VIIRS ke dalam piksel 2 km), atau menggunakan representasi berbasis poligon wilayah administratif / unit hidrologi lahan gambut?
* **[OPEN QUESTION 5] Jendela Waktu (*Temporal Window*) Integrasi:**  
  Berapa batas toleransi waktu yang akan diterapkan ketika mengaitkan snapshot VIIRS (yang terjadi ~12:46 WIB dan ~00:00 WIB) dengan deret waktu citra Himawari (tiap 10 menit) dan observasi cuaca harian?

---

### Next Exploration (Langkah Eksplorasi Logis Berikutnya)

1. **Uji Coba Pengambilan & Penggabungan Segmen Himawari S0610:**  
   Menguji download dan penggabungan (*stitching*) segmen S0510 dan S0610 untuk memastikan daratan Kalimantan bagian selatan tertutup tanpa celah koordinat.
2. **Eksplorasi Kandidat Data Cuaca Reanalisis / Gridded (ERA5-Land / CHIRPS):**  
   Melakukan uji kelayakan aksesibilitas terhadap dataset reanalisis meteorologi terbuka berjangkauan historis panjang (misalnya ERA5-Land via CDS API atau CHIRPS via HTTP/FTP) sebagai opsi komparasi terhadap data stasiun BMKG yang sparse.
3. **Eksplorasi Data Lingkungan Statis / Kuasi-Statis (Land Cover, Peatland, Topografi):**  
   Mengeksplorasi kandidat dataset peta kubah gambut Indonesia (Kementerian LHK / BBSDLP) dan tutupan lahan (*land cover*) untuk melengkapi faktor kerentanan biofisik lahan di Kalimantan.
4. **Penyusunan Desain Kerangka Waktu Eksperimen (*Temporal Alignment Framework*):**  
   Mendiskusikan dan merumuskan proposal jendela waktu (misal: periode studi kebakaran historis tahun 2019 atau 2023) tanpa mengunci arsitektur model sebelum semua sumber data terbukti siap.

---
*Catatan teknis ini disusun berdasarkan hasil eksperimen nyata dan bukti data yang tersimpan di direktori `outputs/` dan `data/`.*
