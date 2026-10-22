# Himawari-9 AHI Pipeline — README

Pipeline untuk akuisisi dan preprocessing data **Himawari-9 AHI** dari AWS S3 NOAA,
sebagai salah satu sumber fitur untuk prediksi risiko kebakaran hutan di Kalimantan.

---

## Struktur Project

```
data-mining-borneo/
├── data/
│   ├── HS_H09_YYYYMMDD_HHMM_B07_FLDK_R20_S0510.DAT.bz2   # raw download
│   └── HS_H09_YYYYMMDD_HHMM_B07_FLDK_R20_S0510.DAT        # decompressed
├── outputs/
│   └── <date>_<time>_<band>_<segment>/
│       ├── <stem>_fullseg.png       # visualisasi full segment
│       ├── <stem>_borneo.png        # visualisasi Kalimantan subset
│       └── <stem>_borneo.nc         # NetCDF (data + lat/lon, ML-ready)
├── scripts/
│   ├── download_himawari.py         # download + decompress dari S3
│   ├── read_himawari.py             # baca HSD, return DataArray
│   ├── geolocate_himawari.py        # lat/lon grid, bounding box, overlap
│   ├── subset_himawari.py           # subset ke bbox + simpan NetCDF
│   ├── pipeline.py                  # entry point pipeline lengkap
│   └── README.md                    # (file ini)
├── explore_himawari.py              # explorasi one-shot (Step 1-7)
└── .venv/                           # Python virtual environment
```

---

## Cara Menjalankan Pipeline

### Aktivasi Environment

```bash
.venv\Scripts\activate
```

### Jalankan Pipeline Lengkap (untuk observasi baru)

```bash
python scripts/pipeline.py \
    --date 20260920 \
    --time 0000 \
    --band B07 \
    --segment S0510
```

**Parameter:**

| Parameter | Deskripsi | Contoh |
|---|---|---|
| `--date` | Tanggal observasi (YYYYMMDD) | `20260920` |
| `--time` | Waktu UTC (HHMM) | `0000`, `0010`, `0020` |
| `--band` | Band AHI | `B07`, `B13`, `B14` |
| `--segment` | Segmen full disk | `S0110` ... `S1010` |
| `--outdir` | Direktori data (default: `data`) | `data` |
| `--outputdir` | Direktori output (default: `outputs`) | `outputs` |
| `--no-download` | Skip download (file sudah ada) | |
| `--no-decompress` | Skip decompress (DAT sudah ada) | |

### Jalankan Pipeline Tanpa Download Ulang

```bash
python scripts/pipeline.py \
    --date 20260920 \
    --time 0000 \
    --band B07 \
    --segment S0510 \
    --no-download
```

### Gunakan Custom Bounding Box

```bash
python scripts/pipeline.py \
    --date 20260920 \
    --time 0000 \
    --band B07 \
    --segment S0510 \
    --lon-min 108 --lon-max 119 \
    --lat-min -5  --lat-max 7
```

---

## Sumber Data

| Atribut | Detail |
|---|---|
| **Bucket S3** | `s3://noaa-himawari9` |
| **Akses** | Public (anonymous, tanpa credentials) |
| **Path pattern** | `AHI-L1b-FLDK/{YYYY}/{MM}/{DD}/{HHMM}/` |
| **Format file** | HSD (Himawari Standard Data), `.DAT.bz2` |

---

## Informasi Band B07

| Atribut | Nilai |
|---|---|
| **Panjang gelombang** | 3.9 µm (SWIR) |
| **Kalibrasi** | Brightness Temperature |
| **Satuan** | Kelvin (K) |
| **Resolusi** | 2 km (2000 m) |
| **Rentang valid** | ~196 K – 340 K (tipikal Earth) |

> **Catatan:** B07 (3.9 µm) sensitif terhadap suhu permukaan dan hotspot kebakaran.
> Titik api aktif akan menunjukkan nilai brightness temperature yang jauh lebih tinggi
> dibanding area sekitarnya pada band ini.

---

## Segmen Full Disk Himawari-9

Satu observasi full disk terdiri dari **10 segmen** (S0110 – S1010).

| Segmen | Posisi Lintang (approx) |
|---|---|
| S0110 | Paling Utara |
| S0210 – S0410 | Utara |
| **S0510** | **Sekitar ekuator / Asia Tenggara** |
| S0610 – S0810 | Selatan |
| S0910 – S1010 | Paling Selatan |

Hasil verifikasi dari data aktual:
- **S0510** mencakup area sekitar **Lat 0–12°N, Lon ~95–155°E**
- Kalimantan (**Lat -5–7°N, Lon 108–119°E**) ter-cover sebagian oleh S0510

---

## Output NetCDF

File NetCDF yang dihasilkan (`*_borneo.nc`) berisi:

| Variable | Shape | Deskripsi |
|---|---|---|
| `B07` | (y, x) | Brightness Temperature [K] |
| `longitude` | (y, x) | Longitude grid [degrees_east] |
| `latitude` | (y, x) | Latitude grid [degrees_north] |

Cara membuka:

```python
import xarray as xr
ds = xr.open_dataset("outputs/.../..._borneo.nc")
print(ds)
print(ds["B07"].values.shape)
print(ds["latitude"].values)
```

---

## Roadmap Fitur Selanjutnya

- [ ] Download multi-segmen otomatis dan merge
- [ ] Support multi-band dalam satu run
- [ ] Thermal anomaly detection (FRP proxy)
- [ ] Temporal stacking (time series per pixel)
- [ ] Integrasi dengan VIIRS active fire, BMKG, GPM

---

## Dependensi

| Package | Versi | Kegunaan |
|---|---|---|
| `satpy` | 0.60.0 | Reader HSD, kalibrasi |
| `numpy` | 2.5.3 | Komputasi array |
| `xarray` | tersedia | Dataset multidimensi |
| `netCDF4` | tersedia | Simpan/baca NetCDF |
| `matplotlib` | 3.11.2 | Visualisasi |
| `pyresample` | tersedia | Geolocation / area definition |
| `pyproj` | 3.8.0 | Proyeksi koordinat |
| `boto3` | tersedia | Akses AWS S3 |
