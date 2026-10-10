"""Crew Route Brief: MISSION · ROUTE · WATCH · DISCOVER · CONDITIONS · EVIDENCE · METHOD · UNCERTAINTY · SOURCES.
Assembled only from computed route data and provenance records."""

from __future__ import annotations

import time

from ..config import MODES, STOP_RADIUS_M


def build_brief(store, route: dict, compare: list[dict] | None = None) -> dict:
    m, man = route["metrics"], store.manifest
    topo = man["layers"][0]["provenance"]
    synth = man["data_mode"] != "NASA_PDS"
    L = route["profile"][-1]["d_km"] or 1
    tgt = {t["id"]: t for t in man["targets"]}
    watch = [
        {
            "id": s["id"],
            "km": [
                round(route["profile"][s["from_vertex"]]["d_km"], 2),
                round(route["profile"][s["to_vertex"]]["d_km"], 2),
            ],
            "slope_max_deg": s["slope_max_deg"],
            "T_mean": s["T_mean"],
            "gain_m": s["gain_m"],
            "note": f"Higher modeled traversal cost — max slope {s['slope_max_deg']}°, relief {s['relief_mean_m']} m",
        }
        for s in route["segments"]
        if s["higher_cost"]
    ]
    discover = []
    for s in route["stops"]:
        t = tgt.get(s["target_id"], {})
        discover.append(
            {
                **s,
                "why": t.get("why"),
                "investigate": t.get("investigate"),
                "source": t.get("source"),
                "limitation": t.get("limitation"),
            }
        )
    alt = [
        {
            "mode": r["mode_label"],
            "letter": MODES[r["mode"]]["letter"],
            "length_km": r["metrics"]["length_km"],
            "slope_max_deg": r["metrics"]["slope_max_deg"],
            "candidate_stops": r["metrics"]["candidate_stops"],
            "higher_cost_segments": r["metrics"]["higher_cost_segments"],
        }
        for r in (compare or [])
        if r["route_id"] != route["route_id"]
    ]
    letter = MODES[route["mode"]]["letter"]
    strip = {
        "length_km": L,
        "segments": [
            {
                "id": s["id"],
                "from_km": route["profile"][s["from_vertex"]]["d_km"],
                "to_km": route["profile"][s["to_vertex"]]["d_km"],
                "higher_cost": s["higher_cost"],
            }
            for s in route["segments"]
        ],
        "stops": [{"label": s["label"], "at_km": s["at_km"]} for s in route["stops"]],
        "elev": [[p["d_km"], p["elev_m"]] for p in route["profile"][:: max(1, len(route["profile"]) // 80)]],
    }
    return {
        "title": "CREW ROUTE BRIEF",
        "doc_id": f"BRIEF-{letter} · MSC-{man['region']['id'].upper()}-{route['route_id'][:6].upper()}",
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "data_mode": man["data_mode"],
        "letter": letter,
        "classification": "PLANNING AID — NOT A SAFETY ASSESSMENT"
        + (" · SYNTHETIC TEST TERRAIN — NOT NASA DATA" if synth else ""),
        "mission": {
            "region": man["region"]["name"],
            "start": route["start"],
            "destination": route["dest"],
            "objective": MODES[route["mode"]]["intent"],
            "mode": route["mode_label"],
            "route": f"ROUTE {letter}",
        },
        "route": {
            "length_km": m["length_km"],
            "segments": m["segments"],
            "grid": f"{route['grid']['cell_deg']} {route['grid']['level']} grid ({route['grid']['status']})",
            "elev_gain_m": m["elev_gain_m"],
            "elev_loss_m": m["elev_loss_m"],
            "slope_mean_deg": m["slope_mean_deg"],
            "slope_max_deg": m["slope_max_deg"],
            "alternatives": alt,
            "strip": strip,
        },
        "watch": watch,
        "discover": discover,
        "conditions": [
            {
                "item": "Terrain epoch",
                "text": (
                    "Synthetic fixture: no observation epoch (generated data). Real MOLA observations date from 1999–2001."
                    if synth
                    else "MOLA observations 1999–2001; topography is treated as static."
                ),
                "status": "VERIFIED" if not synth else "SYNTHETIC",
            },
            {
                "item": "Measured vs interpolated ground",
                "text": (
                    f"{round(100 * m['interpolated_fraction'])}% of route cells have no MOLA shot (interpolated)."
                    if m.get("interpolated_fraction") is not None
                    else "Shot counts not loaded."
                ),
                "status": "DERIVED" if not synth else "SYNTHETIC",
            },
            {
                "item": "Thermal / surface-material context",
                "text": "THEMIS layer not integrated in this build.",
                "status": "CONCEPTUAL",
            },
            {
                "item": "Weather, dust, lighting",
                "text": "No MEDA files were provided, so no measured temperature, pressure or wind is shown. Not modeled. No real-time conditions are used anywhere.",
                "status": "CONCEPTUAL",
            },
        ],
        "evidence": [
            {
                "name": topo["source_name"],
                "detail": f"{topo['mission']} · {topo['instrument']} · {topo['product']}",
                "status": topo["status"],
            }
        ]
        + [
            {"name": l["name"], "detail": l["provenance"]["product"], "status": l["provenance"]["status"]}
            for l in man["layers"][1:]
        ],
        "method": [
            f"{route['grid']['algorithm']} on the {route['grid']['cell_deg']} {route['grid']['level']} grid "
            f"({route['grid']['method'] if route['grid']['level'] != 'native' else 'source cells'}) — 8-connected, spherical step lengths, optimal and deterministic.",
            f"Slope evidence also read along the path on the {route['grid']['evidence_grid']} analysis grid (max {m.get('slope_max_deg_analysis')}°). Finer grids are interpolated and add no terrain detail.",
            f"Cell cost c = β + α·T + γ·(1−S) with α={route['weights']['alpha']}, β={route['weights']['beta']}, γ={route['weights']['gamma']} ({route['mode_label']}).",
            f"Candidate science stop = target within {STOP_RADIUS_M:.0f} m of the route.",
        ],
        "uncertainty": [
            "Terrain source resolution ~463 m per cell (1/128°); the finer route grid is interpolated, so metre-scale obstacles (boulders, small craters) are still not represented.",
            "No orbital imagery (CTX, HiRISE) or composition data (CRISM) integrated; the SURFACE layer is shaded relief computed from the same elevation grid.",
            "Cost-model weights are configurable assumptions, not human mobility limits.",
            "Candidate science targets come from published descriptions or derived topography — not new detections.",
            "Target positions marked APPROXIMATE are placements, not surveyed points.",
        ]
        + (
            ["SYNTHETIC TEST TERRAIN: every terrain number in this brief is from the synthetic fixture, not NASA data."]
            if synth
            else []
        ),
        "sources": [
            {
                "name": topo["source_name"],
                "archive": topo["archive"],
                "url": topo["source_url"],
                "credit": topo["credit"],
                "retrieved": topo["retrieval_date"],
            }
        ]
        + [
            {"name": t["name"], "archive": t.get("source"), "url": t.get("source_url"), "status": t["status"]}
            for t in man["targets"]
        ],
    }


def route_differences(routes: list[dict]) -> list[dict]:
    """Plain-language, computed differences of each route relative to BALANCED (answers 'why did they differ?')."""
    base = next((r for r in routes if r["mode"] == "balanced"), routes[0])
    out = []
    for r in routes:
        if r is base:
            continue
        a, b = r["metrics"], base["metrics"]
        d = lambda k: (a[k] or 0) - (b[k] or 0)
        parts = [
            f"{abs(d('length_km')):.2f} km {'longer' if d('length_km') > 0 else 'shorter'}",
            f"mean terrain cost T {a['T_mean']} vs {b['T_mean']}",
            f"mean science proximity S {a['S_mean']} vs {b['S_mean']}",
            f"{a['candidate_stops']} vs {b['candidate_stops']} candidate stops",
        ]
        why = (
            "γ = 0, so distance from science costs nothing and only terrain (α) and distance (β) shape the path."
            if r["mode"] == "traversability"
            else "γ is higher, so cells far from candidate science cost more and the path is pulled toward targets."
        )
        out.append(
            {
                "mode": r["mode_label"],
                "letter": MODES[r["mode"]]["letter"],
                "vs": base["mode_label"],
                "facts": parts,
                "why": why,
                "shared_cells_pct": round(
                    100
                    * len(
                        {(p["lat"], p["lon"]) for p in r["profile"]} & {(p["lat"], p["lon"]) for p in base["profile"]}
                    )
                    / max(1, len(r["profile"]))
                ),
            }
        )
    return out
