"""Central configuration. Every modelling assumption lives here, named and documented."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW, PROCESSED, TARGETS, FIXTURES = DATA / "raw", DATA / "processed", DATA / "targets", DATA / "fixtures"

# Official source (PDS Geosciences Node, PDS4 bundle mgs_mola_topography_derived, collection meg128).
PDS_MEG128 = "https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/"
MOLA_TOPO_TILE = "megt44n045hb"  # topography, 0-44N / 45-90E, 128 px/deg  (contains Jezero)
MOLA_COUNT_TILE = "megc44n045hb"  # number of MOLA shots per bin (same grid) -> interpolation flag

# Mars sphere used by the MEGDR map projection. Overridden by A_AXIS_RADIUS from the label when present.
MARS_RADIUS_M_DEFAULT = 3_396_000.0

REGION = {
    "id": "jezero",
    "name": "Jezero Crater",
    "why": (
        "Mars 2020 Perseverance landing region: an ancient crater lake with a preserved delta, "
        "giving a clear exploration-and-science narrative and a well-documented start point."
    ),
    # ROI (deg, planetocentric, east-positive). Clipped to whole MEGDR pixels — no resampling.
    "lat_min": 17.85,
    "lat_max": 18.90,
    "lon_min": 76.95,
    "lon_max": 78.20,
    "crater_center": [18.38, 77.58],  # IAU nomenclature value
    "crater_radius_km": 22.5,  # ~45 km diameter (IAU / published); used only to search for the rim
}

# Route model. Every value below is an ASSUMPTION and is shown in the UI.
TERRAIN = {
    "slope_ref_deg": 15.0,  # ASSUMPTION: slope at which the slope term saturates (=1)
    "relief_ref_m": 150.0,  # ASSUMPTION: local relief (~1.4 km window) at which the relief term saturates
    # ASSUMPTION: weights inside T (sum = 1)
    "w_slope": 0.75,
    "w_relief": 0.25,
    "max_slope_deg": 25.0,  # ASSUMPTION: cells steeper than this (at ~463 m scale) are excluded. Not a human limit.
}
SCIENCE_SIGMA_M = 1500.0  # ASSUMPTION: distance scale of the science-proximity field S
MODES = {  # cell cost c = beta + alpha*T + gamma*(1-S);  edge cost = distance_m * mean(c_i, c_j)
    "traversability": {
        "letter": "A",
        "label": "TRAVERSABILITY-FIRST",
        "alpha": 6.0,
        "beta": 1.0,
        "gamma": 0.0,
        "intent": "Minimise modeled terrain cost; science is ignored.",
    },
    "science": {
        "letter": "B",
        "label": "SCIENCE-FIRST",
        "alpha": 1.5,
        "beta": 1.0,
        "gamma": 4.0,
        "intent": "Stay close to candidate science targets while keeping terrain cost bounded.",
    },
    "balanced": {
        "letter": "C",
        "label": "BALANCED",
        "alpha": 3.0,
        "beta": 1.0,
        "gamma": 1.5,
        "intent": "Trade modeled terrain cost against science proximity.",
    },
}

# Routes are searched on the 1/512 deg routing grid by default (cubic interpolation of the native grid).
# "native" keeps the original 1/128 deg grid + pure-Python A* for comparison. Finer grids add NO information.
ROUTING_GRID_DEFAULT = "routing"
GRID_CHOICES = ("routing", "native")

# Perseverance path (only used if a local copy exists in data/raw/m20/). The property that holds the sol number is
# NOT assumed: leave None until a person has opened the real file and found the right property name.
PATH_SOL_PROPERTY = None
SEGMENT_TARGET_M = 1500.0  # route is split into ~1.5 km segments for evidence
STOP_RADIUS_M = 1200.0  # a target within this distance of the route counts as a candidate stop

# The 8-stage pipeline shown in the SYSTEM view, with the status of each stage in this build.
PIPELINE = [
    (
        "NASA DATA",
        "PDS archives",
        "IMPLEMENTED",
        "PDS3 reader + MOLA MEGDR fetcher (scripts/fetch_mola.py, needs internet). This offline build runs on the labelled synthetic fixture.",
        "HiRISE, CRISM, CTX products",
    ),
    (
        "DATA HARMONIZATION",
        "common grid · CRS",
        "IMPLEMENTED",
        "Label/file validation, pixel-exact clip, grid-alignment check; documented cubic resampling to 1/512° routing and 1/1024° analysis grids.",
        "Reprojection of CTX/HiRISE/CRISM GeoTIFFs",
    ),
    (
        "FEATURE EXTRACTION",
        "slope · roughness",
        "IMPLEMENTED",
        "Slope (spherical spacing), 3x3 local relief, MOLA coverage flags.",
        "HiRISE-scale roughness",
    ),
    (
        "SPATIAL ANALYSIS",
        "overlay · buffers",
        "IMPLEMENTED",
        "Science-proximity field, derived rim target, cell inspection.",
        "CRISM-derived science areas",
    ),
    (
        "ROUTE GRAPH",
        "nodes · edges · costs",
        "IMPLEMENTED",
        "8-connected graph on the 1/512° routing grid (native 1/128° kept for comparison), spherical step lengths.",
        "Graph on real CTX/HiRISE terrain",
    ),
    (
        "MULTI-OBJECTIVE PLANNING",
        "priority-weighted paths",
        "IMPLEMENTED",
        "Weighted-sum objective, 3 priority modes; exact least-cost search (Dijkstra on 1/512°, A* on 1/128°).",
        "Pareto sets, user-set weights",
    ),
    (
        "EXPLAINABLE EVIDENCE",
        "provenance per segment",
        "IMPLEMENTED",
        "WHY panel: values, cost breakdown, method, provenance, limitation.",
        "Imagery evidence per segment",
    ),
    (
        "CREW BRIEF",
        "one page for the crew",
        "IMPLEMENTED",
        "Brief generated from computed route + provenance; printable.",
        "Export to mission formats",
    ),
]
