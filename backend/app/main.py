"""MARSCOPE API (FastAPI). Run:  uvicorn app.main:app --port 8000   (from backend/)
All logic lives in app/api/handlers.py; app/lite.py serves the same handlers with Starlette only."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import handlers as h
from .api.handlers import BriefReq, NotFound, RouteReq
from .config import PROCESSED, REGION, ROOT
from .ingestion.pds3 import DataError

app = FastAPI(title="MARSCOPE API", version="0.2.0-offline")


@app.exception_handler(DataError)
async def data_error(_: Request, e: DataError):
    return JSONResponse(status_code=422, content={"error": str(e)})


@app.exception_handler(NotFound)
async def not_found(_: Request, e: NotFound):
    return JSONResponse(status_code=404, content={"error": str(e)})


@app.exception_handler(Exception)
async def any_error(_: Request, e: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal problem while processing the request. The demo snapshot remains available."},
    )


app.get("/api/health")(h.health)
app.get("/api/regions")(h.regions)
app.get("/api/layers")(h.layers)
app.get("/api/science-targets")(h.targets)
app.get("/api/overlays")(h.overlays)
app.get("/api/sources")(h.sources)
app.get("/api/credits")(h.credits)
app.get("/api/metadata")(h.metadata)
app.get("/api/cell")(h.cell)


@app.get("/api/layers/{layer_id}")
def layer(layer_id: str):
    return h.layer(layer_id)


@app.post("/api/routes")
def route(req: RouteReq):
    return h.route(req)


@app.post("/api/routes/compare")
def compare(req: RouteReq):
    return h.compare(req)


@app.get("/api/routes/{route_id}")
def get_route(route_id: str):
    return h.get_route(route_id)


@app.get("/api/routes/{route_id}/evidence")
def evidence(route_id: str, segment: str):
    return h.evidence(route_id, segment)


@app.post("/api/crew-brief")
def crew_brief(req: BriefReq):
    return h.crew_brief(req)


app.mount("/layers", StaticFiles(directory=str(PROCESSED / REGION["id"] / "layers"), check_dir=False), name="layers")
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="ui")
