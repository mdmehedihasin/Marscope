"""Deterministic tests on small synthetic inputs and the synthetic MEGDR fixture."""

import json
from pathlib import Path

import numpy as np
import pytest

from app.api.asgi_client import Client, available_apps
from app.config import FIXTURES, MODES
from app.geospatial.terrain import haversine_m, pixel_spacing_m, slope_deg
from app.ingestion.pds3 import DataError, Raster, clip, geometry_from_label, parse_label, read_megdr
from app.provenance.registry import REQUIRED, mola_record
from app.routing.engine import Grid, analyse, astar, cell_cost, science_field

R = 3_396_000.0


def flat_grid(z, counts=None, ppd=128.0, lat_max=18.5, lon_west=77.0):
    lat = lat_max - (np.arange(z.shape[0]) + 0.5) / ppd
    return Grid(z, slope_deg(z, lat, ppd, R), np.zeros_like(z), counts, lat_max, lon_west, ppd, R)


# Coordinate transformation
def test_pixel_latlon_roundtrip():
    r = Raster(np.zeros((10, 20)), 18.5, 77.0, 128.0, R)
    for i, j in [(0, 0), (5, 7), (9, 19)]:
        assert np.isclose(r.row_of_lat(r.lat_of_row(i)), i) and np.isclose(r.col_of_lon(r.lon_of_col(j)), j)
    assert np.isclose(r.lat_of_row(0), 18.5 - 0.5 / 128)


def test_label_parsing_and_validation():
    lab = parse_label(
        'A = 1\nOBJECT = IMAGE\n  LINES = 4\n  UNIT = METER\nEND_OBJECT = IMAGE\nB = "two\n words" \nEND\n'
    )
    assert lab["A"] == 1 and lab["IMAGE"]["LINES"] == 4 and lab["B"] == "two words"
    r = read_megdr(FIXTURES / "megt_fixture.lbl")
    assert r.shape == (256, 256) and r.ppd == 128 and r.radius_m == R


# Raster alignment and clipping
def test_clip_is_pixel_exact_and_aligned():
    t = read_megdr(FIXTURES / "megt_fixture.lbl")
    c = read_megdr(FIXTURES / "megc_fixture.lbl")
    a, sa = clip(t, 18.0, 18.6, 77.1, 77.9)
    b, _ = clip(c, 18.0, 18.6, 77.1, 77.9)
    assert sa["resampled"] is False and a.shape == b.shape and a.lat_max == b.lat_max and a.lon_west == b.lon_west
    i0, j0 = sa["rows"][0], sa["cols"][0]
    assert np.array_equal(a.data, t.data[i0 : i0 + a.shape[0], j0 : j0 + a.shape[1]])  # values unchanged
    bb = a.bounds()
    assert bb["lat_max"] >= 18.6 and bb["lat_min"] <= 18.0
    with pytest.raises(DataError):
        clip(t, 10, 11, 77, 78)


# Slope calculation
def test_slope_on_known_plane():
    h, w = 40, 40
    lat = 18.5 - (np.arange(h) + 0.5) / 128
    dy, _ = pixel_spacing_m(lat, 128, R)
    z = np.tile((np.arange(h) * dy * np.tan(np.radians(10.0)))[:, None], (1, w))  # 10 deg N-S plane
    s = slope_deg(z, lat, 128, R)
    assert np.allclose(s, 10.0, atol=1e-6)


def test_haversine_quarter_meridian():
    assert np.isclose(haversine_m(0, 0, 90, 0, R), np.pi * R / 2)


# Route generation and cost
def test_route_avoids_wall_and_cost_is_consistent():
    z = np.zeros((30, 30))
    z[5:25, 15] = 2000.0  # steep wall with a gap at rows 25-29
    g = flat_grid(z)
    # a 1-cell spike has zero central-difference slope at its peak; its flanks carry the slope and are excluded
    assert not g.passable[10, 14] and not g.passable[10, 16]
    S = np.zeros_like(z)
    c = cell_cost(g, S, "traversability")
    path, total = astar(g, c, (15, 2), (15, 28), MODES["traversability"]["beta"])
    assert all(g.passable[p] for p in path) and path[0] == (15, 2) and path[-1] == (15, 28)
    assert any(p[0] >= 25 or p[0] < 5 for p in path if p[1] == 15)
    prof, segs, stops, m = analyse(g, S, c, path, "traversability", [])
    assert np.isclose(sum(s["cost"] for s in segs), total, rtol=0.05) or np.isclose(m["total_cost"], total, atol=1)
    path2, total2 = astar(g, c, (15, 2), (15, 28), 1.0)
    assert path2 == path and total2 == total  # deterministic


