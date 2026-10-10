#!/usr/bin/env python3
"""One command to run MARSCOPE:  python run.py
Builds the region if needed (real MOLA if present in data/raw, else the labelled synthetic fixture),
then serves the API and UI at http://localhost:8000. No internet needed: nothing is downloaded."""

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
py = sys.executable
if not (ROOT / "data/raw/megt44n045hb.lbl").exists() and not (ROOT / "data/fixtures/megt_fixture.lbl").exists():
    subprocess.run([py, str(ROOT / "scripts/make_fixture.py")], check=True)
manifest = ROOT / "data/processed/jezero/manifest.json"
real_raw = (ROOT / "data/raw/megt44n045hb.lbl").exists()
stale = not manifest.exists() or (real_raw and '"NASA_PDS"' not in manifest.read_text())
if stale or "--rebuild" in sys.argv:
    subprocess.run([py, str(ROOT / "scripts/build_region.py")], check=True)
    subprocess.run([py, str(ROOT / "scripts/build_snapshot.py")], check=True)
port = int(os.environ.get("MARSCOPE_PORT", "8000"))
if not (ROOT / "frontend/dist/index.html").exists():
    print("frontend/dist missing: run `npm install && npm run build` in frontend/ (Node 18+).")
threading.Timer(2.0, lambda: webbrowser.open(f"http://localhost:{port}/")).start()
os.chdir(ROOT / "backend")
try:  # FastAPI is the primary server; the Starlette-only fallback serves the identical API when FastAPI is missing.
    import fastapi  # noqa: F401

    target = "app.main:app"
except ImportError:
    target = "app.lite:app"
    print("FastAPI not installed - using the Starlette fallback server (same API).")
subprocess.run([py, "-m", "uvicorn", target, "--port", str(port)])
