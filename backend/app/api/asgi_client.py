"""Tiny in-process ASGI test client (no httpx, no network, no sockets).

Calls the ASGI app directly with an HTTP scope, so tests and the snapshot builder work on machines where
httpx / FastAPI's TestClient are not installed. Interface mirrors the parts of TestClient that MARSCOPE uses."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlencode


class Response:
    def __init__(self, status: int, headers: list, body: bytes):
        self.status_code, self.headers, self.content = (
            status,
            {k.decode().lower(): v.decode() for k, v in headers},
            body,
        )

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.content)


class Client:
    def __init__(self, app):
        self.app = app

    def _call(self, method, path, params=None, body=b"", headers=None):
        qs = urlencode(params or {})
        if "?" in path:
            path, q = path.split("?", 1)
            qs = q + ("&" + qs if qs else "")
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": qs.encode(),
            "root_path": "",
            "headers": [(b"host", b"testserver")] + [(k.encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": ("127.0.0.1", 0),
            "server": ("testserver", 80),
        }
        out = {"status": 500, "headers": [], "body": b""}
        sent = {"done": False}

        async def receive():
            if sent["done"]:
                return {"type": "http.disconnect"}
            sent["done"] = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(msg):
            if msg["type"] == "http.response.start":
                out["status"], out["headers"] = msg["status"], msg.get("headers", [])
            elif msg["type"] == "http.response.body":
                out["body"] += msg.get("body", b"")

        asyncio.run(self.app(scope, receive, send))
        return Response(out["status"], out["headers"], out["body"])

    def get(self, path, params=None):
        return self._call("GET", path, params)

    def post(self, path, json=None, params=None):
        import json as _j

        return self._call(
            "POST",
            path,
            params,
            _j.dumps(json if json is not None else {}).encode(),
            {"content-type": "application/json"},
        )


def available_apps():
    """Return [(name, asgi_app)] for every server implementation importable here (FastAPI first)."""
    apps = []
    try:
        from ..main import app as fast_app

        apps.append(("fastapi", fast_app))
    except ImportError:
        pass
    from ..lite import app as lite_app

    apps.append(("lite", lite_app))
    return apps
