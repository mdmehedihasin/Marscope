"""Interpolated grid levels, exact routing on the routing grid, status labels and the Starlette fallback API.
Small synthetic inputs only; no network, no real source data required."""

import numpy as np
import pytest

from app.api.asgi_client import Client, available_apps
from app.geospatial.levels import (
    build_level,
    level_description,
    relief_window,
    slope_stats,
    upsample_bicubic,
    upsample_nearest,
)
from app.geospatial.terrain import pixel_spacing_m, slope_deg
from app.ingestion.pds3 import DataError
from app.provenance.registry import REQUIRED, STATUS, grid_record
from app.routing.engine import Grid, astar, cell_cost, sample_slope_along, shortest_path

R = 3_396_000.0


def test_status_vocabulary_has_all_seven_words():
    assert set(STATUS) == {
        "VERIFIED",
        "DERIVED",
        "APPROXIMATE",
        "ASSUMPTION",
        "SYNTHETIC",
        "CONCEPTUAL",
        "DATA_UNAVAILABLE",
    }


def test_upsample_nearest_is_exact_block_copy():
    a = np.arange(6).reshape(2, 3)
    u = upsample_nearest(a, 4)
    assert u.shape == (8, 12) and (u[:4, :4] == 0).all() and (u[4:, 8:] == 5).all()


def test_bicubic_reproduces_a_plane_and_keeps_bounds_alignment():
    h, w = 20, 24
    z = np.add.outer(np.arange(h) * 30.0, np.arange(w) * -12.0)  # plane in index space
    f = 4
    u = upsample_bicubic(z, f)
    assert u.shape == (h * f, w * f)
    k = np.arange(0, f * h)  # all rows, edges included (odd-reflection padding)
    r = (k + 0.5) / f - 0.5  # fine centre in native index units
    assert np.allclose(u[k, f * 10], 30.0 * r + -12.0 * ((f * 10 + 0.5) / f - 0.5), atol=1e-6)
    assert np.isclose(upsample_bicubic(z, 1), z).all()  # factor 1 = unchanged copy


def test_bicubic_keeps_nan_footprint():
    z = np.ones((10, 10))
    z[4, 5] = np.nan
    u = upsample_bicubic(z, 4)
    assert np.isnan(u[16:20, 20:24]).all() and np.isfinite(u[:16]).all()


def test_fine_grid_slope_of_a_10_degree_plane():
    h, w, ppd = 30, 30, 128.0
    lat = 18.5 - (np.arange(h) + 0.5) / ppd
    dy, _ = pixel_spacing_m(lat, ppd, R)
    z = np.tile((np.arange(h) * dy * np.tan(np.radians(10.0)))[:, None], (1, w))
    lv = build_level(z, None, 18.5, 77.0, ppd, R, 4)
    s = lv["slope"][1:-1, 1:-1]
    assert np.allclose(s, 10.0, atol=1e-3) and lv["ppd"] == 512.0
    assert relief_window(4) % 2 == 1 and relief_window(8) % 2 == 1


def test_level_description_says_no_new_information():
    d = level_description("routing", 4, 128.0, R, 18.4)
    assert d["cell_deg"] == "1/512°" and 110 < d["cell_ns_m"] < 120 and "NOT add" in d["information_note"]


def test_grid_record_is_never_verified():
    d = level_description("routing", 4, 128.0, R, 18.4)
    for synth in (True, False):
        rec = grid_record(d, synth)
        assert all(k in rec and rec[k] not in (None, "") for k in REQUIRED)
        assert rec["status"] == ("SYNTHETIC" if synth else "APPROXIMATE")


def _grid(z, ppd=128.0):
    lat = 18.5 - (np.arange(z.shape[0]) + 0.5) / ppd
    return Grid(z, slope_deg(z, lat, ppd, R), np.zeros_like(z), None, 18.5, 77.0, ppd, R)


