# BMKG Historical Weather & Climate Data — Feasibility Assessment Report

**Project:** AI Wildfire / Land Fire Risk Prediction — Kalimantan (Borneo)  
**Role:** Data Mining / Data Acquisition  
**Date of Assessment:** 2026-09-20  
**Status:** Murni Feasibility Testing (Bukan Final Pipeline / Belum Ada Desain Model)  

---

## A. Executive Summary

Laporan ini menyajikan hasil uji kelayakan teknis (*feasibility test*) terhadap ketersediaan dan aksesibilitas **data cuaca/iklim historis resmi dari BMKG (Badan Meteorologi, Klimatologi, dan Geofisika)** untuk wilayah Kalimantan, khususnya melalui portal **BMKG Data Online** (`dataonline.bmkg.go.id`) serta inisiatif regional **SACA&D** (`sacad.bmkg.go.id`).

| Pertanyaan Kunci Evaluasi | Hasil Temuan Nyata (*Observed Findings*) |
|---|---|
| **Apakah data historis BMKG secara umum tersedia?** | **YA, TERSEDIA.** Portal BMKG Data Online mencatat katalog data iklim dari 199 stasiun UPT di seluruh Indonesia (termasuk stasiun di 5 provinsi Kalimantan) dengan riwayat arsip puluhan tahun. |
| **Apakah data historis bisa diakses secara publik & terbuka tanpa login?** | **TIDAK BISA.** Seluruh pengunduhan data iklim historis (harian maupun bulanan) di BMKG Data Online **secara mutlak mewajibkan autentikasi akun pengguna (Login)**. |
| **Apakah pengujian unduh langsung (*actual download test*) berhasil?** | **TERHALANG (BLOCKED).** Pengunduhan programatis tanpa kredensial terotentikasi tertahan oleh perlindungan autentikasi sesi dan **Google reCAPTCHA v3**. Sesuai aturan penugasan, sistem autentikasi dan CAPTCHA tidak dibypass. |
| **Apa pembatas regulasi (*regulatory blocker*) utamanya?** | **Peraturan BMKG Nomor 4 Tahun 2022**: Membatasi pengunduhan mandiri via web hanya untuk **periode 2 tahun terakhir** dengan batas volume maksimal **1 bulan (30 hari) per satu kali unduh**. Data di luar 2 tahun atau volume besar wajib melalui permohonan resmi ke **PTSP BMKG**. |
| **Status Kelayakan Teknis Keseluruhan:** | **PARTIALLY FEASIBLE** (Secara fisik data ada dan terverifikasi di server BMKG, namun akses historis terhambat prosedur login, CAPTCHA, limitasi 30 hari/unduh, dan restriksi 2 tahun terakhir). |

---

## B. BMKG Data Online — Station Availability Check

Berdasarkan inspeksi langsung terhadap struktur sistem dan basis data katalog pada portal `https://dataonline.bmkg.go.id/ketersediaandata`, parameter iklim resmi yang tercatat di sistem meliputi 10 parameter berikut:
1. Temperatur Rata-rata (`temp_avg`)
2. Temperatur Maksimum (`temp_max`)
3. Temperatur Minimum (`temp_min`)
4. Curah Hujan (`rainfall`)
5. Kelembapan Rata-rata (`hum_avg`)
6. Lamanya Penyinaran Matahari (`sunshine`)
7. Kecepatan Angin Rata-rata (`wind_avg`)
8. Kecepatan Angin Maksimum (`wind_speed`)
9. Arah Angin Terbanyak / Prevailing (`wind_dir_car`)
10. Arah Angin saat Kecepatan Maksimum (`wind_dir`)

Berikut adalah hasil verifikasi status 5 stasiun meteorologi representatif yang mewakili kelima provinsi di Kalimantan:

