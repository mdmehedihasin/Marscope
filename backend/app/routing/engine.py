"""Route search (A* on the native grid, Dijkstra on the routing grid), the cost model and route analysis."""

from __future__ import annotations

import heapq

import numpy as np

from ..config import MODES, SCIENCE_SIGMA_M, SEGMENT_TARGET_M, STOP_RADIUS_M, TERRAIN
from ..geospatial.terrain import haversine_m, pixel_spacing_m
from ..ingestion.pds3 import DataError


class Grid:
    """Elevation and derived layers on one grid level (native, routing or analysis)."""

    def __init__(self, z, slope, relief, counts, lat_max, lon_west, ppd, radius_m):
        self.z, self.slope, self.relief, self.counts = z, slope, relief, counts
        self.lat_max, self.lon_west, self.ppd, self.radius_m = lat_max, lon_west, ppd, radius_m
        self.h, self.w = z.shape
        self.lat = lat_max - (np.arange(self.h) + 0.5) / ppd
        self.lon = lon_west + (np.arange(self.w) + 0.5) / ppd
        self.dy, self.dx = pixel_spacing_m(self.lat, ppd, radius_m)
        self.T = terrain_cost(slope, relief)
        self.passable = np.isfinite(z) & (slope <= TERRAIN["max_slope_deg"])

    def cell(self, lat, lon):
        i = int(np.floor((self.lat_max - lat) * self.ppd))
        j = int(np.floor((lon - self.lon_west) * self.ppd))
        if not (0 <= i < self.h and 0 <= j < self.w):
            raise DataError(f"Point {lat:.4f}N {lon:.4f}E is outside the processed region")
        return i, j

    def bounds(self):
        return {
            "lat_min": self.lat_max - self.h / self.ppd,
            "lat_max": self.lat_max,
            "lon_min": self.lon_west,
            "lon_max": self.lon_west + self.w / self.ppd,
        }


def terrain_cost(slope, relief):
    """T in [0,1] = w_s*min(1,slope/slope_ref)^2 + w_r*min(1,relief/relief_ref)."""
    t = TERRAIN
    s = np.minimum(1.0, slope / t["slope_ref_deg"]) ** 2
    r = np.minimum(1.0, relief / t["relief_ref_m"])
    return t["w_slope"] * s + t["w_relief"] * r


def science_field(grid: Grid, targets: list[dict]) -> np.ndarray:
    """S in [0,1]: max over targets of exp(-d^2 / (2 sigma^2)), great-circle distance d."""
    S = np.zeros((grid.h, grid.w))
    LAT, LON = np.meshgrid(grid.lat, grid.lon, indexing="ij")
    for t in targets:
        if not t.get("science"):
            continue
        d = haversine_m(LAT, LON, t["lat"], t["lon"], grid.radius_m)
        S = np.maximum(S, np.exp(-(d**2) / (2 * SCIENCE_SIGMA_M**2)))
    return S


def cell_cost(grid: Grid, S: np.ndarray, mode: str) -> np.ndarray:
    m = MODES[mode]
    return m["beta"] + m["alpha"] * grid.T + m["gamma"] * (1.0 - S)


_NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def astar(grid: Grid, c: np.ndarray, start: tuple, goal: tuple, beta: float):
    """A* over 8-connected cells. Edge cost = step length (m) x mean cell cost.
    Heuristic = beta x straight-line distance — admissible because every cell cost >= beta."""
    h, w = grid.h, grid.w
    if not grid.passable[start] or not grid.passable[goal]:
        raise DataError("Start or destination lies on a cell excluded by the terrain model")
    gi, gj = goal
    lat_g, lon_g = grid.lat[gi], grid.lon[gj]
    INF = np.inf
    g = np.full(h * w, INF)
    g[start[0] * w + start[1]] = 0.0
    parent = np.full(h * w, -1, dtype=np.int64)
    closed = np.zeros(h * w, dtype=bool)
    heur = lambda i, j: beta * float(haversine_m(grid.lat[i], grid.lon[j], lat_g, lon_g, grid.radius_m))
    pq = [(heur(*start), 0.0, start[0] * w + start[1])]
    goal_k = gi * w + gj
    while pq:
        f, gc, k = heapq.heappop(pq)
        if closed[k]:
            continue
        closed[k] = True
        if k == goal_k:
            break
        i, j = divmod(k, w)
        for di, dj in _NB:
            ni, nj = i + di, j + dj
            if not (0 <= ni < h and 0 <= nj < w) or not grid.passable[ni, nj]:
                continue
            nk = ni * w + nj
            if closed[nk]:
                continue
            dx = 0.5 * (grid.dx[i] + grid.dx[ni]) * dj
            step = (dx * dx + (grid.dy * di) ** 2) ** 0.5
            ng = gc + step * 0.5 * (c[i, j] + c[ni, nj])
            if ng < g[nk]:
                g[nk] = ng
                parent[nk] = k
                heapq.heappush(pq, (ng + heur(ni, nj), ng, nk))
    if not np.isfinite(g[goal_k]):
        raise DataError("No connected route exists between these points under the current terrain model")
    path, k = [], goal_k
    while k != -1:
        path.append(divmod(int(k), w))
        k = parent[k]
    return path[::-1], float(g[goal_k])