def test_dijkstra_matches_astar_cost_on_rough_terrain():
    rng = np.random.default_rng(7)
    z = rng.normal(0, 20, (35, 40)).cumsum(axis=1)  # rough, deterministic
    g = _grid(z)
    for mode in ("traversability", "balanced"):
        c = cell_cost(g, np.zeros_like(z), mode)
        a_path, a_cost = astar(g, c, (2, 2), (30, 37), 1.0)
        d_path, d_cost = shortest_path(g, c, (2, 2), (30, 37))
        assert np.isclose(a_cost, d_cost, rtol=1e-9)  # same optimum (ties may differ)
        assert d_path[0] == (2, 2) and d_path[-1] == (30, 37)
        assert all(abs(p[0] - q[0]) <= 1 and abs(p[1] - q[1]) <= 1 for p, q in zip(d_path, d_path[1:]))


def test_dijkstra_reports_disconnected_grid():
    z = np.zeros((20, 20))
    z[:, 10] = 5000.0
    g = _grid(z)
    with pytest.raises(DataError):
        shortest_path(g, cell_cost(g, np.zeros_like(z), "balanced"), (5, 2), (5, 18))


def test_slope_sampling_along_path_reads_fine_grid():
    z = np.zeros((40, 40))
    z[:, 20:] = np.arange(20) * 50.0  # flat west half, ramp east half
    g = _grid(z, ppd=1024.0)
    lat = np.array([g.lat[10], g.lat[10]])
    lon = np.array([g.lon[2], g.lon[10]])
    m, x = sample_slope_along(g, lat, lon)
    assert x[0] < 0.01
    lon2 = np.array([g.lon[25], g.lon[35]])
    m2, x2 = sample_slope_along(g, lat, lon2)
    assert m2[0] > 1.0


def test_slope_stats_fields():
    s = slope_stats(np.array([[1.0, 2.0], [30.0, np.nan]]), 25.0)
    assert s["max_deg"] == 30.0 and s["cells_above_limit"] == 1 and s["cells"] == 3


# Store and API level (processed region)
@pytest.fixture(scope="module")
def lite():
    return Client(dict(available_apps())["lite"])


def test_default_routes_use_routing_grid_and_are_labelled(lite):
    rs = lite.post("/api/routes/compare", json={}).json()["routes"]
    meta = lite.get("/api/metadata").json()
    synth = meta["data_mode"] != "NASA_PDS"
    for r in rs:
        assert r["grid"]["level"] == "routing" and r["grid"]["cell_deg"] == "1/512°"
        assert r["grid"]["status"] == ("SYNTHETIC" if synth else "APPROXIMATE")
        assert r["timing_ms"]["search"] < 10_000
        assert all("slope_max_deg_analysis" in s for s in r["segments"])
    assert set(meta["grids"]) == {"native", "routing", "analysis"}
    assert set(meta["slope_by_level"]) == {"native", "routing", "analysis"}
    assert meta["grids"]["native"]["status"] == ("SYNTHETIC" if synth else "VERIFIED")
    assert "Pre-event concept prototype" in meta["disclosure"]


def test_native_grid_still_available_for_comparison(lite):
    r = lite.post("/api/routes", json={"mode": "balanced", "grid": "native"}).json()
    assert r["grid"]["level"] == "native" and r["grid"]["algorithm"].startswith("A*")
    bad = lite.post("/api/routes", json={"mode": "balanced", "grid": "ctx"})
    assert bad.status_code == 422 and "Unknown grid" in bad.json()["error"]


def test_lite_server_validation_errors_are_clean(lite):
    r = lite.post("/api/routes", json={"start": {"lat": 999, "lon": 77}})
    assert r.status_code == 422 and "error" in r.json() and "Traceback" not in r.text
    assert lite.get("/api/cell", params={"lat": 18.4}).status_code == 422
    assert lite.get("/api/routes/nope/evidence", params={"segment": "C-01"}).status_code == 422
    assert lite.get("/api/credits").json()["credits"]
