"""HTTP API and the web page."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from coderemote import __version__, platform_info
from coderemote.readiness import StatusCache

STATIC_DIR = Path(__file__).parent / "static"


def create_app(token: str, cache: StatusCache | None = None) -> FastAPI:
    app = FastAPI(title="CodeRemote", version=__version__, docs_url=None, redoc_url=None)
    status_cache = cache or StatusCache()

    def require_token(request: Request) -> None:
        header = request.headers.get("authorization", "")
        supplied = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
        if not supplied or not secrets.compare_digest(supplied, token):
            raise HTTPException(status_code=401, detail="missing or wrong token")

    @app.get("/api/status", dependencies=[Depends(require_token)])
    def status(refresh: bool = False) -> dict:
        return {
            "version": __version__,
            "platform": platform_info.detect(),
            "tools": status_cache.get(refresh=refresh),
        }

    # The page itself is public; it holds no data until the token is supplied.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