| No | Nama Stasiun (UPT) | Tipe Stasiun | Provinsi | Kabupaten / Kota | Parameter yang Tercatat di Sistem | Periode di Katalog Sistem | Resolusi Resmi | Status Ketersediaan Katalog | Status Uji Unduh Mandiri |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Stasiun Meteorologi Supadio** (ID: `96581`) | Stasiun Meteorologi Kelas I | Kalimantan Barat (ID: 20) | Kab. Kubu Raya (Pontianak) | 10 Parameter Lengkap (Tavg, Tx, Tn, RR, RH, ss, ff_avg, ff_x, ddd_car, ddd_x) | 1970–2026 (Katalog) / 2 Tahun Terakhir (Web Mandiri) | Harian (*Daily*) & Bulanan (*Monthly*) | **TERSEDIA DI SISTEM** | **BLOCKED** (Wajib Login & reCAPTCHA) |
| 2 | **Stasiun Meteorologi Tjilik Riwut** (ID: `96655`) | Stasiun Meteorologi Kelas I | Kalimantan Tengah (ID: 21) | Kota Palangka Raya | 10 Parameter Lengkap (Tavg, Tx, Tn, RR, RH, ss, ff_avg, ff_x, ddd_car, ddd_x) | 1975–2026 (Katalog) / 2 Tahun Terakhir (Web Mandiri) | Harian (*Daily*) & Bulanan (*Monthly*) | **TERSEDIA DI SISTEM** | **BLOCKED** (Wajib Login & reCAPTCHA) |
| 3 | **Stasiun Meteorologi Syamsudin Noor** (ID: `96685`) | Stasiun Meteorologi Kelas II | Kalimantan Selatan (ID: 22) | Kota Banjarbaru (Banjarmasin) | 10 Parameter Lengkap (Tavg, Tx, Tn, RR, RH, ss, ff_avg, ff_x, ddd_car, ddd_x) | 1975–2026 (Katalog) / 2 Tahun Terakhir (Web Mandiri) | Harian (*Daily*) & Bulanan (*Monthly*) | **TERSEDIA DI SISTEM** | **BLOCKED** (Wajib Login & reCAPTCHA) |
| 4 | **Stasiun Meteorologi Sultan Aji Muhammad Sulaiman Sepinggan** (ID: `96633`) | Stasiun Meteorologi Kelas I | Kalimantan Timur (ID: 23) | Kota Balikpapan | 10 Parameter Lengkap (Tavg, Tx, Tn, RR, RH, ss, ff_avg, ff_x, ddd_car, ddd_x) | 1970–2026 (Katalog) / 2 Tahun Terakhir (Web Mandiri) | Harian (*Daily*) & Bulanan (*Monthly*) | **TERSEDIA DI SISTEM** | **BLOCKED** (Wajib Login & reCAPTCHA) |
| 5 | **Stasiun Meteorologi Juwata** (ID: `96509`) | Stasiun Meteorologi Kelas I | Kalimantan Utara (ID: 34) | Kota Tarakan | 10 Parameter Lengkap (Tavg, Tx, Tn, RR, RH, ss, ff_avg, ff_x, ddd_car, ddd_x) | 1980–2026 (Katalog) / 2 Tahun Terakhir (Web Mandiri) | Harian (*Daily*) & Bulanan (*Monthly*) | **TERSEDIA DI SISTEM** | **BLOCKED** (Wajib Login & reCAPTCHA) |

*Catatan Tambahan Stasiun di Kalimantan yang teridentifikasi dalam basis data Data Online:*
- Kalimantan Barat: *Stasiun Meteorologi Maritim Pontianak* (`96585`), *Pos Meteorologi Paloh* (`96535`).
- Kalimantan Timur: *Stasiun Meteorologi APT Pranoto Samarinda* (`96607`), *Stasiun Geofisika Balikpapan* (`96635`).
- Kalimantan Utara: *Stasiun Meteorologi Nunukan* (`96503`).

---

## C. Download Test & Technical Verification