def test_route_is_optimal_on_flat_grid():
    g = flat_grid(np.zeros((20, 20)))
    c = cell_cost(g, np.zeros((20, 20)), "traversability")
    path, total = astar(g, c, (0, 0), (0, 10), 1.0)
    assert len(path) == 11 and np.isclose(total, 10 * g.dx[0] * 1.0, rtol=1e-6)


def test_no_route_raises_clean_error():
    z = np.zeros((20, 20))
    z[:, 10] = 5000.0
    g = flat_grid(z)
    c = cell_cost(g, np.zeros_like(z), "balanced")
    with pytest.raises(DataError):
        astar(g, c, (5, 2), (5, 18), 1.0)


# Science proximity
def test_science_field_peaks_at_target():
    g = flat_grid(np.zeros((40, 40)))
    t = {"id": "x", "name": "x", "lat": float(g.lat[20]), "lon": float(g.lon[20]), "science": True, "status": "TEST"}
    S = science_field(g, [t])
    assert np.isclose(S[20, 20], 1.0) and S[20, 20] == S.max() and S[0, 0] < 0.01


def test_science_mode_moves_route_toward_target():
    g = flat_grid(np.zeros((40, 60)))
    # Target ~2.3 km off the straight line between start and destination.
    t = {
        "id": "x",
        "name": "x",
        "lat": float(g.lat[25]),
        "lon": float(g.lon[30]),
        "science": True,
        "status": "TEST",
    }
    S = science_field(g, [t])
    p_trav, _ = astar(g, cell_cost(g, S, "traversability"), (30, 2), (30, 57), 1.0)
    p_sci, _ = astar(g, cell_cost(g, S, "science"), (30, 2), (30, 57), 1.0)
    d = lambda p: min(abs(i - 25) + abs(j - 30) for i, j in p)
    assert d(p_sci) < d(p_trav)


# Provenance
def test_provenance_records_complete():
    rec = mola_record({"radius_m": R, "ppd": 128, "extent": {}}, [{"step": "read"}], synthetic=False)
    assert all(k in rec and rec[k] not in (None, "") for k in REQUIRED) and rec["status"] == "VERIFIED"
    syn = mola_record({}, [], synthetic=True)
    assert (
        syn["status"] == "SYNTHETIC" and not syn["source_url"].startswith("http") and "NOT NASA" in syn["source_name"]
    )


# Missing data
def test_missing_and_truncated_files(tmp_path):
    with pytest.raises(DataError):
        read_megdr(tmp_path / "nope.lbl")
    lbl = (FIXTURES / "megt_fixture.lbl").read_text()
    (tmp_path / "t.lbl").write_text(lbl.replace("MEGT_FIXTURE.IMG", "T.IMG"))
    (tmp_path / "t.img").write_bytes(b"\x00" * 100)
    with pytest.raises(DataError, match="truncated"):
        read_megdr(tmp_path / "t.lbl")


def test_nan_cells_are_impassable():
    z = np.zeros((10, 10))
    z[4, 4] = np.nan
    assert not flat_grid(z).passable[4, 4]


# API: the tests run against every server implementation installed here (FastAPI and/or the Starlette
# fallback) through an in-process ASGI client, so no httpx or network is needed.
_APPS = dict(available_apps())


@pytest.fixture(scope="module", params=list(_APPS))
def client(request):
    return Client(_APPS[request.param])


def test_compare_returns_three_explainable_routes(client):
    rs = client.post("/api/routes/compare", json={}).json()["routes"]
    assert [r["mode"] for r in rs] == list(MODES)
    for r in rs:
        assert r["geojson"]["geometry"]["type"] == "LineString" and len(r["segments"]) >= 2
        assert set(r["weights"]) == {"alpha", "beta", "gamma"}
        for s in r["segments"]:
            assert abs(sum(s["cost_breakdown"].values()) - 1) < 0.01


