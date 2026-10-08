"""User settings stored as settings.json in the CodeRemote settings folder."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from coderemote.config import config_dir


def _path(directory: Path | None) -> Path:
    return (directory or config_dir()) / "settings.json"


def load(directory: Path | None = None) -> dict:
    try:
        data = json.loads(_path(directory).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(values: dict, directory: Path | None = None) -> dict:
    """Merge `values` into the saved settings and write them atomically."""
    path = _path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load(directory) | values
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return data
