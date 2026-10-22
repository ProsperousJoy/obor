import re

with open("outputs/ketersediaandata.html", "r", encoding="utf-8", errors="ignore") as f:
    html = f.read()

# 1. Extract all parameters
param_select = re.search(r'<select[^>]*id=["\']parameter["\'][^>]*>(.*?)</select>', html, re.DOTALL)
if param_select:
    params = re.findall(r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>', param_select.group(1))
    print("=== PARAMETERS IN BMKG DATA ONLINE ===")
    for val, text in params:
        if val:
            print(f"  {val:<15}: {text.strip()}")

# 2. Extract all provinces
prov_select = re.search(r'<select[^>]*id=["\']provinsi["\'][^>]*>(.*?)</select>', html, re.DOTALL)
kalimantan_prov_ids = {}
if prov_select:
    provs = re.findall(r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>', prov_select.group(1))
    print("\n=== PROVINCES (KALIMANTAN FILTER) ===")
    for val, text in provs:
        if val != '0':
            if 'kalimantan' in text.lower():
                print(f"  ID {val:<3}: {text.strip()}")
                kalimantan_prov_ids[val] = text.strip()

# 3. Extract all stations
station_select = re.search(r'<select[^>]*id=["\']station_id["\'][^>]*>(.*?)</select>', html, re.DOTALL)
if station_select:
    stations = re.findall(r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>', station_select.group(1))
    print(f"\n=== TOTAL STATIONS LISTED: {len(stations)} ===")
    print("--- Kalimantan Stations found by name: ---")
    kali_keywords = ['pontianak', 'supadio', 'palangkaraya', 'tjilik', 'banjarmasin', 'syamsudin', 'samarinda', 'pranoto', 'balikpapan', 'sepinggan', 'tarakan', 'juwata', 'sambas', 'sintang', 'ketapang', 'pangkalan bun', 'sampit', 'buntok', 'muara teweh', 'kotabaru', 'tanjung selor', 'nunukan', 'berau', 'paloh', 'nanga pinoh', 'putussibau']
    kali_stations = []
    for sid, sname in stations:
        if sid:
            s_clean = sname.strip()
            if any(k in s_clean.lower() for k in kali_keywords):
                print(f"  Station ID: {sid:<6} | Name: {s_clean}")
                kali_stations.append((sid, s_clean))
    print(f"Total Kalimantan stations identified: {len(kali_stations)}")

# 4. Check how the table is loaded (AJAX endpoint)
print("\n=== AJAX / DATA-FETCHING SCRIPTS IN HTML ===")
ajax_calls = re.findall(r'\$\.ajax\(\{[^}]*\}', html, re.DOTALL)
for a in ajax_calls:
    print("---------------------------------------------")
    lines = [l.strip() for l in a.split('\n') if l.strip()]
    for l in lines[:10]:
        print("  ", l)
