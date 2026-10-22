import urllib.request
import urllib.parse
import json
import re

with open("outputs/ketersediaandata.html", "r", encoding="utf-8", errors="ignore") as f:
    html = f.read()

# Extract CSRF token if present
csrf_match = re.search(r'name=["\']_token["\'][^>]*value=["\']([^"\']+)["\']', html)
csrf_meta = re.search(r'name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)["\']', html)
csrf_token = csrf_match.group(1) if csrf_match else (csrf_meta.group(1) if csrf_meta else None)
print("CSRF token found:", csrf_token)

# Representative stations in Kalimantan
# 1. Kalbar: Stasiun Meteorologi Supadio (96581)
# 2. Kalteng: Stasiun Meteorologi Tjilik Riwut (96655)
# 3. Kalsel: Stasiun Meteorologi Syamsudin Noor (96685)
# 4. Kaltim: Stasiun Meteorologi SAMS Sepinggan Balikpapan (96633)
# 5. Kaltara: Stasiun Meteorologi Juwata Tarakan (96509)

stations_to_test = [
    {"prov": "Kalimantan Barat", "station_id": "96581", "name": "Stasiun Meteorologi Supadio"},
    {"prov": "Kalimantan Tengah", "station_id": "96655", "name": "Stasiun Meteorologi Tjilik Riwut"},
    {"prov": "Kalimantan Selatan", "station_id": "96685", "name": "Stasiun Meteorologi Syamsudin Noor"},
    {"prov": "Kalimantan Timur", "station_id": "96633", "name": "Stasiun Meteorologi SAMS Sepinggan"},
    {"prov": "Kalimantan Utara", "station_id": "96509", "name": "Stasiun Meteorologi Juwata Tarakan"}
]

params_to_test = [
    "temp_avg", "temp_max", "temp_min", "rainfall",
    "hum_avg", "sunshine", "wind_avg", "wind_speed",
    "wind_dir_car", "wind_dir"
]

print("\nTesting process-ketersediaan-data endpoint...")
url = "https://dataonline.bmkg.go.id/process-ketersediaan-data"

# Test for year 2024 and 2023
for st in stations_to_test:
    form_data = {
        "_token": csrf_token or "",
        "type": "mkg",
        "station_id": st["station_id"],
        "parameter": "rainfall",
        "tahun": "2024",
        "year": "2024"
    }
    data_bytes = urllib.parse.urlencode(form_data).encode("utf-8")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://dataonline.bmkg.go.id/ketersediaandata"
    }
    if csrf_token:
        headers["X-CSRF-TOKEN"] = csrf_token
        
    req = urllib.request.Request(url, data=data_bytes, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            res_json = json.loads(body)
            print(f"[OK] {st['prov']} - {st['name']} ({st['station_id']})")
            print("     Response keys:", list(res_json.keys()))
            if "getStation" in res_json:
                gst = res_json["getStation"]
                print(f"     Station info: ID={gst.get('station_id')}, Name={gst.get('station_name')}, Regency={gst.get('regency_name')}, Province={gst.get('province_name')}")
            if "data" in res_json or "availability" in res_json or "getData" in res_json:
                d_key = "getData" if "getData" in res_json else ("data" if "data" in res_json else "availability")
                print(f"     Data summary ({d_key}):", str(res_json[d_key])[:200])
    except Exception as e:
        print(f"[ERR] {st['prov']} - {st['name']}: {e}")
