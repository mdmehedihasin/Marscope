"""Inventory of local source files (offline). Lists what is present in data/raw/ and what is missing.
Nothing is downloaded. File names are those of the intended sources listed in docs/DATA.md."""

from __future__ import annotations

import hashlib
from pathlib import Path

EXPECTED = [
    {
        "id": "mola_topo",
        "name": "MOLA MEGDR topography tile megt44n045hb",
        "paths": ["megt44n045hb.lbl", "megt44n045hb.img"],
        "integration": "Integrated automatically (scripts/build_region.py) → terrain becomes VERIFIED, slope/hillshade DERIVED.",
    },
    {
        "id": "mola_counts",
        "name": "MOLA MEGDR shot counts megc44n045hb",
        "paths": ["megc44n045hb.lbl", "megc44n045hb.img"],
        "integration": "Integrated automatically → real coverage layer.",
    },
    {
        "id": "ctx_dem",
        "name": "CTX DEM 20 m (USGS / NASA JPL)",
        "paths": ["ctx/M20_JezeroCrater_CTXDEM_20m.tif"],
        "integration": "Not integrated in this build (needs a GeoTIFF reader such as rasterio). Planned.",
    },
    {
        "id": "ctx_ortho",
        "name": "CTX orthomosaic 5 m (USGS / NASA JPL)",
        "paths": ["ctx/M20_JezeroCrater_CTXortho_mosaic_5m.tif"],
        "integration": "Not integrated in this build (needs a GeoTIFF reader). Planned.",
    },
    {
        "id": "m20_traverse",
        "name": "Perseverance traverse (NASA Mars 2020 location map)",
        "paths": ["m20/M20_traverse.json"],
        "integration": "Integrated automatically if present (GeoJSON geometry only, Butler Landing convention check).",
    },
    {
        "id": "m20_waypoints",
        "name": "Perseverance waypoints (NASA Mars 2020 location map)",
        "paths": ["m20/M20_waypoints.json"],
        "integration": "Integrated automatically if present (as points).",
    },
    {
        "id": "crism",
        "name": "CRISM-derived mineral map jezeroFinal.tif + readme (Zenodo 5575824)",
        "paths": ["crism/jezeroFinal.tif", "crism/README*"],
        "integration": "Not integrated in this build: classes must be mapped from the readme by a person. Stays DATA_UNAVAILABLE.",
    },
    {
        "id": "meda",
        "name": "Mars 2020 MEDA files with .xml labels",
        "paths": ["meda/*.xml"],
        "integration": "Not integrated in this build: column names/units must come from the labels. Conditions stay CONCEPTUAL.",
    },
    {
        "id": "basemap",
        "name": "Global Mars basemap (local file)",
        "paths": ["basemap/*"],
        "integration": "Not integrated. The global view is a CONCEPTUAL schematic.",
    },
]


def _sha256(p: Path, limit_mb: int = 2048) -> str | None:
    if p.stat().st_size > limit_mb * 1_000_000:
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def inventory(raw_dir: Path, checksums: bool = True) -> list[dict]:
    raw_dir = Path(raw_dir)
    out = []
    for e in EXPECTED:
        files = []
        for pat in e["paths"]:
            files += [p for p in sorted(raw_dir.glob(pat)) if p.is_file()]
        present = all(any(True for _ in raw_dir.glob(pat)) for pat in e["paths"])
        out.append(
            {
                "id": e["id"],
                "name": e["name"],
                "expected": [f"data/raw/{p}" for p in e["paths"]],
                "present": present,
                "integration": e["integration"],
                "files": [
                    {
                        "name": str(p.relative_to(raw_dir)),
                        "bytes": p.stat().st_size,
                        "sha256": _sha256(p) if checksums else None,
                    }
                    for p in files
                ],
            }
        )
    return out
