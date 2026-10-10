"""Terrain derivation on the native simple-cylindrical grid (spherical Mars)."""

from __future__ import annotations

import numpy as np
from scipy import ndimage


def pixel_spacing_m(lat_rows, ppd: float, radius_m: float):
    """North-south spacing (scalar) and east-west spacing per row, metres."""
    dy = np.pi * radius_m / 180.0 / ppd
    dx = dy * np.cos(np.radians(np.asarray(lat_rows, dtype=float)))
    return dy, dx


def slope_deg(z, lat_rows, ppd, radius_m):
    """Slope (degrees): central differences (one-sided at edges), latitude-dependent dx."""
    dy, dx = pixel_spacing_m(lat_rows, ppd, radius_m)
    dzdy = np.gradient(z, axis=0) / dy
    dzdx = np.gradient(z, axis=1) / dx[:, None]
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))


def local_relief_m(z, size: int = 3):
    """Max minus min elevation in a size x size window (m): a roughness proxy at this scale."""
    zz = np.where(np.isnan(z), np.nanmean(z), z)
    return ndimage.maximum_filter(zz, size=size) - ndimage.minimum_filter(zz, size=size)


def hillshade(z, lat_rows, ppd, radius_m, azimuth=315.0, altitude=45.0, exaggeration=3.0):
    dy, dx = pixel_spacing_m(lat_rows, ppd, radius_m)
    zz = np.where(np.isnan(z), np.nanmean(z), z) * exaggeration
    dzdn = -np.gradient(zz, axis=0) / dy  # rows increase southward -> north gradient
    dzde = np.gradient(zz, axis=1) / dx[:, None]
    nx, ny, nz = -dzde, -dzdn, np.ones_like(zz)
    norm = np.sqrt(nx * nx + ny * ny + 1)
    az, alt = np.radians(azimuth), np.radians(altitude)
    lx, ly, lz = np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)
    return np.clip((nx * lx + ny * ly + nz * lz) / norm, 0, 1)


def haversine_m(lat1, lon1, lat2, lon2, radius_m):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * radius_m * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
