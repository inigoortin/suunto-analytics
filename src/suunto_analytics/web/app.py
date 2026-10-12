"""Local dashboard server (`suunto-app`): read-only JSON API + static frontend, bound to 127.0.0.1."""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from suunto_analytics.core.repository import Database, open_readonly
from suunto_analytics.web.data import DashboardData
from suunto_analytics.web.sync_job import SyncJob

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend"
HOST, PORT = "127.0.0.1", 8790
NO_STORE = {"Cache-Control": "no-store"}
# Only answer requests addressed to this machine by name: blocks DNS-rebinding pages from reading data.
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
# Only our own scripts run; the only outside request is map tiles (disclosed in README).
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def create_app(
    data_dir: Path,
    frontend_dir: Path = FRONTEND,
    sync_job: SyncJob | None = None,
    allowed_hosts: tuple[str, ...] = ALLOWED_HOSTS,
) -> FastAPI:
    db_path = data_dir / "suunto.db"
    if (
        not db_path.exists()
    ):  # first run: create the empty schema so every screen renders
        data_dir.mkdir(parents=True, exist_ok=True)
        Database(db_path).close()
    job = sync_job or SyncJob(data_dir)
    app = FastAPI(
        title="Suunto Analytics", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    @contextmanager
    def data() -> Iterator[DashboardData]:
        with closing(open_readonly(db_path)) as conn:
            yield DashboardData(conn)

    def ok(payload: object) -> JSONResponse:
        return JSONResponse(payload, headers=NO_STORE)

    @app.get("/api/summary")
    def summary() -> JSONResponse:
        with data() as d:
            return ok(d.summary())

    @app.get("/api/activities/{key}/recording")
    def recording(key: str) -> JSONResponse:
        with data() as d:
            rec = d.recording(key)
        if rec is None:
            raise HTTPException(404, "No recording for this activity.")
        return ok(rec)

    @app.get("/api/routes")
    def routes() -> JSONResponse:
        with data() as d:
            return ok(d.routes())

    @app.get("/api/sync")
    def sync_state() -> JSONResponse:
        return ok(job.state())

    @app.post("/api/sync")
    def sync_start(request: Request) -> JSONResponse:
        origin = request.headers.get(
            "origin"
        )  # browsers send it on every cross-site POST
        if origin and urlsplit(origin).hostname not in allowed_hosts:
            raise HTTPException(403, "Sync can only be started from the dashboard.")
        started, reason = job.start()
        return JSONResponse(
            {"started": started, "reason": reason, **job.state()},
            status_code=202 if started else 409,
            headers=NO_STORE,
        )

    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(
        prog="suunto-app", description="Local Suunto dashboard (127.0.0.1 only)."
    )
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    a = ap.parse_args()
    data_dir = Path(os.environ.get("SUUNTO_DATA_DIR", "data")).resolve()
    if not a.no_browser:
        threading.Timer(1.0, webbrowser.open, (f"http://{HOST}:{a.port}/",)).start()
    # access_log off: request paths are not logged anywhere
    uvicorn.run(
        create_app(data_dir),
        host=HOST,
        port=a.port,
        access_log=False,
        log_level="warning",
    )
