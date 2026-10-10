"""Loads the processed region once and computes/caches routes. All route numbers come from here.

Besides the native source grid, the store builds two finer grids by interpolation (see geospatial/levels.py):
a 1/512 deg routing grid (route search) and a 1/1024 deg analysis grid (slope evidence along the chosen path).
They are rebuilt from grid.npz at start-up (<1 s), so no large raster is shipped.
"""

from __future__ import annotations

import hashlib
import json
import time
from functools import lru_cache

import numpy as np

from .config import GRID_CHOICES, MODES, PROCESSED, REGION, ROUTING_GRID_DEFAULT, SCIENCE_SIGMA_M, TERRAIN
from .geospatial.levels import LEVELS, build_level, level_description
from .ingestion.pds3 import DataError
from .routing.engine import Grid, analyse, astar, cell_cost, sample_slope_along, science_field, shortest_path


class Store:
    def __init__(self, region_id: str = REGION["id"]):
        d = PROCESSED / region_id
        if not (d / "manifest.json").exists():
            raise DataError("No processed region found. Run: python scripts/build_region.py")
        self.dir = d
        self.manifest = json.loads((d / "manifest.json").read_text())
        g = np.load(d / "grid.npz")
        counts = g["counts"] if (g["counts"] >= 0).any() else None
        lat_max, lon_west, ppd, R = float(g["lat_max"]), float(g["lon_west"]), float(g["ppd"]), float(g["radius_m"])
        self.grid = Grid(g["z"], g["slope"], g["relief"], counts, lat_max, lon_west, ppd, R)  # native (baseline)
        t0 = time.perf_counter()
        r = build_level(g["z"], counts, lat_max, lon_west, ppd, R, LEVELS["routing"])
        self.routing = Grid(r["z"], r["slope"], r["relief"], r["counts"], lat_max, lon_west, r["ppd"], R)
        a = build_level(g["z"], counts, lat_max, lon_west, ppd, R, LEVELS["analysis"], with_relief=False)
        self.analysis = Grid(a["z"], a["slope"], np.zeros_like(a["z"]), a["counts"], lat_max, lon_west, a["ppd"], R)
        self.levels_build_ms = round(1000 * (time.perf_counter() - t0), 1)
        self.grids = {"native": self.grid, "routing": self.routing}
        self.targets = self.manifest["targets"]
        self.S = science_field(self.grid, self.targets)
        self.S_by = {"native": self.S, "routing": science_field(self.routing, self.targets)}
        lat_mid = 0.5 * (self.grid.lat[0] + self.grid.lat[-1])
        self.level_info = {k: level_description(k, f, ppd, R, lat_mid) for k, f in LEVELS.items()}
        self.routes: dict[str, dict] = {}

    @property
    def synthetic(self):
        return self.manifest["data_mode"] != "NASA_PDS"

    def grid_status(self, level: str) -> str:
        if self.synthetic:
            return "SYNTHETIC"
        return "VERIFIED" if level == "native" else "APPROXIMATE"

    def default_endpoints(self):
        s = next(t for t in self.targets if t["role"] == "start")
        d = next(t for t in self.targets if t["role"] == "destination")
        return {"lat": s["lat"], "lon": s["lon"], "name": s["name"]}, {
            "lat": d["lat"],
            "lon": d["lon"],
            "name": d["name"],
        }

    def route(self, start: dict, dest: dict, mode: str, grid: str | None = None) -> dict:
        if mode not in MODES:
            raise DataError(f"Unknown route mode '{mode}'. Use one of: {', '.join(MODES)}")
        grid = grid or ROUTING_GRID_DEFAULT
        if grid not in GRID_CHOICES:
            raise DataError(f"Unknown grid '{grid}'. Use one of: {', '.join(GRID_CHOICES)}")
        key = json.dumps(
            [round(start["lat"], 5), round(start["lon"], 5), round(dest["lat"], 5), round(dest["lon"], 5), mode]
            + ([] if grid == "native" else [grid])
        )
        rid = hashlib.sha1(key.encode()).hexdigest()[:12]
        if rid in self.routes:
            return self.routes[rid]
        g, S = self.grids[grid], self.S_by[grid]
        a, b = g.cell(start["lat"], start["lon"]), g.cell(dest["lat"], dest["lon"])
        c = cell_cost(g, S, mode)
        t0 = time.perf_counter()
        if grid == "native":
            path, total = astar(g, c, a, b, MODES[mode]["beta"])
            algo = "A* (pure Python, admissible heuristic)"
        else:
            path, total = shortest_path(g, c, a, b)
            algo = "Dijkstra (scipy.sparse.csgraph, compiled)"
        t1 = time.perf_counter()
        profile, segs, stops, metrics = analyse(g, S, c, path, mode, self.targets)
        # Read slope along the chosen path on the 1/1024 deg analysis grid.
        lat = np.array([p["lat"] for p in profile])
        lon = np.array([p["lon"] for p in profile])
        mean_i, max_i = sample_slope_along(self.analysis, lat, lon)
        for s in segs:
            lo, hi = s["from_vertex"], max(s["from_vertex"] + 1, s["to_vertex"])
            s["slope_mean_deg_analysis"] = round(float(mean_i[lo:hi].mean()), 2)
            s["slope_max_deg_analysis"] = round(float(max_i[lo:hi].max()), 2)
        metrics["slope_max_deg_analysis"] = round(float(max_i.max()), 2)
        t2 = time.perf_counter()
        coords = [[p["lon"], p["lat"]] for p in profile]
        info = self.level_info[grid]
        r = {
            "route_id": rid,
            "mode": mode,
            "mode_label": MODES[mode]["label"],
            "intent": MODES[mode]["intent"],
            "weights": {k: MODES[mode][k] for k in ("alpha", "beta", "gamma")},
            "start": start,
            "dest": dest,
            "algorithm_cost": round(total, 1),
            "grid": {
                **info,
                "status": self.grid_status(grid),
                "algorithm": algo,
                "cells": int(g.h * g.w),
                "evidence_grid": self.level_info["analysis"]["cell_deg"],
            },
            "timing_ms": {"search": round(1000 * (t1 - t0), 1), "analysis": round(1000 * (t2 - t1), 1)},
            "geojson": {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {"route_id": rid, "mode": mode, "grid": grid},
            },
            "profile": profile,
            "segments": segs,
            "stops": stops,
            "metrics": metrics,
            "data_mode": self.manifest["data_mode"],
        }
        self.routes[rid] = r
        return r

    def evidence(self, rid: str, seg_id: str) -> dict:
        r = self.routes.get(rid)
        if r is None:
            raise DataError("Route not found — generate it first")
        s = next((x for x in r["segments"] if x["id"] == seg_id), None)
        if s is None:
            raise DataError(f"Segment {seg_id} not found on this route")
        w = r["weights"]
        topo = self.manifest["layers"][0]["provenance"]
        rank = sorted(r["segments"], key=lambda x: -x["cost_per_m"]).index(s) + 1
        t = TERRAIN
        gi = r["grid"]
        terrain_text = (
            f"Mean slope {s['slope_mean_deg']}° (max {s['slope_max_deg']}°) and local relief {s['relief_mean_m']} m "
            f"give a modeled terrain cost T = {s['T_mean']} (0–1). Elevation {s['elev_start_m']} → {s['elev_end_m']} m "
            f"(+{s['gain_m']:g} m up, {s['loss_m']:g} m down) over {s['length_m']/1000:.2f} km. "
            f"Route searched on the {gi['cell_deg']} {gi['level']} grid; slope also read on the "
            f"{gi['evidence_grid']} analysis grid (max {s.get('slope_max_deg_analysis')}°). "
            + ("Finer grids are interpolated: they add no terrain detail." if gi["level"] != "native" else "")
        )
        nt = s["nearest_target"]
        sci_text = (
            (
                f"Nearest candidate target: {nt['name']} at {nt['distance_m']/1000:.2f} km ({nt['status']}). "
                f"Mean science proximity S = {s['S_mean']}."
            )
            if nt
            else "No candidate science target in this region."
        )
        share_cost = s["cost"] / max(1e-9, sum(x["cost"] for x in r["segments"]))
        share_len = s["length_m"] / max(1e-9, sum(x["length_m"] for x in r["segments"]))
        decision = (
            f"{s['id']} is part of ROUTE {s['id'][0]} ({r['mode_label']}). It carries {100*share_cost:.0f}% of the route's modeled cost "
            f"over {100*share_len:.0f}% of its length. Under these weights, no cheaper connected path between the same endpoints exists "
            f"on this grid ({'A* optimality' if gi['level'] == 'native' else 'exact optimum found by Dijkstra — the same guarantee as A* optimality'})."
        )
        surface = next((l for l in self.manifest["layers"] if l["id"] == "surface"), None)
        surface_sec = (
            {
                "text": (
                    f"{surface['name']}: {surface['provenance']['product']}. It is computed from the elevation grid, "
                    "so it shows the same terrain again as light and shadow — it is NOT an orbital photograph and adds no new evidence."
                ),
                "status": surface["provenance"]["status"],
            }
            if surface
            else {
                "text": "No surface imagery is integrated in this build. HiRISE orthoimagery of this segment is the planned next layer.",
                "status": "DATA_UNAVAILABLE",
            }
        )
        src_cell = "Synthetic fixture cells are" if self.synthetic else "MOLA cells are"
        return {
            "route_id": rid,
            "segment": s,
            "decision": decision,
            "mode": r["mode_label"],
            "rank_by_cost_per_m": f"{rank} of {len(r['segments'])}",
            "label": "Higher modeled traversal cost" if s["higher_cost"] else "Lower modeled traversal cost",
            "sections": {
                "TERRAIN": {
                    "text": terrain_text,
                    "status": "DERIVED" if not self.synthetic else "SYNTHETIC",
                    "values": [
                        ["mean slope", s["slope_mean_deg"], "deg"],
                        ["max slope", s["slope_max_deg"], "deg"],
                        ["max slope (analysis grid)", s.get("slope_max_deg_analysis"), "deg"],
                        ["local relief", s["relief_mean_m"], "m"],
                        ["terrain cost T", s["T_mean"], "0–1"],
                        ["elevation gain", s["gain_m"], "m"],
                        ["length", s["length_m"], "m"],
                    ],
                },
                "SURFACE": surface_sec,
                "SCIENCE": {"text": sci_text, "status": nt["status"] if nt else "DATA_UNAVAILABLE"},
                "DATA": {
                    "text": f"{topo['source_name']} — {topo['product']}",
                    "status": topo["status"],
                    "url": topo["source_url"],
                },
                "METHOD": {
                    "text": (
                        f"Cell cost c = β + α·T + γ·(1−S) with α={w['alpha']}, β={w['beta']}, γ={w['gamma']} ({r['mode_label']}). "
                        f"Edge cost = step length × mean c. {gi['algorithm']}, 8-connected {gi['cell_deg']} grid ({gi['cells']} cells). "
                        f"T = {t['w_slope']}·min(1, slope/{t['slope_ref_deg']}°)² + {t['w_relief']}·min(1, relief/{t['relief_ref_m']} m). "
                        f"S = max exp(−d²/2σ²), σ = {SCIENCE_SIGMA_M:.0f} m."
                    ),
                    "breakdown": s["cost_breakdown"],
                    "status": "DERIVED",
                },
                "PROVENANCE": {
                    "chain": [
                        topo["mission"],
                        topo["instrument"],
                        topo["product"],
                        topo["archive"],
                        f"grid: {gi['cell_deg']} {gi['level']} — {gi['status']}",
                    ],
                    "status": topo["status"],
                },
                "LIMITATION": {
                    "items": [
                        f"{src_cell} ~463 m (1/128°): boulders, small craters and short steep slopes are invisible at this scale. "
                        + (
                            "The finer route grid is interpolated and does not reveal them."
                            if gi["level"] != "native"
                            else ""
                        ),
                        (
                            f"{round(100*s['interpolated_fraction'])}% of this segment's cells have zero shots in the shot-count grid (interpolated)."
                            if s["interpolated_fraction"] is not None
                            else "Shot-count coverage not available for this build."
                        ),
                        "Cost weights and the slope limit are assumptions, not measured human or rover mobility limits.",
                        "This is a planning aid, not a safety assessment.",
                    ]
                    + (
                        ["SYNTHETIC TEST TERRAIN: these numbers come from a generated fixture, not from Mars data."]
                        if self.synthetic
                        else []
                    ),
                    "status": "ASSUMPTION",
                },
            },
        }


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store()
