"""Minimal, dependency-free reader for PDS3 detached labels + raw IMG rasters (MOLA MEGDR format).

Validates the label against the file (size, extents vs. resolution) instead of trusting it blindly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


class DataError(Exception):
    """User-presentable data problem (never shown as a raw traceback)."""


def _value(v: str):
    v = v.strip()
    m = re.match(r"^(.*?)\s*<([^>]+)>$", v, re.S)
    if m:
        v = m.group(1).strip()
    if v.startswith('"') and v.endswith('"'):
        return " ".join(v[1:-1].split())
    try:
        f = float(v)
        return int(f) if re.fullmatch(r"[+-]?\d+", v) else f
    except ValueError:
        return v.strip('"')


def parse_label(text: str) -> dict:
    """Parse a PDS3 label into a nested dict. OBJECT blocks become sub-dicts keyed by their name."""
    root: dict = {}
    stack = [root]
    lines = text.replace("\r", "").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].split("/*")[0].rstrip()
        i += 1
        if line.strip() == "END":
            break
        if not line.strip() or "=" not in line:
            continue
        key, val = [s.strip() for s in line.split("=", 1)]
        while (val.count('"') % 2 == 1 or val.count("(") > val.count(")")) and i < len(lines):
            val += " " + lines[i].strip()
            i += 1
        if key == "OBJECT":
            obj: dict = {}
            stack[-1][val] = obj
            stack.append(obj)
        elif key == "END_OBJECT":
            if len(stack) > 1:
                stack.pop()
        else:
            stack[-1][key] = _value(val)
    return root


@dataclass
class Raster:
    data: np.ndarray  # float64, metres (NaN = no data)
    lat_max: float  # northern edge of first row (deg)
    lon_west: float  # western edge of first column (deg, east-positive)
    ppd: float  # pixels per degree
    radius_m: float
    meta: dict = field(default_factory=dict)

    @property
    def shape(self):
        return self.data.shape

    def lat_of_row(self, i):
        return self.lat_max - (np.asarray(i) + 0.5) / self.ppd

    def lon_of_col(self, j):
        return self.lon_west + (np.asarray(j) + 0.5) / self.ppd

    def row_of_lat(self, lat):
        return (self.lat_max - np.asarray(lat)) * self.ppd - 0.5

    def col_of_lon(self, lon):
        return (np.asarray(lon) - self.lon_west) * self.ppd - 0.5

    def bounds(self):
        h, w = self.shape
        return {
            "lat_min": self.lat_max - h / self.ppd,
            "lat_max": self.lat_max,
            "lon_min": self.lon_west,
            "lon_max": self.lon_west + w / self.ppd,
        }


_DTYPES = {
    ("MSB_INTEGER", 16): ">i2",
    ("MSB_UNSIGNED_INTEGER", 16): ">u2",
    ("LSB_INTEGER", 16): "<i2",
    ("LSB_UNSIGNED_INTEGER", 16): "<u2",
    ("UNSIGNED_INTEGER", 16): ">u2",
    ("PC_REAL", 32): "<f4",
    ("IEEE_REAL", 32): ">f4",
    ("MSB_INTEGER", 32): ">i4",
    ("LSB_INTEGER", 32): "<i4",
}


def geometry_from_label(lab: dict, name: str = "label") -> dict:
    """Validated simple-cylindrical geometry from a parsed MEGDR label.

    Checks (verified against the real PDS label megr44s090hb.lbl):
      * extents x MAP_RESOLUTION == LINES / LINE_SAMPLES
      * LINE_PROJECTION_OFFSET ~= MAXIMUM_LATITUDE x MAP_RESOLUTION (PDS: line = LPO - lat*res, 1-based)
      * east-positive longitudes, sphere radius from A_AXIS_RADIUS
    """
    img = lab.get("IMAGE")
    proj = lab.get("IMAGE_MAP_PROJECTION") or lab.get("MAP_PROJECTION")
    if not isinstance(img, dict) or not isinstance(proj, dict):
        raise DataError(f"{name}: label has no IMAGE / IMAGE_MAP_PROJECTION object")
    lines, samples = int(img["LINES"]), int(img["LINE_SAMPLES"])
    ppd = float(proj["MAP_RESOLUTION"])
    lat_max, lat_min = float(proj["MAXIMUM_LATITUDE"]), float(proj["MINIMUM_LATITUDE"])
    lon_w, lon_e = float(proj["WESTERNMOST_LONGITUDE"]), float(proj["EASTERNMOST_LONGITUDE"])
    if str(proj.get("POSITIVE_LONGITUDE_DIRECTION", "EAST")).upper() != "EAST":
        raise DataError("Only east-positive longitude products are supported")
    if abs((lat_max - lat_min) * ppd - lines) > 0.5 or abs((lon_e - lon_w) * ppd - samples) > 0.5:
        raise DataError(f"{name}: map extents disagree with LINES/LINE_SAMPLES at {ppd} px/deg")
    if "LINE_PROJECTION_OFFSET" in proj:
        lpo = float(proj["LINE_PROJECTION_OFFSET"])
        if abs(lpo - lat_max * ppd) > 1.0:
            raise DataError(f"{name}: LINE_PROJECTION_OFFSET {lpo} inconsistent with MAXIMUM_LATITUDE")
    return {
        "lines": lines,
        "samples": samples,
        "ppd": ppd,
        "lat_max": lat_max,
        "lat_min": lat_min,
        "lon_w": lon_w,
        "lon_e": lon_e,
        "radius_m": float(proj.get("A_AXIS_RADIUS", 3396.0)) * 1000.0,
    }


def read_megdr(lbl_path: Path) -> Raster:
    lbl_path = Path(lbl_path)
    if not lbl_path.exists():
        raise DataError(f"Label not found: {lbl_path.name}")
    lab = parse_label(lbl_path.read_text(errors="replace"))
    img = lab.get("IMAGE")
    proj = lab.get("IMAGE_MAP_PROJECTION") or lab.get("MAP_PROJECTION")
    if not isinstance(img, dict) or not isinstance(proj, dict):
        raise DataError(f"{lbl_path.name}: label has no IMAGE / IMAGE_MAP_PROJECTION object")
    ptr = lab.get("^IMAGE")
    name = ptr if isinstance(ptr, str) else lbl_path.with_suffix(".img").name
    cands = [lbl_path.with_name(name), lbl_path.with_name(name.lower()), lbl_path.with_name(name.upper())]
    img_path = next((p for p in cands if p.exists()), None)
    if img_path is None:
        raise DataError(f"Image file {name} referenced by {lbl_path.name} is missing")
    lines, samples = int(img["LINES"]), int(img["LINE_SAMPLES"])
    key = (str(img["SAMPLE_TYPE"]).upper(), int(img["SAMPLE_BITS"]))
    if key not in _DTYPES:
        raise DataError(f"Unsupported SAMPLE_TYPE {key}")
    dt = np.dtype(_DTYPES[key])
    expected = lines * samples * dt.itemsize
    size = img_path.stat().st_size
    if size < expected:
        raise DataError(f"{img_path.name} is truncated ({size} bytes, expected {expected}) — re-download it")
    raw = np.fromfile(img_path, dtype=dt, count=lines * samples).reshape(lines, samples)
    data = raw.astype(np.float64) * float(img.get("SCALING_FACTOR", 1) or 1) + float(img.get("OFFSET", 0) or 0)
    if "MISSING_CONSTANT" in img:
        data[raw == img["MISSING_CONSTANT"]] = np.nan
    geo = geometry_from_label(lab, lbl_path.name)
    ppd, lat_max, lat_min, lon_w, lon_e, radius = (
        geo[k] for k in ("ppd", "lat_max", "lat_min", "lon_w", "lon_e", "radius_m")
    )
    meta = {
        "label": lbl_path.name,
        "image": img_path.name,
        "bytes": size,
        "lines": lines,
        "samples": samples,
        "sample_type": key[0],
        "unit": img.get("UNIT", "METER"),
        "ppd": ppd,
        "projection": proj.get("MAP_PROJECTION_TYPE", "SIMPLE CYLINDRICAL"),
        "product_id": lab.get("PRODUCT_ID"),
        "data_set_id": lab.get("DATA_SET_ID"),
        "note": lab.get("NOTE") or img.get("NOTE"),
        "radius_m": radius,
        "extent": {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_w, "lon_max": lon_e},
    }
    return Raster(data, lat_max, lon_w, ppd, radius, meta)


def clip(r: Raster, lat_min, lat_max, lon_min, lon_max):
    """Clip to the whole source pixels covering the box. No resampling. Returns (raster, step record)."""
    b = r.bounds()
    eps = 1e-9
    if (
        lat_min < b["lat_min"] - eps
        or lat_max > b["lat_max"] + eps
        or lon_min < b["lon_min"] - eps
        or lon_max > b["lon_max"] + eps
    ):
        raise DataError("Requested region is not fully covered by this tile")
    i0 = int(np.floor((r.lat_max - lat_max) * r.ppd + eps))
    i1 = int(np.ceil((r.lat_max - lat_min) * r.ppd - eps))
    j0 = int(np.floor((lon_min - r.lon_west) * r.ppd + eps))
    j1 = int(np.ceil((lon_max - r.lon_west) * r.ppd - eps))
    out = Raster(
        r.data[i0:i1, j0:j1].copy(), r.lat_max - i0 / r.ppd, r.lon_west + j0 / r.ppd, r.ppd, r.radius_m, dict(r.meta)
    )
    step = {
        "step": "clip",
        "rows": [i0, i1],
        "cols": [j0, j1],
        "result_bounds": out.bounds(),
        "resampled": False,
        "note": "Clipped to whole source pixels; values unchanged.",
    }
    return out, step
