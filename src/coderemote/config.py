"""Per-user settings directory and the access token."""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def config_dir() -> Path:
    override = os.environ.get("CODEREMOTE_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "coderemote"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "coderemote"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "coderemote"


def load_or_create_token(directory: Path | None = None) -> str:
    """Return the saved token, creating one (readable only by this user) on first run."""
    directory = directory or config_dir()
    path = directory / "token"
    if path.exists():
        token = path.read_text().strip()
        if token:
            return token
    directory.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(token + "\n")
    return token
