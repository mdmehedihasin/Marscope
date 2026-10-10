#!/usr/bin/env python3
"""Freeze the Demo Mission into frontend/public/demo/ so the UI works with no backend and no internet.
Every value is a real API response from the local backend (same code path), not hand-written."""

import json
import shutil
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.api.asgi_client import Client, available_apps  # noqa: E402  (in-process; no httpx, no sockets)
from app.config import PROCESSED, REGION  # noqa: E402

name, app = available_apps()[0]
c = Client(app)
out = ROOT / "frontend" / "public" / "demo"
(out / "layers").mkdir(parents=True, exist_ok=True)
get = {
    p: c.get(p).json()
    for p in [
        "/api/metadata",
        "/api/layers",
        "/api/science-targets",
        "/api/regions",
        "/api/sources",
        "/api/overlays",
        "/api/credits",
    ]
}
routes = c.post("/api/routes/compare", json={}).json()["routes"]
get["/api/routes/compare"] = {"routes": routes}
ev = {
    r["route_id"]: {
        s["id"]: c.get(f"/api/routes/{r['route_id']}/evidence", params={"segment": s["id"]}).json()
        for s in r["segments"]
    }
    for r in routes
}
briefs = {r["route_id"]: c.post("/api/crew-brief", json={"route_id": r["route_id"]}).json() for r in routes}
snap = {
    "default_start": routes[0]["start"],
    "default_dest": routes[0]["dest"],
    "default_grid": routes[0]["grid"]["level"],
    "server": name,
    "get": get,
    "evidence": ev,
    "briefs": briefs,
    "metadata": get["/api/metadata"],
}
(out / "snapshot.json").write_text(json.dumps(snap))
for old in (out / "layers").glob("*.png"):
    old.unlink()
for p in (PROCESSED / REGION["id"] / "layers").glob("*.png"):
    shutil.copy(p, out / "layers" / p.name)
dist_demo = ROOT / "frontend" / "dist" / "demo"
if dist_demo.parent.exists():  # keep the shipped UI's offline fallback in step (no rebuild needed)
    shutil.rmtree(dist_demo, ignore_errors=True)
    shutil.copytree(out, dist_demo)
print(
    f"snapshot ({name} server, {(out / 'snapshot.json').stat().st_size/1e6:.2f} MB): {len(routes)} routes, {sum(len(v) for v in ev.values())} evidence records, data_mode={get['/api/metadata']['data_mode']}"
)
