import urllib.request
import json

test_queries = [
    ("Pontianak (Kalbar)", "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=61.71.01.1001"),
    ("Palangka Raya (Kalteng)", "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=62.71.01.1001"),
    ("Banjarmasin (Kalsel)", "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=63.71.01.1001"),
    ("Balikpapan (Kaltim)", "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=64.71.01.1001"),
    ("Samarinda (Kaltim)", "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=64.72.01.1001"),
    ("Tarakan (Kaltara)", "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=65.71.01.1001"),
    ("Adm2 Kalbar", "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm2=61.71"),
    ("Adm1 Kalbar", "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm1=61"),
]

for name, url in test_queries:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            lok = data.get("lokasi", {})
            cuaca_data = data.get("data", [])
            print(f"[OK] {name}: {url}")
            if isinstance(lok, dict):
                print(f"     Provinsi: {lok.get('provinsi')}, Kota/Kab: {lok.get('kotkab')}, Kec: {lok.get('kecamatan')}, Desa: {lok.get('desa')}")
                print(f"     Coords: Lat={lok.get('lat')}, Lon={lok.get('lon')}, Timezone={lok.get('timezone')}")
            if cuaca_data and len(cuaca_data) > 0:
                cuaca_slots = cuaca_data[0].get("cuaca", [])
                total_slots = sum(len(day) for day in cuaca_slots)
                print(f"     Cuaca forecast slots: {total_slots} time steps (3 days, 3-hourly)")
                if cuaca_slots and len(cuaca_slots[0]) > 0:
                    sample_slot = cuaca_slots[0][0]
                    print(f"     Sample slot: datetime={sample_slot.get('datetime')}, t={sample_slot.get('t')} C, hu={sample_slot.get('hu')} %, tp={sample_slot.get('tp')} mm, ws={sample_slot.get('ws')}, wd={sample_slot.get('wd')}")
    except Exception as e:
        print(f"[ERR] {name}: {e}")
