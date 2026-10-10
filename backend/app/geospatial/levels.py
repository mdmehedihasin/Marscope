"""Multi-resolution terrain levels built from the native source grid.

IMPORTANT: a finer grid made by interpolation contains NO new terrain information. It only gives smoother
route geometry and a denser sampling of the same source surface. Every record built here says so.

Levels (all share the exact same outer bounds as the native clipped grid):
  native    1/128 deg  (~463 m)  source cells, values unchanged
  routing   1/512 deg  (~116 m)  bicubic interpolation of the native grid  -> used for route search
  analysis  1/1024 deg (~58 m)   bicubic interpolation of the native grid  -> used for evidence sampling
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from .terrain import pixel_spacing_m, slope_deg

LEVELS = {"native": 1, "routing": 4, "analysis": 8}  # upsampling factor relative to the native grid
PAD = 8  # source cells of odd-reflection padding before the spline (removes edge bending)


def relief_window(factor: int) -> int:
    """Odd window size (cells) that keeps the relief window near the native 3x3 footprint (~1.4 km)."""
    return 2 * int(round(1.5 * factor)) + 1


def upsample_bicubic(z: np.ndarray, factor: int) -> np.ndarray:
    """Cubic-spline interpolation onto a grid `factor` times finer, cell centres aligned to the same bounds.

    Fine cell k (0-based) has its centre at native index (k + 0.5)/factor - 0.5. The source is padded by odd
    reflection (linear continuation) so planes are reproduced exactly, also near the edges.
    NaN cells in the source are filled for the spline and then masked again (nearest-neighbour footprint).
    """
    if factor == 1:
        return z.astype(float).copy()
    h, w = z.shape
    nan = ~np.isfinite(z)
    zz = z.astype(float)
    if nan.any():
        idx = ndimage.distance_transform_edt(nan, return_distances=False, return_indices=True)
        zz = zz[tuple(idx)]
    # Pad by odd reflection (= linear continuation) so the spline is not bent by the array edge.
    p = PAD
    zp = np.pad(zz, p, mode="reflect", reflect_type="odd")
    r = (np.arange(h * factor) + 0.5) / factor - 0.5 + p
    c = (np.arange(w * factor) + 0.5) / factor - 0.5 + p
    rr, cc = np.meshgrid(r, c, indexing="ij")
    out = ndimage.map_coordinates(zp, [rr, cc], order=3, mode="nearest", prefilter=True)
    if nan.any():
        out[upsample_nearest(nan.astype(np.uint8), factor).astype(bool)] = np.nan
    return out


def upsample_nearest(a: np.ndarray, factor: int) -> np.ndarray:
    """Exact nearest-neighbour upsampling (each source cell becomes factor x factor cells)."""
    return np.repeat(np.repeat(a, factor, axis=0), factor, axis=1)


def build_level(
    z_native, counts_native, lat_max, lon_west, ppd_native, radius_m, factor: int, with_relief=True
) -> dict:
    z = upsample_bicubic(z_native, factor)
    ppd = ppd_native * factor
    lat = lat_max - (np.arange(z.shape[0]) + 0.5) / ppd
    slope = slope_deg(np.where(np.isfinite(z), z, np.nanmean(z)), lat, ppd, radius_m)
    slope[~np.isfinite(z)] = np.nan
    out = {
        "factor": factor,
        "ppd": ppd,
        "z": z,
        "slope": slope,
        "lat_max": lat_max,
        "lon_west": lon_west,
        "radius_m": radius_m,
        "counts": None if counts_native is None else upsample_nearest(counts_native, factor),
    }
    if with_relief:
        k = 3 if factor == 1 else relief_window(factor)
        zz = np.where(np.isfinite(z), z, np.nanmean(z))
        out["relief"] = ndimage.maximum_filter(zz, size=k) - ndimage.minimum_filter(zz, size=k)
        out["relief_window_cells"] = k
    return out


def slope_stats(slope: np.ndarray, max_slope_deg: float) -> dict:
    s = slope[np.isfinite(slope)]
    return {
        "mean_deg": round(float(s.mean()), 2),
        "p50_deg": round(float(np.percentile(s, 50)), 2),
        "p95_deg": round(float(np.percentile(s, 95)), 2),
        "p99_deg": round(float(np.percentile(s, 99)), 2),
        "max_deg": round(float(s.max()), 2),
        "cells": int(s.size),
        "cells_above_limit": int((s > max_slope_deg).sum()),
    }


def level_description(name: str, factor: int, ppd_native: float, radius_m: float, lat_mid: float) -> dict:
    ppd = ppd_native * factor
    dy, dx = pixel_spacing_m([lat_mid], ppd, radius_m)
    return {
        "level": name,
        "factor": factor,
        "ppd": ppd,
        "cell_deg": f"1/{ppd:g}°",
        "cell_ns_m": round(float(dy), 1),
        "cell_ew_m": round(float(dx[0]), 1),
        "method": (
            "source cells, values unchanged"
            if factor == 1
            else f"cubic-spline interpolation (scipy.ndimage.map_coordinates, order=3, prefilter=True; edges padded {PAD} cells by odd reflection) "
            f"of the native 1/{ppd_native:g}° grid; shot counts by nearest neighbour"
        ),
        "relief_window": (
            "3x3 cells"
            if factor == 1
            else f"{relief_window(factor)}x{relief_window(factor)} cells (keeps ~1.4 km footprint)"
        ),
        "information_note": (
            "native source resolution"
            if factor == 1
            else "finer spacing does NOT add terrain information; the effective resolution is still the native grid"
        ),
    }