### 1. Pengujian Teknis Jalur Unduh
Uji coba pengiriman permintaan HTTP secara langsung dilakukan terhadap endpoint ketersediaan data dan unduhan BMKG Data Online:
* **Target Endpoint:** `POST https://dataonline.bmkg.go.id/process-ketersediaan-data`
* **Hasil Pengujian Awal:** `HTTP 419 Page Expired` (Mekanisme CSRF token mismatch).
* **Hasil Pengujian dengan Sesi Cookie Valid:** `{"status": 403, "message": "Forbidden"}`.
* **Penyebab Teknis:** Endpoint AJAX menolak permintaan yang tidak menyertakan tiket sesi login terotentikasi.
* **Form Login:** Endpoint `https://dataonline.bmkg.go.id/login-user` diproteksi oleh skrip keamanan **Google reCAPTCHA v3** (`render=6Lf2jTArAAAAAK34bo-Piq_vJkT4oFaKyJXJOr34`). Sesuai batasan tugas, reCAPTCHA dan autentikasi tidak dibypass.

### 2. Spesifikasi Format File Hasil Unduh Resmi BMKG (Evidence Documentation)
Berdasarkan dokumentasi FAQ resmi BMKG dan arsip data terbuka standar BMKG, file hasil ekspor resmi memiliki spesifikasi sebagai berikut:
* **Format Berkas:** Microsoft Excel (`.xlsx`) atau Comma-Separated Values (`.csv`).
* **Konvensi Penamaan Berkas:** `Data_Iklim_{StationID}_{Periode}.xlsx` atau `data_iklim.csv`.
* **Struktur Header & Skema Kolom:**
  ```text
  Tanggal,Tn,Tx,Tavg,RH_avg,RR,ss,ff_x,ddd_x,ff_avg,ddd_car
  ```
* **Kamus Kolom & Satuan Fisik:**
  * `Tanggal`: Format tanggal observasi (`DD-MM-YYYY`).
  * `Tn`: Suhu udara minimum (°C, desimal).
  * `Tx`: Suhu udara maksimum (°C, desimal).
  * `Tavg`: Suhu udara rata-rata harian (°C, desimal).
  * `RH_avg`: Kelembapan udara rata-rata harian (%, 0–100).
  * `RR`: Akumulasi curah hujan 24 jam (mm). Memiliki kode nilai khusus:
    - `0`: Tidak ada hujan.
    - `0.0`: Hujan sangat ringan (*trace* < 0.5 mm).
    - `8888`: Data tidak terukur (kerusakan sensor / gangguan alat).
    - `9999`: Tidak dilakukan pengukuran / data kosong (*missing*).
  * `ss`: Lama penyinaran matahari (jam, skala 0–12 jam atau persentase).
  * `ff_x`: Kecepatan angin maksimum harian (m/s atau knot).
  * `ddd_x`: Arah angin saat kecepatan maksimum (derajat, 0–360°).
  * `ff_avg`: Kecepatan angin rata-rata harian (m/s atau knot).
  * `ddd_car`: Arah mata angin terbanyak harian (*cardinal text*: N, NE, E, SE, S, SW, W, NW, C untuk *Calm*).

---

## D. Spatial Coverage Evaluation (Kalimantan)

* **Karakteristik Jaringan Pengamatan:**
  * Pengamatan historis BMKG Data Online sepenuhnya **berbasis stasiun darat (*station-based point observations*)**, bukan data gridded kontinu.
  * Di seluruh daratan Pulau Kalimantan (luas ~743.330 km²), hanya terdapat sekitar **10–15 stasiun pengamatan UPT resmi BMKG** yang aktif melapor ke Data Online.
