#!/usr/bin/env python3
"""List which source files are present in data/raw/ (offline; never downloads anything).

python scripts/check_local_data.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import RAW  # noqa: E402
from app.ingestion.local_inventory import inventory  # noqa: E402

print(f"Looking in {RAW} (offline check, no network)\n")
for e in inventory(RAW):
    mark = "PRESENT" if e["present"] else "missing"
    print(f"[{mark:7s}] {e['name']}")
    print(f"           expected: {', '.join(e['expected'])}")
    for f in e["files"]:
        print(f"           found: {f['name']}  {f['bytes']} bytes  sha256 {f['sha256'] or '(not computed)'}")
    print(f"           {e['integration']}\n")
