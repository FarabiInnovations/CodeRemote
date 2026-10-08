"""HTTP API and the web page."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coderemote import __version__, claude_config, folders, launcher, platform_info, settings
from coderemote.readiness import StatusCache, attention

STATIC_DIR = Path(__file__).parent / "static"


class SettingsUpdate(BaseModel):
    projects_root: str


class LaunchRequest(BaseModel):
    tool: Literal["claude", "codex"]
    path: str
    trust: bool = False  # the user tapped "Trust and start" (Claude only)


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
        tools = status_cache.get(refresh=refresh)
        return {
            "version": __version__,
            "platform": platform_info.detect(),
            "tools": tools,
            "attention": attention(tools),
        }

    @api.get("/fs")
    def list_folder(path: str | None = None, hidden: bool = False) -> dict:
        try:
            return folders.list_folder(path or projects_root()["path"], show_hidden=hidden)
        except folders.FolderError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    @api.get("/settings")
    def get_settings() -> dict:
        return {"projects_root": projects_root(), "recent": settings.recent()}

    @api.put("/settings")
    def put_settings(body: SettingsUpdate) -> dict:
        try:
            folder = folders.resolve_folder(body.projects_root)
        except folders.FolderError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        settings.save({"projects_root": str(folder)})
        return {"projects_root": projects_root(), "recent": settings.recent()}

    @api.post("/launch")
    def launch(body: LaunchRequest) -> dict:
        try:
            folder = str(folders.resolve_folder(body.path))
        except folders.FolderError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        tool = status_cache.get().get(body.tool, {})
        if not tool.get("installed") or not tool.get("path"):
            raise HTTPException(status_code=400, detail=f"{body.tool} is not installed on this machine")

        def start() -> dict:
            if body.tool == "claude" and body.trust:
                claude_config.trust(folder)
            return launcher.launch(body.tool, tool["path"], folder)

        try:
            result = start()
            # A running Claude session can rewrite ~/.claude.json and drop the trust we
            # just added; try once more, then report it.
            if result["status"] == "untrusted" and body.trust:
                result = start()
        except claude_config.TrustError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result["status"] == "untrusted":
            result["trust_refused"] = claude_config.refuse_reason(folder)
        if result["status"] in ("connected", "started"):
            settings.add_recent(folder)
        return result

    app.include_router(api)
    # Mounted last: it matches every path, so routes added after it would never be reached.
    # The page itself is public; it holds no data until the token is supplied.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
