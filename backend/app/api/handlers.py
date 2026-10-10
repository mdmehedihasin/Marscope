"""Framework-free API logic. Both servers call these functions:
  * app/main.py — FastAPI (primary; `pip install -r requirements.txt`)
  * app/lite.py — Starlette-only fallback (used when FastAPI is not installed, e.g. an offline machine)
Each handler takes plain Python values and returns JSON-ready dicts. Data problems raise DataError (HTTP 422);
unknown ids raise NotFound (HTTP 404)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..briefing.brief import build_brief, route_differences
from ..config import MODES, PIPELINE, ROUTING_GRID_DEFAULT
from ..ingestion.pds3 import DataError
from ..provenance.registry import CREDITS, STATUS
from ..store import get_store


class NotFound(Exception):
    pass


class Point(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-360, le=360)
    name: str | None = None


class RouteReq(BaseModel):
    start: Point | None = None
    dest: Point | None = None
    mode: str = "balanced"
    grid: str = ROUTING_GRID_DEFAULT


class BriefReq(BaseModel):
    route_id: str


def _ends(req: RouteReq):
    s, d = get_store().default_endpoints()
    return (req.start.model_dump() if req.start else s), (req.dest.model_dump() if req.dest else d)


def health():
    st = get_store()
    return {"ok": True, "data_mode": st.manifest["data_mode"]}


def regions():
    m = get_store().manifest
    return [
        {
            "id": m["region"]["id"],
            "name": m["region"]["name"],
            "why": m["region"]["why"],
            "bounds": m["region"]["bounds"],
            "data_mode": m["data_mode"],
        }
    ]


def layers():
    m = get_store().manifest
    return {"layers": [dict(l) | {"url": f"/layers/{l['png']}"} for l in m["layers"]], "unavailable": m["unavailable"]}


def layer(layer_id: str):
    for l in get_store().manifest["layers"]:
        if l["id"] == layer_id:
            return l | {"url": f"/layers/{l['png']}"}
    raise NotFound(f"No layer '{layer_id}' for this region")


def targets():
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [t["lon"], t["lat"]]}, "properties": t}
            for t in get_store().targets
        ],
    }


def route(req: RouteReq):
    s, d = _ends(req)
    return get_store().route(s, d, req.mode, req.grid)


def compare(req: RouteReq):
    s, d = _ends(req)
    st = get_store()
    routes = [st.route(s, d, m, req.grid) for m in MODES]
    return {"routes": routes, "differences": route_differences(routes)}


def get_route(route_id: str):
    r = get_store().routes.get(route_id)
    if not r:
        raise DataError("Route not found — generate it first")
    return r


def evidence(route_id: str, segment: str):
    return get_store().evidence(route_id, segment)


def cell(lat: float, lon: float):
    st = get_store()
    g = st.grid
    i, j = g.cell(lat, lon)
    c = None if g.counts is None else int(g.counts[i, j])
    ri, rj = st.routing.cell(lat, lon)
    return {
        "lat": round(float(g.lat[i]), 5),
        "lon": round(float(g.lon[j]), 5),
        "elev_m": round(float(g.z[i, j]), 1),
        "slope_deg": round(float(g.slope[i, j]), 2),
        "relief_m": round(float(g.relief[i, j]), 1),
        "T": round(float(g.T[i, j]), 3),
        "S": round(float(st.S[i, j]), 3),
        "mola_shots": c,
        "interpolated": (c == 0) if c is not None else None,
        "slope_deg_routing": round(float(st.routing.slope[ri, rj]), 2),
        "level": "native 1/128° source cell (slope_deg_routing: 1/512° interpolated grid)",
        "data_mode": st.manifest["data_mode"],
    }


def sources():
    m = get_store().manifest
    return {
        "layers": [l["provenance"] for l in m["layers"]],
        "targets": m["targets"],
        "unavailable": m["unavailable"],
        "overlays": [o["provenance"] for o in m.get("overlays", [])],
        "credits": CREDITS,
        "grids": m.get("grid_records", []),
        "inventory": m.get("local_inventory", []),
    }


def metadata():
    st = get_store()
    m = st.manifest
    return {
        "data_mode": m["data_mode"],
        "built": m["built"],
        "region": m["region"],
        "assumptions": m["assumptions"],
        "stats": m["stats"],
        "status_vocabulary": STATUS,
        "unavailable": m["unavailable"],
        "grids": {k: v | {"status": st.grid_status(k)} for k, v in st.level_info.items()},
        "slope_by_level": m.get("slope_by_level"),
        "disclosure": m.get("disclosure"),
        "pipeline": [{"stage": a, "sub": b, "status": c, "built": d, "next": e} for a, b, c, d, e in PIPELINE],
    }


def overlays():
    """Vector overlays (e.g. the Perseverance path slot). Each carries its own provenance and status."""
    return {"overlays": get_store().manifest.get("overlays", [])}


def credits():
    return {"credits": CREDITS}


def crew_brief(req: BriefReq):
    st = get_store()
    r = st.routes.get(req.route_id)
    if not r:
        raise DataError("Route not found — generate it first")
    comp = [
        x
        for x in st.routes.values()
        if x["start"] == r["start"] and x["dest"] == r["dest"] and x["grid"]["level"] == r["grid"]["level"]
    ]
    return build_brief(st, r, comp)
