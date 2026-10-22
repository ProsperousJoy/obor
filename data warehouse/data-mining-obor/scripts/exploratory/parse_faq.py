import re

with open("outputs/dataonline_faq.html", "r", encoding="utf-8", errors="ignore") as f:
    c = f.read()

# Look for accordion, faq questions and answers
questions = re.findall(r'<div[^>]*class=["\'][^"\']*accordion[^"\']*["\'][^>]*>(.*?)</div>\s*</div>', c, re.DOTALL)
print(f"Found {len(questions)} accordion blocks")

# Or search all headers/buttons inside accordion
items = re.findall(r'<(?:button|h\d|a)[^>]*class=["\'][^"\']*(?:accordion|faq|collapsed)[^"\']*["\'][^>]*>(.*?)</(?:button|h\d|a)>', c, re.DOTALL | re.I)
print(f"Found {len(items)} FAQ titles:")
for it in items:
    clean = re.sub(r'<[^>]+>', '', it).strip()
    if clean:
        print("  Q:", clean)

# Also extract all text paragraphs that explain data access rules
paras = re.findall(r'<p[^>]*>(.*?)</p>', c, re.DOTALL)
print(f"\nSample explanatory paragraphs:")
for p in paras:
    clean = re.sub(r'<[^>]+>', '', p).strip()
    if any(k in clean.lower() for k in ["data", "unduh", "download", "hari", "bulan", "format", "ptsp", "gratis", "bayar", "tarif", "harian"]):
        print("  -", clean[:150])
