# Panduan & Skrip Presentasi Data Warehouse Karhutla Kalimantan

Dokumen ini berisi panduan praktis presentasi singkat (5–7 menit) mengenai Data Warehouse Kebakaran Hutan Kalimantan (2021–2025).

---

## 📂 1. File yang Perlu Dibuka / Ditampilkan saat Presentasi

Siapkan file-file ini di VS Code atau editor kamu agar presentasi terlihat kredibel dan berbasis bukti:

1. **`config/ml_features.py`**
   * *Tampilkan saat menjelaskan kesiapan Machine Learning.*
   * Menunjukkan daftar 16 fitur resmi (`BASELINE_FEATURE_COLS`), pemisahan target (`TARGET_COLS`), dan formula kalibrasi probabilitas.
2. **`database/ml_views.sql` (baris 1–50 & baris 120–150)**
   * *Tampilkan saat menjelaskan anti-leakage.*
   * Menunjukkan query `vw_training_dataset` yang rapi dan fitur cuaca yang strictly diambil dari $T-1\text{ hari}$ (`- INTERVAL 1 DAY`).
3. **`outputs/validation/verify_remediation.py` atau terminal query cepat**
   * *Tampilkan saat menunjukkan statistik data.*
   * Menunjukkan row count 906.556 baris, rasio 1:3 seimbang, dan 0 sampel di laut.

---

## 🎙️ 2. Skrip Presentasi Singkat (5 Menit)

### Bagian 1: Latar Belakang & Tujuan (1 Menit)
* **File yang disorot:** `README.md` atau `config/settings.py`
* **Ucapkan:**
  > *"Halo semuanya. Di sini saya mempresentasikan Data Warehouse Prediksi Risiko Kebakaran Hutan di Kalimantan untuk periode 5 tahun penuh (2021–2025).*  
  > *Tujuan warehouse ini adalah menyatukan data multi-sensor satelit dan stasiun cuaca yang formatnya berbeda-beda ke dalam satu basis data analitik (OLAP) spasial beresolusi 0.02° (~2.2 km). Dengan warehouse ini, tim Data Science/ML bisa langsung melatih model tanpa perlu pusing membersihkan data mentah lagi."*

### Bagian 2: Sumber Data & Arsitektur (1.5 Menit)
* **File yang disorot:** Folder `data/warehouse/` (`wildfire.duckdb` & `parquet/`)
* **Ucapkan:**
  > *"Warehouse ini mengintegrasikan 4 sumber data utama:*
  > 1. *Titik api dan intensitas radiasi (FRP) dari satelit **NASA VIIRS**.*
  > 2. *Data cuaca harian dan kelembapan tanah dari **ECMWF ERA5-Land**.*
  > 3. *Suhu kecerahan inframerah dari satelit geostasioner **Himawari-8/9**.*
  > 4. *Prakiraan cuaca dari **BMKG**.*
  >
  > *Untuk teknologinya, kami menggunakan **DuckDB** dan **Apache Parquet**. Keduanya berbasis columnar storage yang sangat cepat untuk agregasi jutaan baris data spasial, tanpa butuh server database terpisah. Ukurannya sangat ringkas: total database 5 tahun hanya **~219 MB**."*

### Bagian 3: Integritas Data & Anti-Leakage (1.5 Menit)
* **File yang disorot:** `database/ml_views.sql`
* **Ucapkan:**
  > *"Yang paling krusial, warehouse ini telah diaudit dan bebas dari kebocoran data (data leakage):*
  > * Pertama, **Zero Temporal Leakage**: semua fitur cuaca dan riwayat api diambil dari masa lalu ($T-1\text{ hari}$), sedangkan target yang ditebak adalah 24 jam ke depan ($T \to T+24\text{h}$).*
  > * Kedua, **Real Land Masking**: kami memasang filter poligon daratan akurat sehingga dari total 331 ribu sel di batas wilayah, hanya 152 ribu sel daratan yang dipakai. Hasilnya: **nol sampel negatif yang jatuh di laut** dan anjungan gas lepas pantai berhasil disaring.*
  > * Ketiga, **Data Spasial Lengkap**: interpolasi cuaca IDW memastikan tidak ada nilai null pada daratan Kalimantan."*

### Bagian 4: Kesiapan Machine Learning & Integrasi Sistem Respons (1 Menit)
* **File yang disorot:** `config/ml_features.py` & tabel relasional respons
* **Ucapkan:**
  > *"Untuk kebutuhan hilir, warehouse ini menyajikan 2 layer output siap pakai:*
  > 1. * **Layer Prediksi (ML Ready)**: Kami menyusun tabel training spine sebanyak **906.556 baris** dengan pembagian temporal yang bersih (*Train: 2021–2023 [552k], Val: 2024 [186k], Test: 2025 [167k]*). Rekan tim yang mengerjakan model Machine Learning cukup query satu view: `vw_training_dataset`.*
  > 2. * **Layer Tanggap Darurat (Emergency Response Ready)**: Kami juga telah memodelkan data spasial operasional, meliputi 12 posko Manggala Agni (`dim_responder_hq`), 17 sumber air strategis (`dim_water_sources`), dan aset konservasi rentan (`dim_vulnerable_assets`) untuk dikonsumsi oleh modul penugasan damkar.*
  >
  > *Dengan demikian, data engineering dan warehouse ini sudah 100% tuntas dan siap mendukung seluruh pipeline tim."*

