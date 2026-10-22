from html.parser import HTMLParser
import re

with open("outputs/dataonline_faq.html", "r", encoding="utf-8", errors="ignore") as f:
    c = f.read()

# Pattern for accordion items
items = re.findall(r'<div class="card mb-4 shadow-sm border-0">(.*?)</div>\s*</div>\s*</div>', c, re.DOTALL)
if not items:
    # Alternative card pattern
    items = re.findall(r'<div class="card[^"]*">(.*?)</div>\s*</div>', c, re.DOTALL)

print(f"Extracting Q&A from FAQ (total length: {len(c):,} chars)...")

# Regex to find questions and corresponding bodies
qa_pairs = re.findall(r'<button[^>]*class="[^"]*accordion-button[^"]*"[^>]*>(.*?)</button>.*?<div class="accordion-body[^"]*">(.*?)</div>', c, re.DOTALL)
print(f"Found {len(qa_pairs)} Q&A pairs:")

target_keywords = ["download", "tahun", "bulan", "rentang", "parameter", "registrasi", "ptsp", "tarif"]

for q, a in qa_pairs:
    clean_q = re.sub(r'<[^>]+>', '', q).strip()
    clean_a = re.sub(r'<[^>]+>', '', a).strip()
    clean_a = re.sub(r'\s+', ' ', clean_a)
    if any(k in clean_q.lower() for k in target_keywords):
        print("\n" + "="*80)
        print("QUESTION:", clean_q)
        print("ANSWER  :", clean_a)
