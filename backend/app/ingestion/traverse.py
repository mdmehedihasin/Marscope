"""Perseverance path slot.

REAL path: only if a local copy exists (data/raw/m20/M20_traverse.json and/or M20_waypoints.json, the file names
of the NASA Mars 2020 location-map endpoints listed in docs/DATA.md). Read as standard GeoJSON geometry only.
No property names are assumed: a sol range is shown only if PATH_SOL_PROPERTY in config.py is set by a person who
has inspected the real file.

ILLUSTRATIVE path: when no real file exists, a deterministic schematic line is generated for interface testing.
It is SYNTHETIC, never called "actual path", carries no rover metrics, and deliberately does not start at the
landing site.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..geospatial.terrain import haversine_m
from .pds3 import DataError

BUTLER_REF = (18.4447, 77.4508)  # Octavia E. Butler Landing (same value as data/targets/jezero_targets.json)


def _lines_from_geojson(doc) -> list[list[tuple[float, float]]]:
    """Return a list of polylines as (x, y) tuples exactly as stored (no convention assumed yet)."""
    feats = doc.get("features") if isinstance(doc, dict) and doc.get("type") == "FeatureCollection" else [doc]
    out = []
    for f in feats or []:
        geom = f.get("geometry") if isinstance(f, dict) and f.get("type") == "Feature" else f
        if not isinstance(geom, dict):
            continue
        t, c = geom.get("type"), geom.get("coordinates")
        if t == "LineString":
            out.append([(float(p[0]), float(p[1])) for p in c])
        elif t == "MultiLineString":
            out.extend([[(float(p[0]), float(p[1])) for p in part] for part in c])
        elif t == "Point":
            out.append([(float(c[0]), float(c[1]))])
    return out


CONVENTIONS = {
    "geojson_lon_lat_east": lambda x, y: (y, x),
    "geojson_lon_lat_east_360": lambda x, y: (y, x % 360.0),
    "geojson_lon_lat_west_positive": lambda x, y: (y, (360.0 - x) % 360.0),
    "swapped_lat_lon_east": lambda x, y: (x, y),
}


def detect_convention(points: list[tuple[float, float]], radius_m: float, ref=BUTLER_REF, tol_km: float = 5.0) -> dict:
    """Try plausible coordinate conventions; pick the one whose nearest vertex is closest to the landing reference.
    Reports the distance so a person can judge it. Raises DataError if none is within tol_km."""
    best = None
    for name, fn in CONVENTIONS.items():
        ll = np.array([fn(x, y) for x, y in points])
        if not (np.all(np.abs(ll[:, 0]) <= 90)):
            continue
        d = haversine_m(ll[:, 0], ll[:, 1], ref[0], ref[1], radius_m)
        k = int(np.argmin(d))
        cand = {
            "convention": name,
            "nearest_to_reference_km": round(float(d[k]) / 1000, 3),
            "nearest_index": k,
            "first_vertex_to_reference_km": round(float(d[0]) / 1000, 3),
        }
        if best is None or cand["nearest_to_reference_km"] < best["nearest_to_reference_km"]:
            best = cand
    if best is None or best["nearest_to_reference_km"] > tol_km:
        raise DataError(
            "Path file coordinates do not match the landing-site reference under any known convention — check the file"
        )
    return best


def in_region_share(lat, lon, bounds, radius_m) -> float:
    """Length fraction of a polyline whose segment midpoints lie inside the region bounds."""
    lat, lon = np.asarray(lat), np.asarray(lon)
    if len(lat) < 2:
        return float(
            (
                (lat >= bounds["lat_min"])
                & (lat <= bounds["lat_max"])
                & (lon >= bounds["lon_min"])
                & (lon <= bounds["lon_max"])
            ).mean()
        )
    seg = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:], radius_m)
    mla, mlo = 0.5 * (lat[:-1] + lat[1:]), 0.5 * (lon[:-1] + lon[1:])
    inside = (
        (mla >= bounds["lat_min"])
        & (mla <= bounds["lat_max"])
        & (mlo >= bounds["lon_min"])
        & (mlo <= bounds["lon_max"])
    )
    return float(seg[inside].sum() / max(seg.sum(), 1e-9))


def sol_range(doc, key: str | None):
    """Min/max of a numeric feature property named `key` — only when a person has set the key. Else None."""
    if not key or not isinstance(doc, dict):
        return None
    vals = []
    for f in doc.get("features") or []:
        v = (f.get("properties") or {}).get(key) if isinstance(f, dict) else None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals.append(v)
    return [min(vals), max(vals)] if vals else None


def load_real_path(path: Path, radius_m: float, bounds: dict, sol_key: str | None = None) -> dict:
    doc = json.loads(Path(path).read_text())
    lines = _lines_from_geojson(doc)
    pts = [p for ln in lines for p in ln]
    if not pts:
        raise DataError(f"{Path(path).name}: no LineString/Point geometry found")
    conv = detect_convention(pts, radius_m)
    fn = CONVENTIONS[conv["convention"]]
    ll_lines = [[fn(x, y) for x, y in ln] for ln in lines]
    flat = np.array([p for ln in ll_lines for p in ln])
    share = in_region_share(flat[:, 0], flat[:, 1], bounds, radius_m)
    return {
        "lines": [[[round(lo, 6), round(la, 6)] for la, lo in ln] for ln in ll_lines],
        "convention": conv,
        "in_region_share": round(share, 3),
        "vertices": int(len(flat)),
        "sol_range": sol_range(doc, sol_key),
    }


def illustrative_path(bounds: dict, n: int = 60) -> list[list[float]]:
    """Deterministic schematic wave across the northern part of the map. NOT rover data. Does not touch the
    landing site (it stays north of 18.7°N while the landing reference is at 18.4447°N)."""
    lo = np.linspace(bounds["lon_min"] + 0.12, bounds["lon_max"] - 0.12, n)
    la = bounds["lat_max"] - 0.14 + 0.04 * np.sin(np.linspace(0, 3 * np.pi, n))
    return [[round(float(a), 5), round(float(b), 5)] for a, b in zip(lo, la)]
