"""Browse folders on this machine and guess where the user keeps their projects."""

from __future__ import annotations

import os
from pathlib import Path

MAX_ENTRIES = 1000

# Common names for a folder that holds all of someone's projects.
ROOT_CANDIDATES = [
    "projects", "Projects", "code", "Code", "src", "dev", "Dev", "repos", "git",
    "workspace", "work", "Developer", "source/repos",
]


class FolderError(Exception):
    status = 400


class NotFound(FolderError):
    status = 404


class NotAFolder(FolderError):
    status = 400


class NoAccess(FolderError):
    status = 403


def is_git_repo(path: Path) -> bool:
    # `.git` is a folder in a normal clone but a file in worktrees and submodules.
    try:
        return (path / ".git").exists()
    except OSError:
        return False


def _encodable(name: str) -> bool:
    # Undecodable filenames come back with lone surrogates that can't go into JSON.
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def resolve_folder(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise FolderError(f"not an absolute path: {raw}")
    try:
        path = path.resolve()
    except OSError as exc:
        raise NotFound(str(exc)) from exc
    if not path.exists():
        raise NotFound(f"no such folder: {path}")
    if not path.is_dir():
        raise NotAFolder(f"not a folder: {path}")
    return path


def list_folder(raw: str, show_hidden: bool = False) -> dict:
    """List the sub-folders of `raw` (files are left out)."""
    path = resolve_folder(raw)
    entries = []
    truncated = False
    try:
        with os.scandir(path) as it:
            for entry in it:
                name = entry.name
                if not show_hidden and name.startswith("."):
                    continue
                if not _encodable(name):
                    continue
                try:
                    if not entry.is_dir():
                        continue
                except OSError:
                    continue
                child = Path(entry.path)
                entries.append({"name": name, "path": str(child), "git": is_git_repo(child)})
    except PermissionError as exc:
        raise NoAccess(f"no permission to read {path}") from exc

    entries.sort(key=lambda e: e["name"].lower())
    if len(entries) > MAX_ENTRIES:
        entries, truncated = entries[:MAX_ENTRIES], True
    parent = path.parent if path.parent != path else None
    return {
        "path": str(path),
        "parent": str(parent) if parent else None,
        "git": is_git_repo(path),
        "entries": entries,
        "truncated": truncated,
    }


def count_git_repos(path: Path) -> int:
    """How many immediate sub-folders of `path` are git repos (no deeper search)."""
    count = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_dir() and is_git_repo(Path(entry.path)):
                        count += 1
                except OSError:
                    continue
    except OSError:
        return 0
    return count


def guess_projects_root(home: Path | None = None) -> Path:
    """First guess at the folder holding the user's projects; falls back to home."""
    home = home or Path.home()
    best, best_count = home, 0
    for name in ROOT_CANDIDATES:
        candidate = home / name
        if candidate.is_dir():
            n = count_git_repos(candidate)
            if n > best_count:
                best, best_count = candidate, n
    return best
