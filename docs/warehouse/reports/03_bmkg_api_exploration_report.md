# BMKG Meteorological Data — Exploratory Acquisition & Validation Report

**Project:** AI Wildfire / Land Fire Risk Prediction — Kalimantan (Borneo)  
**Role:** Data Mining / Data Acquisition  
**Date of Exploration:** 2026-09-20  
**Status:** Murni Eksplorasi Kelayakan Teknis (Belum Ada Finalisasi Fitur / Model)  

---

## 1. Source

* **Institusi Resmi:** Badan Meteorologi, Klimatologi, dan Geofisika (BMKG) Republik Indonesia.
* **Portal Data Resmi:**
  1. **Data Terbuka BMKG:** [https://data.bmkg.go.id/](https://data.bmkg.go.id/)
  2. **API Publik BMKG:** [https://api.bmkg.go.id/publik/](https://api.bmkg.go.id/publik/)
  3. **Repository Panduan Resmi:** [https://github.com/infoBMKG/data-cuaca](https://github.com/infoBMKG/data-cuaca)
  4. **Pusat Database Historis Stasiun (Data Online):** [https://dataonline.bmkg.go.id/](https://dataonline.bmkg.go.id/)
  5. **Sistem Peringatan Kebakaran Hutan & Lahan (SPARTAN / FDRS):** [https://spartan.bmkg.go.id/](https://spartan.bmkg.go.id/)

---

## 2. Access Method

* **Protokol:** HTTP/HTTPS REST API (JSON over HTTPS).
* **Endpoint Format:**
  ```text
  GET https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={kode_wilayah_tingkat_iv}
  ```
* **Metode Pemanggilan:** HTTP GET standar (dapat diakses via `curl`, Python `requests`, atau `urllib`).
* **Header yang Direkomendasikan:** Disarankan menyertakan `User-Agent` berbasis peramban modern (karena reverse proxy / Cloudflare BMKG memblokir default user-agent pustaka otomatis seperti bawaan `urllib/3.x`).

---

## 3. Authentication Requirement

* **Status Autentikasi:** **TIDAK MEMERLUKAN API KEY (Free Open Access)**.
* **Akun Pengguna:** Tidak diperlukan pendaftaran akun untuk endpoint `api.bmkg.go.id/publik/prakiraan-cuaca`.
* **Rate Limit (Batas Akses Resmi):** Maksimum **60 permintaan per menit per alamat IP**.
* **Ketentuan Penggunaan:** Data bersifat terbuka (Open Government Data). Pengguna wajib mencantumkan atribusi resmi: *"Data bersumber dari Badan Meteorologi, Klimatologi, dan Geofisika (BMKG)"*.

---

## 4. Dataset / API Identification

* **Nama Produk:** Data Terbuka Prakiraan Cuaca Wilayah Administrasi Tingkat IV (Kelurahan / Desa).
* **Standar Pengkodean:** Keputusan Menteri Dalam Negeri (Kepmendagri) Nomor 100.1.1-6117 Tahun 2022.
* **Cakupan Spasial Produk:** Seluruh kelurahan dan desa di Indonesia (~83.000 wilayah tingkat IV).
* **Cakupan Temporal Produk:** Prakiraan cuaca 3 hari ke depan (*rolling 72-hour forecast*) dengan resolusi waktu per 3 jam.

---

## 5. Sample Data

Sample nyata berhasil diunduh dan disimpan secara terisolasi tanpa modifikasi:
* **Direktori Raw:** `data/bmkg/raw/` (berisi file mentah format JSON, contoh: `bmkg_prakiraan_61.01.01.2001.json`).
* **Direktori Processed:** `data/bmkg/processed/bmkg_kalimantan_weather_sample.csv` (186 rekaman terstruktur).
* **Lokasi Sampel:** 10 titik yang mewakili 5 provinsi di Kalimantan:
  1. *Kalimantan Barat:* Sambas (`61.01.01.2001`) — Lat 1.3419°, Lon 109.3537°
  2. *Kalimantan Tengah:* Kotawaringin Barat / Kumai (`62.01.01.1011`) — Lat -2.7220°, Lon 111.7312°
  3. *Kalimantan Selatan:* Tanah Laut / Takisung (`63.01.01.2001`) — Lat -3.8691°, Lon 114.6799°
  4. *Kalimantan Selatan:* Kotabaru (`63.02.01.2001`) — Lat -4.8458°, Lon 115.7532°
  5. *Kalimantan Selatan:* Barito Kuala (`63.04.01.2001`) — Lat -3.4642°, Lon 114.4089°
  6. *Kalimantan Timur:* Paser / Batu Sopang (`64.01.01.2009`) — Lat -1.9000°, Lon 115.8603°
  7. *Kalimantan Timur:* Kutai Barat (`64.02.01.2001`) — Lat -0.6163°, Lon 116.4575°
  8. *Kalimantan Timur:* Berau / Kelay (`64.03.01.2001`) — Lat 1.5132°, Lon 117.3011°
  9. *Kalimantan Utara:* Bulungan / Tanjung Palas (`65.01.01.1001`) — Lat 2.8143°, Lon 117.3550°
  10. *Kalimantan Utara:* Nunukan (`65.03.01.2001`) — Lat 4.0569°, Lon 117.8968°

---

## 6. Available Variables

Berdasarkan struktur respon JSON aktual dari endpoint BMKG, berikut adalah inventarisasi variabel meteorologi:

| Variabel | Nama Kolom Asli | Satuan Asli | Status Ketersediaan | Deskripsi & Makna |
|---|---|---|---|---|
| **Suhu Udara (Temperature)** | `t` | °C (Celsius) | **Tersedia (Yes)** | Suhu udara permukaan pada ketinggian 2 meter |
| **Kelembapan Relatif (Humidity)** | `hu` | % (Persen) | **Tersedia (Yes)** | Kelembapan nisbi udara permukaan |
| **Presipitasi / Curah Hujan** | `tp` | mm (Millimeter) | **Tersedia (Yes)** | Akumulasi curah hujan per periode 3 jam |
| **Kecepatan Angin (Wind Speed)** | `ws` | km/jam | **Tersedia (Yes)** | Kecepatan hembusan angin horizontal |
| **Arah Angin (Wind Direction Deg)** | `wd_deg` | derajat (0–360°) | **Tersedia (Yes)** | Sudut azimut asal arah hembusan angin |
| **Arah Angin (Wind Cardinal)** | `wd` | teks kardinal | **Tersedia (Yes)** | Arah mata angin asal (contoh: "SE", "NW", "E") |
| **Arah Tujuan Angin** | `wd_to` | teks kardinal | **Tersedia (Yes)** | Arah mata angin tujuan pergerakan udara |
| **Tutupan Awan (Total Cloud Cover)**| `tcc` | % (Persen) | **Tersedia (Yes)** | Persentase tutupan awan di atmosfer |
| **Kode Cuaca Numerik** | `weather` | integer code | **Tersedia (Yes)** | Kode klasifikasi kondisi atmosfer BMKG |
| **Deskripsi Cuaca (ID)** | `weather_desc` | teks Indonesia | **Tersedia (Yes)** | Deskripsi cuaca (misal: "Cerah", "Hujan Ringan", "Kabut/Asap") |
| **Deskripsi Cuaca (EN)** | `weather_desc_en` | teks Inggris | **Tersedia (Yes)** | Deskripsi cuaca bahasa Inggris (misal: "Sunny", "Light Rain") |
| **Jarak Pandang (Visibility)** | `vs` | km | *Tercantum tapi Null* | Field ada dalam schema tapi bernilai `null` pada feed publik |
| **Tekanan Udara (Pressure)** | - | hPa | **Tidak Tersedia (No)** | Tidak disediakan di feed prakiraan kelurahan |
| **Radiasi Matahari (Solar Radiation)**| - | W/m² | **Tidak Tersedia (No)** | Tidak disediakan di feed prakiraan kelurahan |

---

## 7. Schema

Struktur skema data hasil tabulasi tabular (`data/bmkg/processed/bmkg_kalimantan_weather_sample.csv`):

```text
Column Name          Data Type    Sample Value            Description
---------------------------------------------------------------------------------------------------
provinsi             string       Kalimantan Barat        Nama provinsi
kabupaten_kota       string       Sambas                  Nama kabupaten / kota
kecamatan            string       Sambas                  Nama kecamatan
desa_kelurahan       string       Dalam Kaum              Nama desa / kelurahan
adm4                 string       61.01.01.2001           Kode wilayah administrasi Kemendagri tingkat IV
latitude             float64      1.341904                Garis lintang centroid desa (derajat)
longitude            float64      109.353707              Garis bujur centroid desa (derajat)
timezone             string       Asia/Pontianak          Zona waktu resmi (Asia/Pontianak / Asia/Makassar)
raw_datetime         string       2026-09-20T16:00:00Z    Timestamp asli ISO-8601 UTC
raw_utc_datetime     string       2026-09-20 16:00:00     Timestamp teks UTC
raw_local_datetime   string       2026-09-20 23:00:00     Timestamp teks waktu lokal (WIB/WITA)
analysis_date        string       2026-09-20T12:00:00     Waktu pembuatan model analisis BMKG
temperature_c        float64      25.0                    Suhu udara (derajat Celsius)
humidity_pct         float64      97.0                    Kelembapan relatif udara (persen)
precipitation_mm     float64      0.0                     Curah hujan per 3 jam (mm)
cloud_cover_pct      float64      84.0                    Tutupan awan (persen)
wind_speed_kmh       float64      0.8                     Kecepatan angin (km/jam)
wind_dir_deg         float64      131.0                   Arah angin (derajat)
wind_dir_cardinal    string       E                       Arah mata angin
weather_code         int64        10                      Kode numerik cuaca BMKG
weather_desc_id      string       Udara Kabur             Deskripsi cuaca (Bahasa Indonesia)
weather_desc_en      string       Mist/Haze               Deskripsi cuaca (Bahasa Inggris)
visibility_km        float64      NaN                     Jarak pandang (null)
datetime_utc         timestamp    2026-09-20 16:00:00+00  Timestamp kanonikal UTC bertipe datetime
```

---

## 8. Spatial Information

* **Sistem Koordinat:** Latitude dan Longitude diberikan secara eksplisit pada blok meta `lokasi` dalam format WGS84 desimal derajat.
* **Akurasi Spasial:** Koordinat merepresentasikan titik tengah (*centroid*) dari wilayah administratif desa/kelurahan terkait, bukan koordinat instrumen stasiun fisik.
* **Rentang Koordinat Sampel Kalimantan:**
  * Latitude: `[-4.8458°, 4.0569°]`
  * Longitude: `[109.3537°, 117.8968°]`
  * Seluruh titik berada strictly di dalam bounding box studi Kalimantan (`lon: [108.0, 119.0]`, `lat: [-5.0, 7.0]`).
* **Visualisasi Spasial:** Peta sebaran titik observasi BMKG telah dipetakan dan disimpan di [`outputs/validation/bmkg_kalimantan_coverage.png`](file:///c:/Users/figoa/Documents/my-project/data-mining-borneo/outputs/validation/bmkg_kalimantan_coverage.png).

---

## 9. Temporal Information

* **Resolusi Waktu (Cadence):** Per **3 jam** (00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 UTC).
* **Jangkauan Waktu (Forecast Horizon):** 3 hari ke depan (72 jam) terhitung dari waktu analisis model numerik BMKG. Total 18–24 langkah waktu per lokasi.
* **Zona Waktu Teridentifikasi:**
  * Wilayah barat Kalimantan (Kalbar, Kalteng): `Asia/Pontianak` (WIB = UTC+7).
  * Wilayah timur/selatan Kalimantan (Kalsel, Kaltim, Kaltara): `Asia/Makassar` (WITA = UTC+8).
* **Format Timestamp:** Disediakan dalam 3 bentuk sekaligus (`raw_datetime` ISO UTC, `raw_utc_datetime`, dan `raw_local_datetime`), sehingga meminimalkan risiko kebingungan zona waktu (*timezone ambiguity*).

---

## 10. Kalimantan Coverage

* **Kelengkapan Provinsi:** Mencakup **100% provinsi di Kalimantan** (5 dari 5 provinsi: Kalimantan Barat, Kalimantan Tengah, Kalimantan Selatan, Kalimantan Timur, dan Kalimantan Utara).
* **Kepadatan Titik Potensial:** Terdapat total **7.179 kode wilayah desa/kelurahan** di seluruh Pulau Kalimantan berdasarkan basis data Kemendagri:
  * Kalimantan Barat (61): 2.133 desa/kelurahan
  * Kalimantan Tengah (62): 1.568 desa/kelurahan
  * Kalimantan Selatan (63): 2.007 desa/kelurahan
  * Kalimantan Timur (64): 1.035 desa/kelurahan
  * Kalimantan Utara (65): 436 desa/kelurahan
* **Kelebihan Spasial:** Kepadatan spasial berbasis kelurahan/desa ini jauh lebih rapat dibanding hanya mengandalkan ~20 stasiun meteorologi fisik BMKG di bandara-bandara Kalimantan.

---

## 11. Data Quality Assessment

Dari inspeksi kuantitatif terhadap 186 rekaman cuaca sampel di Kalimantan:

* **Missing Values:**
  * Suhu, kelembapan, curah hujan, tutupan awan, kecepatan angin, arah angin: **0% missing (lengkap 100%)**.
  * Visibility (`vs`): **100% null** (tidak disediakan pada feed kelurahan).
* **Duplikasi:** **0 duplikasi**.
* **Uji Nilai Fisik (Physical Sanity Check):**
  * Suhu udara (`temperature_c`): Min **22.0°C**, Median **26.0°C**, Mean **26.9°C**, Max **34.0°C**. Nilai ini wajar dan realistis untuk wilayah tropis khatulistiwa.
  * Kelembapan relatif (`humidity_pct`): Min **44.0%**, Median **85.0%**, Mean **81.9%**, Max **99.0%**. Konsisten dengan iklim hutan hujan tropis basah dan siklus diurnal (kelembapan turun saat siang terik, naik mendekati 100% saat malam/dini hari).
  * Curah hujan (`precipitation_mm`): Min **0.0 mm**, Median **0.0 mm**, Max **3.3 mm/3h**. Nilai non-negatif dan konsisten.
  * Kecepatan angin (`wind_speed_kmh`): Min **0.2 km/jam**, Median **7.7 km/jam**, Max **30.5 km/jam**.
  * Arah angin (`wind_dir_deg`): Tersebar wajar antara 10° s.d. 356°.
* **Anomali yang Teridentifikasi:** Tidak ditemukan nilai fisik yang mustahil (seperti suhu negatif di dataran rendah tropis atau kelembapan > 100%).

---

## 12. Data Format

* **Format Asli Pengiriman:** Standar JSON (*JavaScript Object Notation*), UTF-8 encoded.
* **Struktur Hierarki Asli:** Objek bersarang (*nested object*), di mana array `cuaca` dikelompokkan per hari (array 2 dimensi) di dalam array `data`.
* **Kemudahan Pemrosesan:** Sangat mudah diparsing dan di-*flatten* menjadi format tabular (Pandas DataFrame, CSV, Parquet).

---

## 13. Historical Availability

> [!WARNING]
> **TEMUAN KRITIS MENGENAI KETERSEDIAAN DATA HISTORIS:**
> * API publik `api.bmkg.go.id/publik/prakiraan-cuaca` adalah **layanan prakiraan cuaca Near-Real-Time dan jangka pendek (3 hari ke depan)**. Endpoint ini **TIDAK MENYEDIAKAN ARSIP HISTORIS MULTI-BULAN ATAU MULTI-TAHUN**.
> * Data yang diperoleh dari endpoint ini hanya merepresentasikan kondisi waktu analisis saat ini ditambah proyeksi 72 jam ke depan.
> * Untuk memperoleh data historis meteorologi masa lalu (misal: 2020–2025):
>   1. Harus melalui portal **BMKG Data Online** (`dataonline.bmkg.go.id`) yang berbasis stasiun pengamatan terukur dan membutuhkan akun pendaftaran resmi, ATAU
>   2. Menggunakan dataset reanalisis meteorologi global pihak ketiga yang mengasimilasi data stasiun BMKG (seperti **ERA5-Land ECMWF**, **CHIRPS** untuk curah hujan, atau **MERRA-2 NASA**).

---

## 14. Potential Use (Hanya Eksplorasi Deskriptif — Bukan Fitur Final)

Tanpa mengunci variabel apa pun sebagai "fitur final" model ML, secara meteorologis variabel yang ditemukan memiliki relevansi teoretis berikut dalam konteks kebakaran hutan/lahan:

* **Suhu Udara (`t`):** Mempengaruhi laju evapotranspirasi dan laju pemanasan bahan bakar nabati (*fuel dryness*).
* **Kelembapan Udara (`hu`):** Berbanding terbalik dengan kemudahan bahan bakar mengering (*fine fuel moisture content*). Kelembapan rendah (<60%) meningkatkan risiko penyalaan api.
* **Curah Hujan (`tp`):** Faktor langsung pemadaman alami dan pembasahan lapisan gambut (*wetting agent*).
* **Kecepatan & Arah Angin (`ws`, `wd_deg`):** Pasokan oksigen bagi api dan vektor penyebaran jilatan api serta bara terbang (*spot fire propagation*).
* **Kondisi Cuaca (`weather_desc`):** Indikator keberadaan kabut/asap (*Mist/Haze/Smoke*) atau potensi sambaran petir (*Thunderstorm*).

---

## 15. Limitations

1. **Bukan Data Observasi Terukur Langsung:** Feed prakiraan kelurahan merupakan output dari model asimilasi numerik cuaca (*Numerical Weather Prediction / NWP*) BMKG yang di-downscale ke tingkat kelurahan, bukan sensor fisik stasiun di setiap desa.
2. **Ketiadaan Arsip Historis di API Publik:** API hanya memuat *rolling window* 3 hari. Untuk melatih model ML historis (misal: data kebakaran 2023–2024), data dari API ini tidak bisa di-query mundur secara retrospektif.
3. **Ketiadaan Variabel Tekanan & Radiasi:** Dua variabel ini tidak disertakan pada feed kelurahan publik.
4. **Visibility Sering Null:** Indikator jarak pandang tidak diisi pada feed publik.
5. **Rate Limiting:** 60 request/menit membatasi kecepatan pengambilan massal untuk 7.179 desa di Kalimantan (membutuhkan waktu ~2 jam jika ingin mengunduh seluruh desa di Kalimantan).

---

## 16. Open Questions

* **[OPEN QUESTION 1]: Strategi Sumber Data Cuaca Historis:**
  * Apakah untuk fase training model kita akan mendaftar ke portal resmi **BMKG Data Online** (`dataonline.bmkg.go.id`) untuk mengambil data historis stasiun cuaca Kalimantan, ATAU menggunakan dataset reanalisis meteorologi (misal: **ERA5-Land** pada resolusi 0.1° atau **CHIRPS**) sebagai *backbone* historis dan menggunakan API BMKG untuk inferensi operasional masa depan?
* **[OPEN QUESTION 2]: Granularitas Spasial Cuaca:**
  * Apakah cuaca akan diagregasi per kecamatan/kabupaten, diinterpolasi ke grid raster 2 km Himawari (via IDW / Kriging), atau dihubungkan ke stasiun terdekat?
* **[OPEN QUESTION 3]: Resolusi Temporal:**
  * Apakah data per 3 jam BMKG akan diagregasi menjadi nilai harian (suhu maksimum, kelembapan minimum, curah hujan akumulasi 24 jam) atau dipertahankan sebagai deret waktu per 3 jam?

---

## 17. Exploration Status & Kesimpulan

* **Kelayakan Akses Teknis:** **FEASIBLE (SANGAT LAYAK) UNTUK NRT / FUTURE FORECAST**.
  * API publik resmi BMKG beroperasi aktif, stabil, berformat JSON terstandarisasi, memuat koordinat akurat, dan tidak membutuhkan API key berbayar.
* **Kelayakan untuk Training Model Historis:** **PARTIALLY FEASIBLE**.
  * Membutuhkan kombinasi dengan portal arsip BMKG Data Online atau dataset reanalisis meteorologi pendukung karena API publik tidak menyediakan query waktu masa lalu.

---
*Laporan eksplorasi ini disimpan di `outputs/bmkg_exploration_report.md`.*
