"""HTTP API and the web page."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coderemote import __version__, folders, platform_info, settings
from coderemote.readiness import StatusCache

STATIC_DIR = Path(__file__).parent / "static"


class SettingsUpdate(BaseModel):
    projects_root: str


def projects_root() -> dict:
    """The saved projects folder if it still exists, otherwise a guess."""
    saved = settings.load().get("projects_root")
    if saved and Path(saved).is_dir():
        return {"path": saved, "source": "saved"}
    return {"path": str(folders.guess_projects_root()), "source": "guessed"}


def create_app(token: str, cache: StatusCache | None = None) -> FastAPI:
    app = FastAPI(title="CodeRemote", version=__version__, docs_url=None, redoc_url=None)
    status_cache = cache or StatusCache()

    def require_token(request: Request) -> None:
        header = request.headers.get("authorization", "")
        supplied = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
        if not supplied or not secrets.compare_digest(supplied, token):
            raise HTTPException(status_code=401, detail="missing or wrong token")

    # Every /api route goes on this router so none can skip the token check.
    api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])

    @api.get("/status")
    def status(refresh: bool = False) -> dict:
        return {
            "version": __version__,
            "platform": platform_info.detect(),
            "tools": status_cache.get(refresh=refresh),
        }

    @api.get("/fs")
    def list_folder(path: str | None = None, hidden: bool = False) -> dict:
        try:
            return folders.list_folder(path or projects_root()["path"], show_hidden=hidden)
        except folders.FolderError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    @api.get("/settings")
    def get_settings() -> dict:
        return {"projects_root": projects_root()}

    @api.put("/settings")
    def put_settings(body: SettingsUpdate) -> dict:
        try:
            folder = folders.resolve_folder(body.projects_root)
        except folders.FolderError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        settings.save({"projects_root": str(folder)})
        return {"projects_root": projects_root()}

    app.include_router(api)
    # Mounted last: it matches every path, so routes added after it would never be reached.
    # The page itself is public; it holds no data until the token is supplied.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