def test_api_endpoints(client):
    assert client.get("/api/health").json()["ok"]
    assert client.get("/api/regions").json()[0]["id"] == "jezero"
    prov = client.get("/api/layers").json()["layers"][0]["provenance"]
    real = client.get("/api/health").json()["data_mode"] == "NASA_PDS"
    assert prov["source_url"].startswith("https://pds-geosciences") == real  # PDS identity only for real PDS data
    assert (prov["status"] == "VERIFIED") == real
    assert client.get("/api/layers/nope").status_code == 404
    assert client.get("/api/science-targets").json()["type"] == "FeatureCollection"
    r = client.post("/api/routes", json={"mode": "balanced"}).json()
    assert client.get(f"/api/routes/{r['route_id']}").status_code == 200
    ev = client.get(f"/api/routes/{r['route_id']}/evidence", params={"segment": r["segments"][0]["id"]}).json()
    assert set(ev["sections"]) == {"TERRAIN", "SURFACE", "SCIENCE", "DATA", "METHOD", "PROVENANCE", "LIMITATION"}
    b = client.post("/api/crew-brief", json={"route_id": r["route_id"]}).json()
    assert b["title"] == "CREW ROUTE BRIEF" and b["sources"]
    bad = client.post("/api/routes", json={"mode": "fastest"})
    assert bad.status_code == 422 and "error" in bad.json() and "Traceback" not in bad.text
    out = client.get("/api/cell", params={"lat": 40, "lon": 77})
    assert out.status_code == 422 and "outside" in out.json()["error"]
    assert "unsafe" not in json.dumps(b).lower() and "safest" not in json.dumps(b).lower()


# Verification against the text of a real PDS label (megr44s090hb.lbl, from the PDS Geosciences Node).
def test_real_pds_label_geometry():
    lab = parse_label((Path(__file__).parent / "data" / "megr44s090hb.lbl").read_text())
    g = geometry_from_label(lab, "megr44s090hb.lbl")
    assert (g["lines"], g["samples"], g["ppd"]) == (5632, 11520, 128.0)
    assert (g["lat_max"], g["lat_min"], g["lon_w"], g["lon_e"]) == (-44.0, -88.0, 90.0, 180.0)
    assert g["radius_m"] == 3396000.0
    assert lab["IMAGE"]["SAMPLE_TYPE"] == "MSB_INTEGER" and lab["IMAGE"]["OFFSET"] == 3396000
    assert "interpolated value" in lab["IMAGE"]["DESCRIPTION"]


def test_route_ids_stops_and_brief(client):
    c = client.post("/api/routes/compare", json={}).json()
    letters = {r["mode"]: r["segments"][0]["id"][0] for r in c["routes"]}
    assert letters == {"traversability": "A", "science": "B", "balanced": "C"}
    assert all(s["id"][1] == "-" and len(s["id"]) == 4 for r in c["routes"] for s in r["segments"])
    for r in c["routes"]:
        assert [s["number"] for s in r["stops"]] == [f"{i:02d}" for i in range(1, len(r["stops"]) + 1)]
    assert len(c["differences"]) == 2 and all(d["facts"] and d["why"] for d in c["differences"])
    bal = next(r for r in c["routes"] if r["mode"] == "balanced")
    b = client.post("/api/crew-brief", json={"route_id": bal["route_id"]}).json()
    for k in ["mission", "route", "watch", "discover", "conditions", "evidence", "method", "uncertainty", "sources"]:
        assert k in b
    assert b["doc_id"].startswith("BRIEF-C")
    ev = client.get(f"/api/routes/{bal['route_id']}/evidence", params={"segment": bal["segments"][0]["id"]}).json()
    assert "A* optimality" in ev["decision"]
    meta = client.get("/api/metadata").json()
    assert [p["stage"] for p in meta["pipeline"]] == [
        "NASA DATA",
        "DATA HARMONIZATION",
        "FEATURE EXTRACTION",
        "SPATIAL ANALYSIS",
        "ROUTE GRAPH",
        "MULTI-OBJECTIVE PLANNING",
        "EXPLAINABLE EVIDENCE",
        "CREW BRIEF",
    ]
