#!/usr/bin/env python3
"""Create a SYNTHETIC test tile in the exact MOLA MEGDR binary format (MSB int16 + PDS3 label).

It is NOT NASA data. It exists so the pipeline, tests and UI can run where the real archive is unreachable.
The UI shows a red SYNTHETIC banner whenever this fixture is in use.
"""

from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "fixtures"
PPD, LAT_MAX, LAT_MIN, LON_W, LON_E = 128, 19.5, 17.5, 76.5, 78.5


def label(name, lines, samples, kind):
    return f"""PDS_VERSION_ID = PDS3
/* SYNTHETIC TEST FIXTURE — NOT NASA DATA. Mimics MOLA MEGDR layout for software testing. */
RECORD_TYPE = FIXED_LENGTH
RECORD_BYTES = {samples * 2}
FILE_RECORDS = {lines}
^IMAGE = "{name.upper()}.IMG"
DATA_SET_ID = "MARSCOPE-SYNTHETIC-FIXTURE"
PRODUCT_ID = "{name.upper()}"
NOTE = "SYNTHETIC TEST FIXTURE - NOT NASA DATA ({kind})"
OBJECT = IMAGE
  LINES = {lines}
  LINE_SAMPLES = {samples}
  SAMPLE_TYPE = {"MSB_INTEGER" if kind == "topography" else "MSB_UNSIGNED_INTEGER"}
  SAMPLE_BITS = 16
  UNIT = {"METER" if kind == "topography" else "COUNT"}
  SCALING_FACTOR = 1
  OFFSET = 0
END_OBJECT = IMAGE
OBJECT = IMAGE_MAP_PROJECTION
  MAP_PROJECTION_TYPE = "SIMPLE CYLINDRICAL"
  A_AXIS_RADIUS = 3396.0 <KM>
  POSITIVE_LONGITUDE_DIRECTION = EAST
  MAP_RESOLUTION = {PPD} <PIX/DEG>
  MAXIMUM_LATITUDE = {LAT_MAX} <DEG>
  MINIMUM_LATITUDE = {LAT_MIN} <DEG>
  WESTERNMOST_LONGITUDE = {LON_W} <DEG>
  EASTERNMOST_LONGITUDE = {LON_E} <DEG>
  LINE_PROJECTION_OFFSET = {LAT_MAX * PPD - 0.5}
END_OBJECT = IMAGE_MAP_PROJECTION
END
"""


def make():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    lines, samples = int((LAT_MAX - LAT_MIN) * PPD), int((LON_E - LON_W) * PPD)
    lat = LAT_MAX - (np.arange(lines) + 0.5) / PPD
    lon = LON_W + (np.arange(samples) + 0.5) / PPD
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    km_lat = np.pi * 3396 / 180
    y = (LA - 18.38) * km_lat
    x = (LO - 77.58) * km_lat * np.cos(np.radians(18.38))
    r = np.hypot(x, y) / 22.5
    z = -2500 + 120 * np.sin(x / 9) * np.cos(y / 11)
    z += np.where(r < 1, -650 * (1 - r**4), 0) + 380 * np.exp(-(((r - 1) / 0.12) ** 2))  # bowl + rim
    xf, yf = x - (-9.5), y - 9.0  # fan inside, west side
    z += 160 * np.exp(-((xf / 6) ** 2) - (yf / 5) ** 2)
    ch = np.exp(-(((y - 12 - 0.15 * x) / 1.2) ** 2)) * (x < -18)  # inlet channel
    z -= 180 * ch
    for _ in range(40):  # small craters
        cx, cy, cr = rng.uniform(-45, 45), rng.uniform(-50, 50), rng.uniform(0.8, 3)
        rr = np.hypot(x - cx, y - cy) / cr
        z += np.where(rr < 1, -60 * cr * (1 - rr**2), 0) + 25 * cr * np.exp(-(((rr - 1) / 0.2) ** 2))
    z += rng.normal(0, 6, z.shape)
    z.astype(">i2").tofile(OUT / "megt_fixture.img")
    (OUT / "megt_fixture.lbl").write_text(label("megt_fixture", lines, samples, "topography"))
    counts = rng.poisson(2.2, z.shape)
    counts[:, ::7] = 0  # synthetic across-track gaps
    counts.astype(">u2").tofile(OUT / "megc_fixture.img")
    (OUT / "megc_fixture.lbl").write_text(label("megc_fixture", lines, samples, "counts"))
    print(f"fixture written: {lines}x{samples} px at {PPD} px/deg -> {OUT}")


if __name__ == "__main__":
    make()