---

## ❓ 3. Antisipasi Pertanyaan Penguji / Dosen & Jawaban Kunci

### Q1: *"Kebakaran hutan kan baru heboh belakangan ini, kenapa harus narik data sampai 5 tahun ke belakang (2021–2025)?"*
* **Jawaban:**
  > *"Karena kebakaran hutan di Kalimantan sangat dipengaruhi oleh siklus iklim global ENSO. Tahun 2021–2022 adalah tahun basah (La Niña) di mana kebakaran minim, sedangkan tahun 2023 adalah kemarau ekstrem (El Niño) dengan ratusan ribu titik api. Jika model hanya dilatih pada 1 tahun terakhir, model akan 'buta iklim'. Rentang 5 tahun memastikan model belajar spektrum iklim lengkap dan memungkinkan kita melakukan evaluasi train-test berbasis tahun yang independen (Train 2021–2023, Test 2025)."*

---

### Q2: *"Bukankah karhutla itu mayoritas disengaja oleh manusia (bakar lahan)? Kenapa memodelkan cuaca & alam?"*
* **Jawaban:**
  > *"Betul, manusia memang menjadi sumber pemantik api (ignition source). Namun apakah api kecil tersebut akan padam sendiri dalam 5 menit atau meledak menjalar menjadi kebakaran hebat ribuan hektar, itu 100% ditentukan oleh faktor biofisik: kekeringan gambut, kelembapan udara, dan angin. Model kita memprediksi **tingkat kerentanan lahan (fire susceptibility)**, sehingga patroli satgas bisa diprioritaskan ke area yang paling mudah meledak jika ada percikan api."*

---

### Q3: *"Kenapa memakai DuckDB bukan PostgreSQL / MySQL?"*
* **Jawaban:**
  > *"PostgreSQL/MySQL dirancang untuk OLTP (transaksi baris per baris seperti web app). Sedangkan proyek kita adalah analitik data mining OLAP dengan jutaan titik spasial. DuckDB memproses data secara columnar vectorization, 10 hingga 50 kali lebih cepat untuk query agregasi spasial-temporal, dan berbentuk in-process file sehingga anggota tim lain bisa langsung pakai tanpa instal server database."*

---

### Q4: *"Kenapa rasio dataset 1 positif : 3 negatif, bukan memakai seluruh titik tanpa kebakaran?"*
* **Jawaban:**
  > *"Di dunia nyata, kebakaran hutan adalah peristiwa langka (rare event), di mana 99.9% sel tidak terbakar. Jika kita masukkan semua sel negatif tanpa sampling, model akan bias dan selalu menebak 'tidak ada api' (akurasi semu). Rasio stratified 1:3 adalah standar metodologi Presence-Background dalam pemodelan spasial kebakaran hutan, dan kami menyediakan fungsi log-odds recalibration di `config/ml_features.py` untuk mengembalikan probabilitas ke base-rate aslinya."*

---

### Q5: *"Bagaimana kalian menjamin tidak ada data leakage?"*
* **Jawaban:**
  > *"Kami mengaudit pipeline pada 2 level:  
  > 1. **Temporal**: Seluruh prediktor di-offset strictly $T-1\text{ hari}$ (misal prediksi jam 00:00 UTC hanya menggunakan cuaca dan histori yang sudah selesai tercatat kemarin).  
  > 2. **Target Window**: Target kebakaran dihitung murni dalam jendela $(T, T+24\text{ jam}]$ ke depan menggunakan tabel terpisah `fact_fire_targets_24h`."*

---

### Q6: *"Apakah kamu juga yang membuat model machine learning dan modul agent responsnya?"*
* **Jawaban:**
  > *"Fokus dan lingkup tanggung jawab saya adalah di **Data Engineering & Data Warehouse Architecture**. Peran saya adalah memastikan seluruh fondasi data—mulai dari integrasi satelit NASA FIRMS 5 tahun, data cuaca reanalisis, masking daratan poligon akurat, audit anti-leakage, hingga perancangan skema relasional dimensi dan fakta—tersedia secara valid, bersih, dan berkinerja tinggi dalam DuckDB dan Parquet. Rekan tim saya yang bertugas mengembangkan model ML dan modul agen respons dapat langsung mengonsumsi data warehouse yang telah saya bangun ini tanpa kendala."*
