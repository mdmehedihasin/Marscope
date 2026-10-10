#!/usr/bin/env python3
"""Time route search on each grid for the default Demo Mission endpoints and print a small table.
Writes docs/benchmark_latest.json. Timings depend on the machine; they are measurements, not guarantees.

  python scripts/benchmark_routes.py
"""

import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import MODES  # noqa: E402
from app.routing.engine import astar, cell_cost, shortest_path  # noqa: E402
from app.store import Store  # noqa: E402


def best_of(fn, n=3):
    t = []
    for _ in range(n):
        t0 = time.perf_counter()
        out = fn()
        t.append(time.perf_counter() - t0)
    return min(t), out


def main():
    t0 = time.perf_counter()
    st = Store()
    init = time.perf_counter() - t0
    s, d = st.default_endpoints()
    rows = []
    for gname, algo in [("native", "astar"), ("routing", "astar"), ("routing", "dijkstra")]:
        g, S = st.grids[gname], st.S_by[gname]
        a, b = g.cell(s["lat"], s["lon"]), g.cell(d["lat"], d["lon"])
        for m in MODES:
            c = cell_cost(g, S, m)
            fn = (
                (lambda: astar(g, c, a, b, MODES[m]["beta"]))
                if algo == "astar"
                else (lambda: shortest_path(g, c, a, b))
            )
            sec, (path, cost) = best_of(fn)
            rows.append(
                {
                    "grid": gname,
                    "cells": g.h * g.w,
                    "algorithm": algo,
                    "mode": m,
                    "seconds": round(sec, 3),
                    "path_vertices": len(path),
                    "cost": round(cost, 1),
                }
            )
    out = {
        "machine": f"{platform.system()} {platform.machine()} · Python {platform.python_version()}",
        "data_mode": st.manifest["data_mode"],
        "store_init_s": round(init, 2),
        "levels_build_ms": st.levels_build_ms,
        "runs": rows,
    }
    (ROOT / "docs" / "benchmark_latest.json").write_text(json.dumps(out, indent=1))
    print(
        f"data_mode={out['data_mode']}  store init {out['store_init_s']} s (grid levels {st.levels_build_ms} ms)  [{out['machine']}]"
    )
    for r in rows:
        print(
            f"  {r['grid']:8s} {r['cells']:>7d} cells  {r['algorithm']:8s} {r['mode']:15s} {r['seconds']:6.3f} s  {r['path_vertices']:4d} vertices  cost {r['cost']}"
        )


if __name__ == "__main__":
    main()
