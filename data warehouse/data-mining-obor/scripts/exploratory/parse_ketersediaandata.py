from html.parser import HTMLParser
import re

with open("outputs/ketersediaandata.html", "r", encoding="utf-8", errors="ignore") as f:
    html = f.read()

# Extract title
title_m = re.search(r'<title>(.*?)</title>', html, re.I)
print("Title:", title_m.group(1) if title_m else "No title")

# Find select elements
select_matches = re.finditer(r'<select([^>]*)>(.*?)</select>', html, re.DOTALL | re.I)
print("\n--- <select> Elements ---")
for sm in select_matches:
    attrs = sm.group(1)
    body = sm.group(2)
    sid = re.search(r'id=["\'](.*?)["\']', attrs)
    sname = re.search(r'name=["\'](.*?)["\']', attrs)
    options = re.findall(r'<option[^>]*value=["\'](.*?)["\'][^>]*>(.*?)</option>', body, re.DOTALL)
    print(f"Select id='{sid.group(1) if sid else None}', name='{sname.group(1) if sname else None}', options count={len(options)}")
    for val, text in options[:8]:
        print(f"   value='{val}': {text.strip()}")

# Check tables or data containers
tables = soup.find_all("table")
print(f"\nFound {len(tables)} <table> elements")
for t in tables:
    tid = t.get("id") or t.get("class")
    print(f"  - Table: {tid}")

# Check script tags for javascript variables or endpoints
scripts = soup.find_all("script")
print(f"\nFound {len(scripts)} <script> elements")
for idx, sc in enumerate(scripts):
    text = sc.string or ""
    if any(k in text for k in ["ajax", "url", "stasiun", "ketersediaan", "DataTable"]):
        print(f"\n--- Script {idx} snippet ---")
        lines = [line.strip() for line in text.split("\n") if line.strip() and not line.strip().startswith("//")]
        for l in lines[:25]:
            print(" ", l)
