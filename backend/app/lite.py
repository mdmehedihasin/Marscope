"""MARSCOPE API on Starlette only (no FastAPI needed). Same handlers, same URLs, same JSON as app/main.py.

Used automatically by run.py when FastAPI is not installed (for example on an offline machine), and by the
tests/snapshot builder in that case. Run directly:  uvicorn app.lite:app --port 8000   (from backend/)"""

from __future__ import annotations

import json

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .api import handlers as h
from .config import PROCESSED, REGION, ROOT
from .ingestion.pds3 import DataError


def _err(status, msg):
    return JSONResponse({"error": msg}, status_code=status)


def endpoint(fn, body_model=None, path_args=(), query_args=()):
    async def run(request: Request):
        try:
            kw = {a: request.path_params[a] for a in path_args}
            for a, typ in query_args:
                if a not in request.query_params:
                    return _err(422, f"Missing query parameter '{a}'")
                try:
                    kw[a] = typ(request.query_params[a])
                except ValueError:
                    return _err(422, f"Query parameter '{a}' must be a {typ.__name__}")
            args = []
            if body_model is not None:
                raw = await request.body()
                try:
                    data = json.loads(raw or b"{}")
                    args.append(body_model.model_validate(data))
                except (ValueError, ValidationError) as e:
                    return _err(422, f"Invalid request body: {str(e).splitlines()[0]}")
            return JSONResponse(fn(*args, **kw))
        except DataError as e:
            return _err(422, str(e))
        except h.NotFound as e:
            return _err(404, str(e))
        except Exception:
            return _err(500, "Internal problem while processing the request. The demo snapshot remains available.")

    return run


routes = [
    Route("/api/health", endpoint(h.health)),
    Route("/api/regions", endpoint(h.regions)),
    Route("/api/layers", endpoint(h.layers)),
    Route("/api/layers/{layer_id}", endpoint(h.layer, path_args=("layer_id",))),
    Route("/api/science-targets", endpoint(h.targets)),
    Route("/api/overlays", endpoint(h.overlays)),
    Route("/api/sources", endpoint(h.sources)),
    Route("/api/credits", endpoint(h.credits)),
    Route("/api/metadata", endpoint(h.metadata)),
    Route("/api/cell", endpoint(h.cell, query_args=(("lat", float), ("lon", float)))),
    Route("/api/routes", endpoint(h.route, h.RouteReq), methods=["POST"]),
    Route("/api/routes/compare", endpoint(h.compare, h.RouteReq), methods=["POST"]),
    Route("/api/routes/{route_id}", endpoint(h.get_route, path_args=("route_id",))),
    Route(
        "/api/routes/{route_id}/evidence", endpoint(h.evidence, path_args=("route_id",), query_args=(("segment", str),))
    ),
    Route("/api/crew-brief", endpoint(h.crew_brief, h.BriefReq), methods=["POST"]),
    Mount(
        "/layers", app=StaticFiles(directory=str(PROCESSED / REGION["id"] / "layers"), check_dir=False), name="layers"
    ),
]
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    routes.append(Mount("/", app=StaticFiles(directory=str(DIST), html=True), name="ui"))

app = Starlette(routes=routes)