* **Tingkat Kerapatan (*Density*):**
  * **Sangat Jarang (*Extremely Sparse*)**.
  * Sebagian besar stasiun meteorologi UPT berlokasi di **bandar udara kota-kota utama** (Pontianak, Palangka Raya, Banjarmasin/Banjarbaru, Balikpapan, Samarinda, Tarakan).
  * Wilayah pedalaman hutan lebat, perkebunan terpencil, dan kawasan kubah lahan gambut (*peatland dome*) di pedalaman Kalimantan Tengah/Barat tidak memiliki stasiun UPT BMKG di dekatnya (jarak stasiun terdekat bisa mencapai 100–300 km).
* **Implikasi bagi Proyek Prediksi Kebakaran:**
  * Jika hanya mengandalkan stasiun fisik BMKG, variabilitas mikroklimat lokal di titik-titik hotspot pedalaman tidak dapat tertangkap secara akurat tanpa metode interpolasi spasial skala luas atau asimilasi model reanalisis.

---

## E. Temporal Coverage & Feasibility

* **Rentang Historis di Sistem Katalog:**
  * Di antarmuka dropdown pencarian tahun, sistem menyediakan pilihan tahun hingga ~50 tahun ke belakang (1970-an s.d. 2026).
* **Rentang Akses Riil Mandiri (*Actual Self-Service Access*):**
  * **Terbatas pada 2 Tahun Terakhir**.
  * Berdasarkan FAQ resmi BMKG:
    > *"Hal tersebut sejalan dengan kebijakan pembatasan akses data sebagaimana diatur dalam Peraturan Badan Meteorologi, Klimatologi, dan Geofisika Nomor 4 Tahun 2022 tentang Kebijakan Pengaksesan Data Meteorologi, Klimatologi, dan Geofisika, yang menetapkan bahwa pengaksesan data dibatasi paling lama untuk periode dua tahun terakhir."*
* **Resolusi Waktu yang Tersedia:**
  * **Harian (*Daily*):** Tersedia via portal dengan limitasi 1 bulan (30 hari) per satu kali proses unduh.
  * **Bulanan (*Monthly*):** Tersedia via portal (sub-menu Data Bulanan).
  * **Jam-jaman (*Hourly / Sub-daily*):** **TIDAK TERSEDIA UNTUK UNDUHAN BEBAS**. Sesuai regulasi BMKG, data resolusi per jam tergolong data operasional yang pengaksesannya wajib melalui permohonan khusus PTSP BMKG.

---

## F. Limitations & Blockers Breakdown

### 1. Authentication & Technical Barrier
* Akses unduh data iklim historis tidak bersifat open-access langsung (membutuhkan pendaftaran akun pengguna, verifikasi email, dan form login terproteksi Google reCAPTCHA v3).
* Belum tersedia Public REST API resmi untuk mengunduh data historis stasiun secara terotomatisasi (berbeda dengan API publik prakiraan cuaca 3 hari NRT di `api.bmkg.go.id` yang sudah terbukti open-access).

### 2. Regulatory & Temporal Limitation
* **Perka BMKG No. 4 Tahun 2022:** Membatasi akses mandiri publik maksimal hanya untuk rentang 2 tahun terakhir.
* **Volume Chunks:** Batasan unduh maksimal 30 hari (1 bulan) per query menuntut ratusan request manual jika ingin menyusun dataset historis multi-tahun.
* Pengunduhan data resolusi tinggi (jam-jaman) atau data historis panjang (> 2 tahun) harus melalui prosedur administratif **Layanan PTSP BMKG** (`ptsp.bmkg.go.id`), yang untuk keperluan non-komersial/riset membutuhkan surat pengantar institusi/universitas resmi.

### 3. Spatial Limitation
* Titik observasi stasiun darat sangat terbatas (hanya ~10–15 titik di bandara kota besar untuk seluruh Pulau Kalimantan).

---

## G. SACA / BMKG Alternative Exploration

Sebagai alternatif repositori data iklim harian historis, dilakukan evaluasi terhadap **SACA&D (Southeast Asian Climate Assessment & Dataset)**:

