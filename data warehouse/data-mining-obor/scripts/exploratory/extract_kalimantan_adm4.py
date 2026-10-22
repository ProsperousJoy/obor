import urllib.request
import re

url = "https://raw.githubusercontent.com/cahyadsn/wilayah/master/db/wilayah.sql"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

print("Downloading part of wilayah.sql...")
with urllib.request.urlopen(req, timeout=20) as resp:
    content = resp.read().decode("utf-8", errors="ignore")

print(f"Total SQL length: {len(content):,} characters")

# Format in wilayah.sql: ('61.71.01.1001', 'BENUA MELAYU DARAT') or ('61.71.01.1001','...')
pattern = r"\('(6[1-5]\.\d{2}\.\d{2}\.\d{4})',\s*'([^']+)'\)"
matches = re.findall(pattern, content)
print(f"Found {len(matches):,} Kalimantan kelurahan/desa records!")

by_prov = {}
for code, name in matches:
    prov = code[:2]
    by_prov.setdefault(prov, []).append((code, name))

prov_names = {
    "61": "Kalimantan Barat",
    "62": "Kalimantan Tengah",
    "63": "Kalimantan Selatan",
    "64": "Kalimantan Timur",
    "65": "Kalimantan Utara"
}

for p, items in sorted(by_prov.items()):
    pname = prov_names.get(p, p)
    print(f"\n{pname} ({p}) -> {len(items):,} desa/kelurahan")
    for code, name in items[:5]:
        print(f"  {code}: {name}")
