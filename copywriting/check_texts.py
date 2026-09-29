"""Output-level check for the copywriting samples: each body stays inside its brief's length envelope
and contains none of the stock phrases the brief forbids. Run: python check_texts.py (exit 0 = pass).
The self-test at the end feeds a text with a forbidden phrase and must see it rejected."""
import re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENVELOPE = {"01-статья.md": (3000, 4000), "02-пост.md": (600, 900), "03-оффер.md": (0, 600)}
FORBIDDEN = re.compile(r"в современном мире|не секрет|играет важную роль|давайте разбер|таким образом", re.I)

def body(text):
    return text.split("\n---\n", 1)[1].strip() if "\n---\n" in text else text.strip()

def problems(name, text):
    out = []
    lo, hi = ENVELOPE[name]
    n = len(body(text))
    if not lo <= n <= hi:
        out.append(f"{name}: {n} chars, expected {lo}-{hi}")
    if FORBIDDEN.search(body(text)):
        out.append(f"{name}: forbidden stock phrase")
    return out

fails = []
for name in ENVELOPE:
    text = (HERE / name).read_text(encoding="utf-8")
    fails += problems(name, text)
    print(f"{name}: {len(body(text))} chars")

bad = "brief\n---\n" + "Не секрет, что оффер важен. " * 5
if not problems("03-оффер.md", bad):
    fails.append("self-test: a forbidden phrase was not rejected")

print("FAIL: " + "; ".join(fails) if fails else "ALL PASSED")
sys.exit(1 if fails else 0)
