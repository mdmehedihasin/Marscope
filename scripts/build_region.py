#!/usr/bin/env python3
"""Pipeline: read MEGDR -> validate -> clip ROI (no resampling) -> derive slope/relief/hillshade
-> derive rim target -> render layer PNGs -> write data/processed/<region>/ with full provenance.

  python scripts/build_region.py            # uses real MOLA in data/raw if present, else the synthetic fixture
  python scripts/build_region.py --fixture  # force the synthetic fixture
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import (  # noqa: E402
    FIXTURES,
    MODES,
    MOLA_COUNT_TILE,
    MOLA_TOPO_TILE,
    PATH_SOL_PROPERTY,
    PROCESSED,
    RAW,
    REGION,
    SCIENCE_SIGMA_M,
    TARGETS,
    TERRAIN,
)
from app.geospatial.levels import LEVELS, build_level, level_description, slope_stats  # noqa: E402
from app.geospatial.terrain import haversine_m, hillshade, local_relief_m, slope_deg  # noqa: E402
from app.ingestion.local_inventory import inventory  # noqa: E402
from app.ingestion.pds3 import DataError, clip, read_megdr  # noqa: E402
from app.ingestion.traverse import illustrative_path, load_real_path  # noqa: E402
from app.provenance.registry import UNAVAILABLE, derived_record, grid_record, mola_record  # noqa: E402

SURFACE_SHADE = {"azimuth": 315.0, "altitude": 45.0, "exaggeration": 3.0}  # display settings for the SURFACE layer
DISCLOSURE = "Pre-event concept prototype, not work produced during the official hackathon (Nov 14-15, 2026)."


def ramp(v, stops):
    """Piecewise-linear colour ramp; stops = [(t, (r,g,b,a)), ...] with t in [0,1]."""
    v = np.clip(v, 0, 1)
    out = np.zeros(v.shape + (4,))
    ts = [s[0] for s in stops]
    for c in range(4):
        out[..., c] = np.interp(v, ts, [s[1][c] for s in stops])
    return out.astype(np.uint8)


def save(arr, path):
    Image.fromarray(arr, "RGBA").save(path, optimize=True)


def main():
    force_fixture = "--fixture" in sys.argv
    real = RAW / f"{MOLA_TOPO_TILE}.lbl"
    synthetic = force_fixture or not real.exists()
    topo_lbl = FIXTURES / "megt_fixture.lbl" if synthetic else real
    cnt_lbl = FIXTURES / "megc_fixture.lbl" if synthetic else RAW / f"{MOLA_COUNT_TILE}.lbl"
    if synthetic and not topo_lbl.exists():
        raise SystemExit("No data. Run scripts/fetch_mola.py (real) or scripts/make_fixture.py (synthetic test).")
    print(("SYNTHETIC FIXTURE MODE — NOT NASA DATA" if synthetic else "REAL MOLA MEGDR") + f": {topo_lbl.name}")
    retrieved = None
    log = RAW / "retrieval_log.json"
    if not synthetic and log.exists():
        retrieved = json.loads(log.read_text()).get(MOLA_TOPO_TILE, {}).get("retrieved")

    r = read_megdr(topo_lbl)
    steps = [
        {
            "step": "read",
            "file": r.meta["image"],
            "bytes": r.meta["bytes"],
            "lines": r.meta["lines"],
            "samples": r.meta["samples"],
            "sample_type": r.meta["sample_type"],
            "validation": "file size and map extents checked against label",
        }
    ]
    roi = (REGION["lat_min"], REGION["lat_max"], REGION["lon_min"], REGION["lon_max"])
    rc, st = clip(r, *roi)
    steps.append(st)
    counts, cstep = None, None
    if cnt_lbl.exists():
        c = read_megdr(cnt_lbl)
        cc, cstep = clip(c, *roi)
        if (cc.ppd, cc.lat_max, cc.lon_west, cc.shape) != (rc.ppd, rc.lat_max, rc.lon_west, rc.shape):
            raise DataError("Counts tile is not aligned with the topography grid")
        counts = cc.data
        steps.append(
            {"step": "align", "note": "shot-count grid verified identical to topography grid (same ppd, origin, shape)"}
        )
    z = rc.data
    lat = rc.lat_of_row(np.arange(z.shape[0]))
    slope = slope_deg(z, lat, rc.ppd, rc.radius_m)
    relief = local_relief_m(z, 3)
    hs = hillshade(z, lat, rc.ppd, rc.radius_m)
    steps.append(
        {
            "step": "derive",
            "note": "slope = atan(|grad z|) by central differences with dx = dy*cos(lat); relief = 3x3 max-min; hillshade az 315°, alt 45°, 3x vertical exaggeration (display only)",
        }
    )

    # Interpolated routing (1/512°) and analysis (1/1024°) grids. They add NO terrain information.
    lv = {
        name: build_level(z, counts, rc.lat_max, rc.lon_west, rc.ppd, rc.radius_m, f, with_relief=(name != "analysis"))
        for name, f in LEVELS.items()
        if f > 1
    }
    lat_mid = float(lat.mean())
    level_info = {name: level_description(name, f, rc.ppd, rc.radius_m, lat_mid) for name, f in LEVELS.items()}
    slope_by_level = {"native": slope_stats(slope, TERRAIN["max_slope_deg"])}
    slope_by_level.update({name: slope_stats(v["slope"], TERRAIN["max_slope_deg"]) for name, v in lv.items()})
    for name in slope_by_level:
        slope_by_level[name].update(
            {"cell_deg": level_info[name]["cell_deg"], "cell_ns_m": level_info[name]["cell_ns_m"]}
        )
    steps.append(
        {
            "step": "resample",
            "note": "routing grid 1/512° and analysis grid 1/1024°: "
            + level_info["routing"]["method"]
            + ". Built at start-up from grid.npz; finer spacing does not add terrain information.",
        }
    )

    # Targets: load them, then derive the west rim crest from the terrain.
    tdoc = json.loads((TARGETS / f"{REGION['id']}_targets.json").read_text())
    targets = tdoc["targets"]
    c_lat, c_lon = REGION["crater_center"]
    st_t = next(t for t in targets if t["role"] == "start")
    km_lat = np.pi * rc.radius_m / 180 / 1000
    vy = (st_t["lat"] - c_lat) * km_lat
    vx = (st_t["lon"] - c_lon) * km_lat * np.cos(np.radians(c_lat))
    n = np.hypot(vx, vy)
    vx, vy = vx / n, vy / n
    best = None
    for frac in np.linspace(0.7, 1.35, 140):
        d = frac * REGION["crater_radius_km"]
        la = c_lat + vy * d / km_lat
        lo = c_lon + vx * d / (km_lat * np.cos(np.radians(c_lat)))
        i, j = int(rc.row_of_lat(la) + 0.5), int(rc.col_of_lon(lo) + 0.5)
        if 0 <= i < z.shape[0] and 0 <= j < z.shape[1] and np.isfinite(z[i, j]) and (best is None or z[i, j] > best[0]):
            best = (float(z[i, j]), float(rc.lat_of_row(i)), float(rc.lon_of_col(j)), frac)
    rim = {
        "id": "west_rim",
        "name": "Jezero west rim crest (derived)",
        "lat": round(best[1], 4),
        "lon": round(best[2], 4),
        "role": "destination",
        "science": True,
        "status": "SYNTHETIC" if synthetic else "DERIVED",
        "source": f"Highest {'synthetic-fixture' if synthetic else 'MOLA'} elevation ({best[0]:.0f} m) sampled along the azimuth from the crater centre through the landing site, "
        f"between 0.70 and 1.35 crater radii (found at {best[3]:.2f} R).",
        "source_url": "derived from " + ("synthetic fixture" if synthetic else f"MOLA {MOLA_TOPO_TILE}"),
        "why": "Impact-crater rims expose material uplifted from depth; a rim position also gives the crew a regional overview.",
        "investigate": "Rim-forming rock types and their relation to crater-floor and delta deposits.",
        "limitation": (
            "Located on SYNTHETIC terrain: this point is a pipeline demonstration, not the real rim crest. "
            if synthetic
            else ""
        )
        + "Located from ~463 m topography only; the exact crest and access path need HiRISE-scale data.",
    }
    targets = [t for t in targets if t["id"] != "west_rim"] + [rim]
    if synthetic:
        for t in targets:
            t["fixture_note"] = "Shown on SYNTHETIC terrain — terrain values near this point are not real."

    # Science proximity (for the layer image only).
    LA, LO = np.meshgrid(lat, rc.lon_of_col(np.arange(z.shape[1])), indexing="ij")
    S = np.zeros_like(z)
    for t in targets:
        if t.get("science"):
            S = np.maximum(
                S, np.exp(-haversine_m(LA, LO, t["lat"], t["lon"], rc.radius_m) ** 2 / (2 * SCIENCE_SIGMA_M**2))
            )
    tc = TERRAIN
    rg = lv["routing"]
    T = tc["w_slope"] * np.minimum(1, rg["slope"] / tc["slope_ref_deg"]) ** 2 + tc["w_relief"] * np.minimum(
        1, rg["relief"] / tc["relief_ref_m"]
    )

    out = PROCESSED / REGION["id"]
    (out / "layers").mkdir(parents=True, exist_ok=True)
    zf = np.where(np.isfinite(z), z, np.nanmean(z))
    zmin, zmax = float(np.nanpercentile(z, 1)), float(np.nanpercentile(z, 99))
    zn = (zf - zmin) / (zmax - zmin)
    base = ramp(
        zn, [(0, (52, 30, 22, 255)), (0.45, (142, 72, 42, 255)), (0.8, (200, 140, 96, 255)), (1, (236, 214, 180, 255))]
    ).astype(float)
    shade = (0.35 + 0.85 * hs)[..., None]
    base[..., :3] = np.clip(base[..., :3] * shade, 0, 255)
    save(base.astype(np.uint8), out / "layers" / "terrain.png")
    smax = max(20.0, float(np.nanpercentile(rg["slope"], 99.5)))
    save(
        ramp(
            rg["slope"] / smax,
            [(0, (224, 168, 74, 0)), (0.15, (224, 168, 74, 40)), (0.5, (224, 168, 74, 170)), (1, (200, 70, 40, 235))],
        ),
        out / "layers" / "slope.png",
    )
    save(
        ramp(
            T, [(0, (224, 168, 74, 0)), (0.2, (224, 168, 74, 60)), (0.6, (210, 110, 50, 180)), (1, (180, 50, 35, 235))]
        ),
        out / "layers" / "cost.png",
    )
    save(
        ramp(S, [(0, (116, 214, 210, 0)), (0.3, (116, 214, 210, 50)), (1, (150, 235, 230, 190))]),
        out / "layers" / "science.png",
    )
    # SURFACE layer: shaded relief computed from the elevation grid (no local imagery).
    an = lv["analysis"]
    lat_an = rc.lat_max - (np.arange(an["z"].shape[0]) + 0.5) / an["ppd"]
    hs_an = hillshade(
        an["z"],
        lat_an,
        an["ppd"],
        rc.radius_m,
        azimuth=SURFACE_SHADE["azimuth"],
        altitude=SURFACE_SHADE["altitude"],
        exaggeration=SURFACE_SHADE["exaggeration"],
    )
    g8 = np.clip(40 + 200 * hs_an, 0, 255).astype(np.uint8)
    surf = np.dstack([g8, g8, g8, np.full_like(g8, 255)])
    save(surf, out / "layers" / "surface.png")
    surface_bytes = (out / "layers" / "surface.png").stat().st_size
    if counts is not None:
        cov = np.zeros(z.shape + (4,), np.uint8)
        cov[counts == 0] = (236, 230, 220, 120)
        save(cov, out / "layers" / "coverage.png")

    b = rc.bounds()
    # Perseverance path slot: real local file if present, else a labelled illustration.
    overlays = []
    real_path = RAW / "m20" / "M20_traverse.json"
    if real_path.exists():
        rp = load_real_path(real_path, rc.radius_m, b, PATH_SOL_PROPERTY)
        overlays.append(
            {
                "id": "perseverance_path",
                "kind": "real",
                "name": "Perseverance traverse (local copy)",
                "lines": rp["lines"],
                "default": False,
                "check": {
                    "coordinate_convention": rp["convention"],
                    "in_region_share": rp["in_region_share"],
                    "vertices": rp["vertices"],
                    "sol_range": rp["sol_range"],
                    "local_copy_date": time.strftime("%Y-%m-%d", time.localtime(real_path.stat().st_mtime)),
                },
                "provenance": {
                    "id": "perseverance_path",
                    "source_name": "Perseverance traverse — NASA Mars 2020 location map (local copy)",
                    "mission": "Mars 2020 (NASA)",
                    "instrument": "rover localization (NASA/JPL-Caltech)",
                    "product": "M20_traverse.json",
                    "source_url": "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json",
                    "archive": "unofficial endpoint of the NASA location-map page; local copy in data/raw/m20/",
                    "spatial_reference": f"GeoJSON; convention detected: {rp['convention']['convention']}",
                    "coverage": "full path; in-region share computed",
                    "resolution": "vertex list",
                    "retrieval_date": time.strftime("%Y-%m-%d", time.localtime(real_path.stat().st_mtime))
                    + " (file date of the local copy)",
                    "processing_steps": [
                        "read GeoJSON geometry only (no property names assumed)",
                        f"coordinate convention checked against Butler Landing: nearest vertex {rp['convention']['nearest_to_reference_km']} km",
                        f"in-region length share {rp['in_region_share']:.1%}",
                    ],
                    "credit": "NASA/JPL-Caltech",
                    "notes": "Descriptive display only; no metrics are computed from it in this build.",
                    "limitations": [
                        "Unofficial endpoint; keep a dated local copy",
                        "Display only — not used to judge route safety or accuracy",
                    ],
                    "status": "VERIFIED",
                },
            }
        )
    else:
        overlays.append(
            {
                "id": "perseverance_path",
                "kind": "illustrative",
                "name": "Synthetic illustrative path — not rover data",
                "lines": [illustrative_path(b)],
                "default": False,
                "provenance": {
                    "id": "perseverance_path",
                    "source_name": "Synthetic illustrative path — not rover data",
                    "mission": "none (synthetic)",
                    "instrument": "none",
                    "product": "schematic sine-wave polyline for interface testing",
                    "source_url": "generated — backend/app/ingestion/traverse.py: illustrative_path()",
                    "archive": "none",
                    "spatial_reference": "lat/lon, inside the region bounds",
                    "coverage": "northern band of the map; deliberately away from the landing site",
                    "resolution": "60 vertices",
                    "retrieval_date": time.strftime("%Y-%m-%d"),
                    "processing_steps": ["deterministic sine wave between fixed points inside the map bounds"],
                    "credit": "MARSCOPE (not NASA)",
                    "notes": "Tests the map's path slot until a real local file (data/raw/m20/M20_traverse.json) is added.",
                    "limitations": [
                        "NOT the Perseverance path",
                        "No rover metrics are computed or shown",
                        "Its position and shape carry no meaning",
                    ],
                    "status": "SYNTHETIC",
                },
            }
        )
    mola = mola_record({**r.meta, "retrieved": retrieved or time.strftime("%Y-%m-%d")}, steps, synthetic)
    layers = [
        {
            "id": "terrain",
            "name": "Terrain (" + ("synthetic fixture" if synthetic else "MOLA") + " elevation + hillshade, 1/128°)",
            "png": "terrain.png",
            "default": True,
            "smooth": True,
            "legend": {
                "type": "ramp",
                "min": round(zmin),
                "max": round(zmax),
                "unit": "m (rel. areoid)",
                "colors": ["#34201a", "#8e482a", "#c88c60", "#ecd6b4"],
            },
            "provenance": mola,
        },
        {
            "id": "surface",
            "name": "Shaded relief (computed from elevation — not imagery)",
            "png": "surface.png",
            "smooth": True,
            "legend": {
                "type": "ramp",
                "min": 0,
                "max": 1,
                "unit": "illumination (az 315°, alt 45°)",
                "colors": ["#282828", "#e8e8e8"],
            },
            "provenance": derived_record(
                "surface",
                "Shaded relief " + ("of the SYNTHETIC fixture terrain" if synthetic else "of MOLA terrain"),
                f"hillshade = cos(angle between surface normal and a sun at azimuth {SURFACE_SHADE['azimuth']:.0f}°, "
                f"altitude {SURFACE_SHADE['altitude']:.0f}°), {SURFACE_SHADE['exaggeration']:g}x vertical exaggeration, on the 1/1024° analysis grid",
                ["elevation on the 1/1024° analysis grid (cubic interpolation of the 1/128° source grid)"],
                "0–1 illumination",
                [
                    "This is NOT an orbital photograph and NOT CTX or HiRISE imagery",
                    "It shows the same elevation data as light and shadow; it adds no new evidence",
                    f"Vertical exaggeration {SURFACE_SHADE['exaggeration']:g}x is for display only",
                    "Source information is ~463 m; the 1/1024° pixel size is interpolation",
                ],
                synthetic,
                resolution=f"{an['z'].shape[1]} x {an['z'].shape[0]} px at 1/1024° (~58 m); source 1/128° (~463 m)",
                spatial_reference="1/1024° lat/lon grid, exactly the same bounds as the native grid",
                steps=[
                    "cubic interpolation of the native grid to 1/1024°",
                    "hillshade (az 315°, alt 45°)",
                    f"8-bit greyscale PNG, {surface_bytes/1e6:.2f} MB",
                ],
            ),
        },
        {
            "id": "slope",
            "name": "Slope (1/512° routing grid)",
            "png": "slope.png",
            "legend": {
                "type": "ramp",
                "min": 0,
                "max": round(smax, 1),
                "unit": "degrees",
                "colors": ["#e0a84a00", "#e0a84aaa", "#c84628"],
            },
            "provenance": derived_record(
                "slope",
                "Slope " + ("from the synthetic fixture" if synthetic else "from MOLA"),
                "slope = atan(sqrt((dz/dx)^2 + (dz/dy)^2)), central differences, dx = dy*cos(lat), on the 1/512° routing grid",
                ["elevation on the 1/512° routing grid (cubic interpolation of the 1/128° source grid)"],
                "degrees",
                [
                    "Source information is ~463 m; the 116 m grid spacing is interpolation, not new detail",
                    "Slope values depend on grid spacing (see docs/SCIENTIFIC_METHOD.md)",
                ],
                synthetic,
                resolution=f"{level_info['routing']['cell_deg']} grid spacing (~{level_info['routing']['cell_ns_m']:.0f} m); source 1/128° (~463 m)",
                spatial_reference="1/512° lat/lon grid, same bounds as the native grid",
            ),
        },
        {
            "id": "cost",
            "name": "Modeled terrain cost T (routing grid)",
            "png": "cost.png",
            "legend": {
                "type": "ramp",
                "min": 0,
                "max": 1,
                "unit": "dimensionless",
                "colors": ["#e0a84a00", "#d26e32b4", "#b43223"],
            },
            "provenance": derived_record(
                "cost",
                "Modeled terrain cost",
                f"T = {tc['w_slope']}*min(1,slope/{tc['slope_ref_deg']}°)^2 + {tc['w_relief']}*min(1,relief/{tc['relief_ref_m']} m)",
                ["slope", f"local relief ({level_info['routing']['relief_window']})"],
                "0–1",
                ["Weights and reference values are ASSUMPTIONS", "Not a safety or hazard score"],
                synthetic,
                resolution=f"{level_info['routing']['cell_deg']} routing grid",
                spatial_reference="1/512° lat/lon grid, same bounds as the native grid",
            ),
        },
        {
            "id": "science",
            "name": "Science proximity S",
            "png": "science.png",
            "legend": {
                "type": "ramp",
                "min": 0,
                "max": 1,
                "unit": "dimensionless",
                "colors": ["#74d6d200", "#96ebe6be"],
            },
            "provenance": derived_record(
                "science",
                "Science proximity",
                f"S = max_k exp(-d_k^2 / (2*{SCIENCE_SIGMA_M:.0f} m^2)) over candidate science targets",
                ["candidate science targets (see Sources)"],
                "0–1",
                [
                    "Depends on the target list, not on spectral data",
                    f"sigma = {SCIENCE_SIGMA_M:.0f} m is an ASSUMPTION",
                ],
                synthetic,
            ),
        },
    ]
    if counts is not None:
        layers.append(
            {
                "id": "coverage",
                "name": ("Shot-count coverage (synthetic gaps)" if synthetic else "MOLA coverage (interpolated bins)"),
                "png": "coverage.png",
                "legend": {"type": "swatch", "label": "0 shots in bin (interpolated)", "colors": ["#ece6dc78"]},
                "provenance": {**mola_record(r.meta, [cstep or {}], synthetic, "counts"), "id": "mola_counts"},
            }
        )
    manifest = {
        "data_mode": "SYNTHETIC_FIXTURE" if synthetic else "NASA_PDS",
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "region": {**REGION, "bounds": b, "shape": list(z.shape), "ppd": rc.ppd, "radius_m": rc.radius_m},
        "layers": layers,
        "targets": targets,
        "unavailable": UNAVAILABLE,
        "disclosure": DISCLOSURE,
        "grid_records": [grid_record(level_info[k], synthetic) for k in ("routing", "analysis")],
        "slope_by_level": slope_by_level,
        "overlays": overlays,
        "local_inventory": inventory(RAW, checksums=False),
        "assumptions": {"terrain": TERRAIN, "modes": MODES, "science_sigma_m": SCIENCE_SIGMA_M},
        "stats": {
            "elev_min_m": round(float(np.nanmin(z)), 1),
            "elev_max_m": round(float(np.nanmax(z)), 1),
            "slope_max_deg": round(float(np.nanmax(slope)), 2),
            "slope_p95_deg": round(float(np.nanpercentile(slope, 95)), 2),
            "interpolated_fraction": None if counts is None else round(float((counts == 0).mean()), 3),
            "excluded_cells": int((slope > TERRAIN["max_slope_deg"]).sum()),
            "excluded_cells_routing": slope_by_level["routing"]["cells_above_limit"],
        },
    }
    np.savez_compressed(
        out / "grid.npz",
        z=z,
        slope=slope,
        relief=relief,
        counts=(counts if counts is not None else np.full(z.shape, -1)),
        lat_max=rc.lat_max,
        lon_west=rc.lon_west,
        ppd=rc.ppd,
        radius_m=rc.radius_m,
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(
        f"wrote {out}: grid {z.shape}, elev {manifest['stats']['elev_min_m']}..{manifest['stats']['elev_max_m']} m, "
        f"slope max {manifest['stats']['slope_max_deg']}°, rim at {rim['lat']},{rim['lon']}"
    )
    for k, v in slope_by_level.items():
        print(
            f"  slope {k:8s} {v['cell_deg']:>8s}: mean {v['mean_deg']}°  p95 {v['p95_deg']}°  p99 {v['p99_deg']}°  max {v['max_deg']}°  >{TERRAIN['max_slope_deg']}°: {v['cells_above_limit']} cells"
        )


if __name__ == "__main__":
    try:
        main()
    except DataError as e:
        raise SystemExit(f"DATA ERROR: {e}")
