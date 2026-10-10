#!/usr/bin/env python3
"""Download the official MOLA MEGDR 128 px/deg tiles that contain Jezero from the PDS Geosciences Node.

  python scripts/fetch_mola.py            # topography (~130 MB) + shot counts (~130 MB)
  python scripts/fetch_mola.py --topo-only

Files land in data/raw/. Each download is checked against the size the label implies.
Needs internet access to pds-geosciences.wustl.edu (only for this step; the demo runs offline afterwards).
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import MOLA_COUNT_TILE, MOLA_TOPO_TILE, PDS_MEG128, RAW  # noqa: E402
from app.ingestion.pds3 import parse_label  # noqa: E402

PDS3_FALLBACK = "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/"


def get(url, dest):
    print(f"  GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "MARSCOPE-prototype/0.1 (education)"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        t0 = time.time()
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            done += len(b)
            if total:
                print(
                    f"\r    {done/1e6:7.1f} / {total/1e6:.1f} MB  ({done/1e6/max(time.time()-t0,1e-3):.1f} MB/s)",
                    end="",
                )
    print()


def fetch(tile):
    RAW.mkdir(parents=True, exist_ok=True)
    for base in (PDS_MEG128, PDS3_FALLBACK):
        try:
            lbl, img = RAW / f"{tile}.lbl", RAW / f"{tile}.img"
            get(base + tile + ".lbl", lbl)
            lab = parse_label(lbl.read_text(errors="replace"))
            im = lab["IMAGE"]
            expect = int(im["LINES"]) * int(im["LINE_SAMPLES"]) * int(im["SAMPLE_BITS"]) // 8
            if img.exists() and img.stat().st_size >= expect:
                print("  image already present, size OK")
                return base
            get(base + tile + ".img", img)
            if img.stat().st_size < expect:
                raise IOError(f"truncated: {img.stat().st_size} < {expect}")
            return base
        except Exception as e:  # try the PDS3 mirror path next
            print(f"  ! {base}: {e}")
    raise SystemExit(f"Could not download {tile}. Check internet access to pds-geosciences.wustl.edu.")


if __name__ == "__main__":
    tiles = [MOLA_TOPO_TILE] + ([] if "--topo-only" in sys.argv else [MOLA_COUNT_TILE])
    log = {}
    for t in tiles:
        print(f"[{t}]")
        log[t] = {"source": fetch(t) + t, "retrieved": time.strftime("%Y-%m-%d")}
    (RAW / "retrieval_log.json").write_text(json.dumps(log, indent=2))
    print("Done. Next: python scripts/build_region.py")
