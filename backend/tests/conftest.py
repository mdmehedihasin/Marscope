import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
if not (ROOT / "data/fixtures/megt_fixture.lbl").exists():
    subprocess.run([sys.executable, str(ROOT / "scripts/make_fixture.py")], check=True)
if not (ROOT / "data/processed/jezero/manifest.json").exists():
    subprocess.run([sys.executable, str(ROOT / "scripts/build_region.py")], check=True)
