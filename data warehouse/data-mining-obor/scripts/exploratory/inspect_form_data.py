import re

with open("outputs/ketersediaan_session.html", "r", encoding="utf-8", errors="ignore") as f:
    c = f.read()

idx = c.find('id="formKetersediaanData"')
if idx != -1:
    end_idx = c.find('</form>', idx)
    form_html = c[idx:end_idx]
    print("=== FORM KETERSEDIAAN DATA INPUTS ===")
    inputs = re.findall(r'<input[^>]+>', form_html)
    for inp in inputs:
        print(" ", inp)
    selects = re.findall(r'<select[^>]+>', form_html)
    for sel in selects:
        print(" ", sel)

# Look for download or data_iklim URLs in the entire site HTML
print("\n=== DATA IKLIM / DOWNLOAD ROUTES IN HTML ===")
routes = re.findall(r'href=["\']([^"\']+)["\']', c)
for r in set(routes):
    if any(k in r.lower() for k in ["data", "iklim", "download", "export", "login", "register", "ptsp"]):
        print("  ", r)