def _edges(grid: Grid):
    """All 8-connected edges between passable cells, with spherical step lengths (cached on the grid)."""
    if getattr(grid, "_edge_cache", None) is not None:
        return grid._edge_cache
    h, w = grid.h, grid.w
    idx = np.arange(h * w).reshape(h, w)
    src, dst, step = [], [], []
    for di, dj in _NB:
        i0, i1 = max(0, -di), h - max(0, di)
        j0, j1 = max(0, -dj), w - max(0, dj)
        a = grid.passable[i0:i1, j0:j1] & grid.passable[i0 + di : i1 + di, j0 + dj : j1 + dj]
        s = idx[i0:i1, j0:j1][a]
        d = idx[i0 + di : i1 + di, j0 + dj : j1 + dj][a]
        rows = np.arange(i0, i1)
        dx = 0.5 * (grid.dx[rows] + grid.dx[rows + di]) * dj
        st = np.sqrt(dx[:, None] ** 2 + (grid.dy * di) ** 2) * np.ones((1, j1 - j0))
        src.append(s)
        dst.append(d)
        step.append(st[a])
    grid._edge_cache = (np.concatenate(src), np.concatenate(dst), np.concatenate(step))
    return grid._edge_cache


def shortest_path(grid: Grid, c: np.ndarray, start: tuple, goal: tuple):
    """Exact least-cost path with the SAME edge model as `astar` (step length x mean cell cost),
    solved by Dijkstra in compiled code (scipy.sparse.csgraph). Used on the large routing grid, where the
    pure-Python A* would be too slow. Optimal and deterministic; equal-cost ties may be broken differently."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra

    if not grid.passable[start] or not grid.passable[goal]:
        raise DataError("Start or destination lies on a cell excluded by the terrain model")
    src, dst, step = _edges(grid)
    cf = c.ravel()
    wgt = step * 0.5 * (cf[src] + cf[dst])
    n = grid.h * grid.w
    G = csr_matrix((wgt, (src, dst)), shape=(n, n))
    s = start[0] * grid.w + start[1]
    t = goal[0] * grid.w + goal[1]
    dist, pred = dijkstra(G, directed=True, indices=s, return_predecessors=True)
    if not np.isfinite(dist[t]):
        raise DataError("No connected route exists between these points under the current terrain model")
    path, k = [], t
    while k != -9999 and k != s:
        path.append(divmod(int(k), grid.w))
        k = pred[k]
    path.append(divmod(int(s), grid.w))
    return path[::-1], float(dist[t])


def sample_slope_along(fine: Grid, lat: np.ndarray, lon: np.ndarray):
    """Densify a lat/lon polyline to the fine grid spacing and read its slope cells (nearest cell).
    Returns per-vertex-interval arrays (mean, max) so callers can aggregate per segment."""
    n = len(lat)
    means, maxs = np.zeros(max(n - 1, 1)), np.zeros(max(n - 1, 1))
    for k in range(n - 1):
        m = max(2, int(np.ceil(max(abs(lat[k + 1] - lat[k]), abs(lon[k + 1] - lon[k])) * fine.ppd * 2)) + 1)
        la = np.linspace(lat[k], lat[k + 1], m)
        lo = np.linspace(lon[k], lon[k + 1], m)
        i = np.clip(np.floor((fine.lat_max - la) * fine.ppd).astype(int), 0, fine.h - 1)
        j = np.clip(np.floor((lo - fine.lon_west) * fine.ppd).astype(int), 0, fine.w - 1)
        v = fine.slope[i, j]
        means[k], maxs[k] = float(np.nanmean(v)), float(np.nanmax(v))
    return means, maxs


def analyse(grid: Grid, S, c, path, mode, targets):
    """Per-vertex profile, ~1.5 km segments with evidence values, and route metrics (all derived)."""
    ii = np.array([p[0] for p in path])
    jj = np.array([p[1] for p in path])
    lat, lon = grid.lat[ii], grid.lon[jj]
    step = np.r_[0.0, haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:], grid.radius_m)]
    dist = np.cumsum(step)
    edge_cost = np.r_[0.0, step[1:] * 0.5 * (c[ii[:-1], jj[:-1]] + c[ii[1:], jj[1:]])]
    z, sl, rl, T, Sv = grid.z[ii, jj], grid.slope[ii, jj], grid.relief[ii, jj], grid.T[ii, jj], S[ii, jj]
    cnt = grid.counts[ii, jj] if grid.counts is not None else None
    m = MODES[mode]
    profile = [
        {
            "d_km": round(float(d) / 1000, 3),
            "lat": round(float(a), 5),
            "lon": round(float(b), 5),
            "elev_m": round(float(e), 1),
            "slope_deg": round(float(s), 2),
            "relief_m": round(float(r), 1),
            "T": round(float(t), 3),
            "S": round(float(sv), 3),
            "interpolated": (None if cnt is None else bool(cnt[k] == 0)),
        }
        for k, (d, a, b, e, s, r, t, sv) in enumerate(zip(dist, lat, lon, z, sl, rl, T, Sv))
    ]
    n_seg = max(1, int(round(dist[-1] / SEGMENT_TARGET_M)))
    edges = np.linspace(0, dist[-1], n_seg + 1)
    segs = []
    hi_T = max(0.35, float(np.percentile(T, 75)))
    for s_i in range(n_seg):
        sel = np.where((dist >= edges[s_i] - 1e-6) & (dist <= edges[s_i + 1] + 1e-6))[0]
        if len(sel) < 2:
            sel = np.array([max(0, sel[0] - 1) if len(sel) else 0, min(len(path) - 1, (sel[0] if len(sel) else 0) + 1)])
        a, b = sel[0], sel[-1]
        seg_cost = float(edge_cost[a + 1 : b + 1].sum())
        length = float(dist[b] - dist[a])
        mT, mS = float(T[sel].mean()), float(Sv[sel].mean())
        terr_share = m["alpha"] * mT
        sci_share = m["gamma"] * (1 - mS)
        base = m["beta"]
        tot = base + terr_share + sci_share
        mid = (lat[sel].mean(), lon[sel].mean())
        near = nearest_target(mid, targets, grid.radius_m)
        dz = np.diff(z[sel])
        segs.append(
            {
                "id": f"{m['letter']}-{s_i + 1:02d}",
                "index": s_i,
                "from_vertex": int(a),
                "to_vertex": int(b),
                "coords": [[round(float(lon[k]), 5), round(float(lat[k]), 5)] for k in sel],
                "length_m": round(length, 1),
                "elev_start_m": round(float(z[a]), 1),
                "elev_end_m": round(float(z[b]), 1),
                "gain_m": round(float(dz[dz > 0].sum()), 1) + 0.0,
                "loss_m": round(float(np.abs(dz[dz < 0]).sum()), 1) + 0.0,
                "slope_mean_deg": round(float(sl[sel].mean()), 2),
                "slope_max_deg": round(float(sl[sel].max()), 2),
                "relief_mean_m": round(float(rl[sel].mean()), 1),
                "T_mean": round(mT, 3),
                "S_mean": round(mS, 3),
                "cost": round(seg_cost, 1),
                "cost_per_m": round(seg_cost / max(length, 1), 3),
                "cost_breakdown": {
                    "distance (beta)": round(base / tot, 3),
                    "terrain (alpha*T)": round(terr_share / tot, 3),
                    "science penalty (gamma*(1-S))": round(sci_share / tot, 3),
                },
                "higher_cost": bool(mT >= hi_T),
                "interpolated_fraction": (None if cnt is None else round(float((cnt[sel] == 0).mean()), 3)),
                "nearest_target": near,
            }
        )
    stops = []
    for t in targets:
        if not t.get("science"):
            continue
        d = haversine_m(lat, lon, t["lat"], t["lon"], grid.radius_m)
        k = int(np.argmin(d))
        if d[k] <= STOP_RADIUS_M:
            stops.append(
                {
                    "target_id": t["id"],
                    "name": t["name"],
                    "distance_m": round(float(d[k]), 0),
                    "at_km": round(float(dist[k]) / 1000, 2),
                    "status": t["status"],
                }
            )
    stops.sort(key=lambda x: x["at_km"])
    for n_, st_ in enumerate(stops, 1):
        st_["number"] = f"{n_:02d}"
        st_["label"] = f"SCIENCE STOP {n_:02d}"
    dirs = np.arctan2(np.diff(ii), np.diff(jj))
    turns = int((np.abs(np.diff(dirs)) > 1e-6).sum()) if len(dirs) > 1 else 0
    metrics = {
        "length_km": round(float(dist[-1]) / 1000, 2),
        "total_cost": round(float(edge_cost.sum()), 0),
        "elev_gain_m": round(float(np.diff(z)[np.diff(z) > 0].sum()), 0),
        "elev_loss_m": round(float(np.abs(np.diff(z)[np.diff(z) < 0]).sum()), 0) + 0.0,
        "slope_mean_deg": round(float(sl.mean()), 2),
        "slope_max_deg": round(float(sl.max()), 2),
        "T_mean": round(float(T.mean()), 3),
        "S_mean": round(float(Sv.mean()), 3),
        "higher_cost_segments": sum(s["higher_cost"] for s in segs),
        "segments": len(segs),
        "candidate_stops": len(stops),
        "direction_changes": turns,
        "interpolated_fraction": (None if cnt is None else round(float((cnt == 0).mean()), 3)),
    }
    return profile, segs, stops, metrics


def nearest_target(pt, targets, radius_m):
    best = None
    for t in targets:
        d = float(haversine_m(pt[0], pt[1], t["lat"], t["lon"], radius_m))
        if best is None or d < best["distance_m"]:
            best = {"id": t["id"], "name": t["name"], "distance_m": round(d, 0), "status": t["status"]}
    return best
