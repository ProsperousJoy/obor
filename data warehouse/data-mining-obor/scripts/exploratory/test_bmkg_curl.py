import subprocess
import json

codes = [
    ("Kalbar",  "61.01.01.2001", "Sambas"),
    ("Kalteng", "62.01.01.1011", "Kumai / Kotawaringin Barat"),
    ("Kalsel",  "63.01.01.2001", "Takisung / Tanah Laut"),
    ("Kaltim",  "64.01.01.2009", "Batu Sopang / Paser"),
    ("Kaltara", "65.01.01.1001", "Tanjung Palas / Bulungan")
]

for prov, code, label in codes:
    url = f"https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={code}"
    cmd = ["curl.exe", "-s", "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", url]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(res.stdout)
        lok = data.get("lokasi", {})
        if "provinsi" in lok:
            print(f"[OK] {prov} ({code}): {lok.get('desa')}, {lok.get('kecamatan')}, {lok.get('kotkab')}, {lok.get('provinsi')}")
            print(f"     Lat={lok.get('lat')}, Lon={lok.get('lon')}, Timezone={lok.get('timezone')}")
        else:
            print(f"[FAIL] {prov} ({code}): {data}")
    except Exception as e:
        print(f"[ERR] {prov} ({code}): {e} | Raw: {res.stdout[:100]}")
