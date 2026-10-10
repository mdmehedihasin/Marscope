# Routing

All parameters below live in `backend/app/config.py`. They are **ASSUMPTIONS** and are shown in the app.

## Grids

Routes are searched on the **1/512° routing grid** (~116 m, cubic interpolation of the 1/128° source grid) by default.
The **native 1/128° grid** stays selectable (`"grid": "native"` in the API, "Routing grid" in PLAN). Finer spacing adds
no terrain information (see [SCIENTIFIC_METHOD.md](SCIENTIFIC_METHOD.md)).

## Graph

Every passable cell is a node with 8-connected edges. Step length on the sphere: dy = πR/180/ppd, dx = dy·cos(lat)
(dx is averaged between the two rows of a diagonal step). The same graph model is used on every grid.

## Cost model

- **Terrain cost (0–1):** `T = 0.75·min(1, slope/15°)² + 0.25·min(1, relief/150 m)`, where relief = max − min elevation
  in a window with a ~1.4 km footprint (3×3 cells native, 13×13 cells on the routing grid).
- **Science proximity (0–1):** `S = max_k exp(−d_k² / 2σ²)`, σ = 1500 m, over the candidate science targets
  (great-circle distance).
- **Cell cost:** `c = β + α·T + γ·(1−S)`; **edge cost** = step length (m) × (c_i + c_j)/2.
- **Excluded cells:** slope > 25° (and no-data cells). The 25° limit was chosen for ~463 m cells and is applied unchanged
  on the finer grids. It is a **modelling threshold, not a human or rover mobility limit**.

| Mode | α | β | γ | Intent |
|---|---|---|---|---|
| TRAVERSABILITY-FIRST (A) | 6 | 1 | 0 | minimise modeled terrain cost |
| SCIENCE-FIRST (B) | 1.5 | 1 | 4 | stay near candidate science |
| BALANCED (C) | 3 | 1 | 1.5 | trade-off |

## Search

- **Native grid:** A* with heuristic β × great-circle distance (admissible because every cell cost is ≥ β).
- **Routing grid:** Dijkstra in compiled code (`scipy.sparse.csgraph`), same edge model, exact.

Both are optimal and deterministic. On the Demo Mission, Dijkstra returns the same paths and costs as A* on the routing
grid, 4–7× faster. Equal-cost ties may break differently.

**Timings** (cloud test machine, Demo Mission, best of 3; run `python scripts/benchmark_routes.py` on your computer):

| grid | cells | algorithm | time per route |
|---|---|---|---|
| native 1/128° | 21,896 | A* | 0.04–0.07 s |
| routing 1/512° | 350,336 | A* | 0.60–1.20 s |
| routing 1/512° | 350,336 | Dijkstra (compiled) | 0.16–0.17 s |

A three-route comparison therefore takes about half a second on the routing grid.

## Evidence and metrics

- **Segments:** the route is split into ~1.5 km segments (`A-01`, `B-03`, …). Each segment reports length, elevation
  gain/loss, mean/max slope on the route grid, max slope read along the path on the 1/1024° analysis grid, relief,
  mean T and S, cost, cost/m rank, cost breakdown, interpolated-cell fraction and nearest target.
- **Higher modeled traversal cost:** segment mean T ≥ max(0.35, the route's 75th percentile of T).
- **Candidate science stop:** a science target within 1200 m of the route.
- **Route metrics:** length, total cost, gain/loss, mean/max slope, higher-cost segment count, candidate stops, direction
  changes, interpolated fraction, search time. No "safety" or "best" score exists.
