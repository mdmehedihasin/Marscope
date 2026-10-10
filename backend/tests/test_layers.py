"""Surface layer labelling, delta-front status, Perseverance path slot and absent sources."""

import json

import numpy as np
import pytest
from PIL import Image

from app.api.asgi_client import Client, available_apps
from app.config import PROCESSED, REGION
from app.geospatial.terrain import haversine_m
from app.ingestion.local_inventory import inventory
from app.ingestion.pds3 import DataError
from app.ingestion.traverse import (
    BUTLER_REF,
    detect_convention,
    illustrative_path,
    in_region_share,
    load_real_path,
    sol_range,
)

R = 3_396_000.0
MAN = json.loads((PROCESSED / REGION["id"] / "manifest.json").read_text())
SYN = MAN["data_mode"] != "NASA_PDS"


def layer(i):
    return next(l for l in MAN["layers"] if l["id"] == i)


def test_surface_layer_is_shaded_relief_not_imagery():
    s = layer("surface")
    p = s["provenance"]
    assert p["status"] == ("SYNTHETIC" if SYN else "DERIVED")
    assert any("NOT an orbital photograph" in x for x in p["limitations"])
    img = Image.open(PROCESSED / REGION["id"] / "layers" / "surface.png")
    h, w = MAN["region"]["shape"]
    assert img.size == (w * 8, h * 8)  # exactly the analysis grid → same bounds
    assert (PROCESSED / REGION["id"] / "layers" / "surface.png").stat().st_size < 3_000_000


def test_no_layer_claims_ctx_or_verified_in_synthetic_mode():
    for l in MAN["layers"]:
        assert "CTX" not in l["provenance"]["source_name"]
        if SYN:
            assert l["provenance"]["status"] != "VERIFIED"
    for g in MAN["grid_records"]:
        assert g["status"] in ("SYNTHETIC", "APPROXIMATE")


def test_delta_front_stays_approximate_with_offline_note():
    t = next(t for t in MAN["targets"] if t["id"] == "delta_front")
    assert t["status"] == "APPROXIMATE" and "Not refined" in t["offline_review"]
    assert (t["lat"], t["lon"]) == (18.465, 77.415)  # unchanged from the original placement


def test_illustrative_path_is_synthetic_and_away_from_landing_site():
    o = next(o for o in MAN["overlays"] if o["id"] == "perseverance_path")
    if o["kind"] != "illustrative":
        pytest.skip("a real local path file is present")
    assert o["provenance"]["status"] == "SYNTHETIC" and "not rover data" in o["name"]
    pts = np.array(o["lines"][0])
    b = MAN["region"]["bounds"]
    assert (pts[:, 1] > b["lat_min"]).all() and (pts[:, 1] < b["lat_max"]).all()
    assert (pts[:, 0] > b["lon_min"]).all() and (pts[:, 0] < b["lon_max"]).all()
    d = haversine_m(pts[:, 1], pts[:, 0], BUTLER_REF[0], BUTLER_REF[1], R)
    assert d.min() > 15_000  # never starts at / touches Butler Landing
    assert "metrics" not in o and "length_km" not in json.dumps(o)


@pytest.mark.parametrize(
    "conv,make",
    [
        ("geojson_lon_lat_east", lambda la, lo: [lo, la]),
        ("geojson_lon_lat_west_positive", lambda la, lo: [360 - lo, la]),
        ("swapped_lat_lon_east", lambda la, lo: [la, lo]),
    ],
)
def test_path_coordinate_convention_detection(conv, make):
    pts = [tuple(make(18.4447 + 0.001 * k, 77.4508 + 0.002 * k)) for k in range(5)]
    c = detect_convention(pts, R)
    assert c["convention"] == conv and c["nearest_to_reference_km"] < 0.01


def test_path_far_from_landing_site_is_rejected():
    with pytest.raises(DataError):
        detect_convention([(10.0, 5.0), (10.1, 5.1)], R)


def test_load_real_path_from_small_local_geojson(tmp_path):
    f = tmp_path / "M20_traverse.json"
    f.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[77.4508, 18.4447], [77.46, 18.45], [77.47, 18.46]],
                        },
                    }
                ],
            }
        )
    )
    p = load_real_path(f, R, MAN["region"]["bounds"])
    assert p["convention"]["convention"] == "geojson_lon_lat_east" and p["in_region_share"] == 1.0
    assert p["lines"][0][0] == [77.4508, 18.4447]


def test_sol_range_only_when_a_person_sets_the_key():
    doc = {"features": [{"properties": {"k_test": 5}}, {"properties": {"k_test": 9}}, {"properties": {}}]}
    assert sol_range(doc, None) is None and sol_range(doc, "k_test") == [5, 9] and sol_range(doc, "absent") is None


def test_in_region_share_half_outside():
    b = {"lat_min": 0, "lat_max": 1, "lon_min": 0, "lon_max": 1}
    assert abs(in_region_share([0.5, 0.5, 0.5], [0.2, 0.8, 1.4], b, R) - 0.5) < 0.01


def test_inventory_reports_missing_and_present(tmp_path):
    inv = {e["id"]: e for e in inventory(tmp_path)}
    assert not any(e["present"] for e in inv.values())
    (tmp_path / "m20").mkdir()
    (tmp_path / "m20" / "M20_traverse.json").write_text("{}")
    inv = {e["id"]: e for e in inventory(tmp_path)}
    assert inv["m20_traverse"]["present"] and inv["m20_traverse"]["files"][0]["sha256"]


def test_absent_sources_stay_unavailable_or_conceptual():
    un = {u["id"]: u["status"] for u in MAN["unavailable"]}
    present = {e["id"]: e["present"] for e in MAN["local_inventory"]}
    if not present["crism"]:
        assert un["crism"] == "DATA_UNAVAILABLE" and not any("mineral" in l["id"] for l in MAN["layers"])
    if not present["meda"]:
        assert un["weather"] == "CONCEPTUAL"
    assert un["global"] == "CONCEPTUAL" and un["ctx"] == "DATA_UNAVAILABLE"


def test_brief_conditions_show_no_invented_measurements():
    c = Client(dict(available_apps())["lite"])
    r = c.post("/api/routes", json={"mode": "balanced"}).json()
    b = c.post("/api/crew-brief", json={"route_id": r["route_id"]}).json()
    cond = {x["item"]: x for x in b["conditions"]}
    assert cond["Weather, dust, lighting"]["status"] == "CONCEPTUAL"
    txt = json.dumps(b["conditions"])
    for unit in ("°C", " K ", " Pa", "m/s", "sol "):
        assert unit not in txt
    ov = c.get("/api/overlays").json()["overlays"]
    assert ov and ov[0]["id"] == "perseverance_path"


def test_illustrative_generator_is_deterministic():
    b = MAN["region"]["bounds"]
    assert illustrative_path(b) == illustrative_path(b)
