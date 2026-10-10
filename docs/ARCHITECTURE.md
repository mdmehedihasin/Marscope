# Architecture

```
PDS .lbl/.img (real MOLA in data/raw/, else the synthetic fixture in data/fixtures/)
        │  ingestion/pds3.py — parse, validate, pixel-exact clip (no resampling)
        ▼
scripts/build_region.py ── geospatial/terrain.py   slope, relief, hillshade on a sphere
        │                ── geospatial/levels.py    1/512° routing + 1/1024° analysis grids (cubic, documented)
        │                ── ingestion/traverse.py   Perseverance path slot (real local GeoJSON, else labelled illustration)
        │                ── ingestion/local_inventory.py  which source files exist in data/raw/
        ▼
data/processed/jezero/{grid.npz (native only), manifest.json, layers/*.png}
        │
store.py  ── rebuilds the finer grids at start-up (~0.4 s; nothing large is shipped)
        │  ── routing/engine.py: cost model; A* (native) / Dijkstra via scipy.sparse.csgraph (1/512°);
        │                        slope read along the path on the 1/1024° grid
        │  ── briefing/brief.py: Crew Route Brief from computed data only
        ▼
api/handlers.py  (framework-free logic, pydantic request models)
   ├── main.py  FastAPI server (primary, `pip install -r requirements.txt`)
   └── lite.py  Starlette-only server (same URLs/JSON; used when FastAPI is not installed)
        ▼
/api/*  ◄──── frontend (React + TypeScript + Leaflet, CRS.Simple on the lat/lon grid)
                └─► fallback: frontend/dist/demo/snapshot.json (frozen API responses, no backend needed)
```

All paths above are relative to `backend/app/` unless they start with `scripts/`, `data/` or `frontend/`.

## API

`GET /api/health · /api/regions · /api/layers · /api/layers/{id} · /api/science-targets · /api/overlays ·
/api/routes/{id} · /api/routes/{id}/evidence?segment= · /api/sources · /api/credits · /api/metadata · /api/cell?lat&lon`

`POST /api/routes · /api/routes/compare · /api/crew-brief` (route bodies may include `"grid": "routing" | "native"`).

Data problems → HTTP 422 `{"error": …}`; unknown layer → 404; unexpected failures → a short 500 message, never a
traceback. The processed layer images are served from `/layers/`, and the built UI from `/`.

## Tests and snapshot without a web stack

`api/asgi_client.py` calls the ASGI app in-process (no httpx, no sockets). The API tests run against every server that
is installed (FastAPI and/or the Starlette fallback). `scripts/build_snapshot.py` uses the same client to freeze the
Demo Mission responses into `frontend/public/demo/` and copies them to `frontend/dist/demo/`.

## Frontend build

`cd frontend && npm install && npm run build` runs the TypeScript check and Vite. `base: './'` in `vite.config.ts` gives
relative asset paths, so `dist/` also works from a sub-folder (for example GitHub Pages). `dist/` is committed so the
app runs without Node.js.

## Design notes

- **Display:** Leaflet `CRS.Simple` with (lat, lon) as plane coordinates, which is the data's own simple-cylindrical
  grid. All distances and slopes are computed on the Mars sphere in the backend, never in screen space.
- **No GDAL/rasterio yet:** one raster tile and a few points; NumPy reads MEGDR directly. CTX/HiRISE/CRISM GeoTIFFs
  will need rasterio + pyproj (planned).