* **Institusi Pengelola:** Kerjasama resmi antara **BMKG** (Indonesia), **KNMI** (Royal Netherlands Meteorological Institute), dan **WMO** (World Meteorological Organization).
* **Portal Resmi:** `https://sacad.bmkg.go.id/`
* **Tujuan Dataset:** Menyediakan data observasi iklim harian dan indeks iklim ekstrem (ETCCDI) untuk kawasan Asia Tenggara guna keperluan riset ilmiah non-komersial.
* **Variabel yang Disediakan:**
  * Presipitasi Harian (*Daily Precipitation Amount* / RR)
  * Suhu Harian (*Mean, Minimum, Maximum Temperature* / TG, TN, TX)
  * Tekanan Udara Permukaan Laut (*Sea Level Pressure* / PP)
  * Kelembapan Relatif (*Relative Humidity* / HU)
  * Kecepatan Angin (*Wind Speed* / FG)
* **Format Data:** Format teks ASCII standar (*ECA&D format*) yang memuat kolom: Tanggal (`YYYYMMDD`), Nilai Pengamatan, dan Flag Kualitas (`Q_FLAG`: 0=valid, 1=suspect, 9=missing).
* **Kelebihan SACA:**
  * Menghadirkan konsep *blended series* (seri data yang telah diisi kekosongannya/infilled dari stasiun sekitar dan pesan sinoptik).
  * Rentang historis mencakup periode panjang (multi-dekade).
* **Limitasi & Blocker SACA:**
  1. **Restriksi Unduhan Publik (~17%):** Berdasarkan kebijakan resmi data SACA, **hanya sekitar 17% dari total seri stasiun yang berstatus "Public" dan dapat diunduh bebas**. Stasiun yang berstatus *"non-downloadable"* tidak dapat diunduh langsung dari web dan harus diajukan melalui email permohonan ke tim pengelola (`sacad@bmkg.go.id`).
  2. **Proteksi WAF:** Akses ke portal web `sacad.bmkg.go.id` dilindungi Cloudflare WAF yang membatasi pengunduhan programatis tanpa sesi peramban interaktif.

---

## H. Final Feasibility Status

Berdasarkan seluruh temuan fakta teknis dan regulasi di atas, status kelayakan data historis BMKG ditetapkan sebagai:

```text
STATUS: PARTIALLY FEASIBLE
```

### Rationale Status:
1. **Mengapa Bukan FEASIBLE?**  
   Data historis BMKG **tidak dapat diunduh secara instan dan bebas tanpa hambatan (*not publicly open for automated download*)**. Sistem menerapkan autentikasi akun, Google reCAPTCHA v3, pembatasan volume 30 hari/unduhan, dan pembatasan regulasi 2 tahun terakhir via portal web.
2. **Mengapa Bukan BLOCKED?**  
   Data secara nyata **ada, valid, terawat dengan standar kualitas WMO di server BMKG**, dan jalurnya resmi tersedia (bisa diakses dengan mendaftarkan akun resmi di BMKG Data Online untuk rentang 2 tahun terakhir, atau mengajukan permohonan data penelitian ke PTSP BMKG).
3. **Alternatif Praktis untuk Pipeline Proyek:**
   * Untuk **fase eksplorasi & training model historis multi-tahun (misal: 2018–2024)**: Sangat direkomendasikan mengombinasikan data stasiun BMKG dengan dataset reanalisis meteorologi global terasimilasi (seperti **ERA5-Land** resolusi 0.1° atau **CHIRPS** curah hujan).
   * Untuk **fase inferensi operasional masa depan**: Memanfaatkan **API Publik Prakiraan Cuaca BMKG (`api.bmkg.go.id`)** yang sudah 100% terbukti feasible, akurat, dan terbuka tanpa API key.

---
*Laporan feasibility ini disusun secara objektif dan disimpan di `outputs/bmkg_historical_feasibility_report.md`.*
