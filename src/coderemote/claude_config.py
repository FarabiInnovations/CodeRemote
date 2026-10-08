"""Mark a folder as trusted in Claude Code's own config file.

Claude refuses to start in a folder until someone accepts its "trust this folder?"
prompt. Its error message names the alternative this module uses: set
`projects[<folder>].hasTrustDialogAccepted = true` in ~/.claude.json. CodeRemote only
does this after the user taps "Trust and start" on the page.

Running Claude sessions rewrite the whole file, so an update can occasionally be lost;
the launcher checks the result and reports it instead of retrying forever.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path


class TrustError(Exception):
    pass


def config_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(base) / ".claude.json" if base else Path.home() / ".claude.json"


def trust_key(folder: str) -> str:
    # Claude keys projects by the real path with forward slashes.
    return os.path.realpath(folder).replace("\\", "/")


def refuse_reason(folder: str) -> str | None:
    """Folders we won't trust from a web page."""
    real = Path(os.path.realpath(folder))
    if real == Path(os.path.realpath(Path.home())):
        return ("Claude only trusts your home folder for a session someone starts in a terminal. "
                "Pick a project folder instead.")
    if real.parent == real:
        return "Refusing to trust the top of the filesystem. Pick a project folder instead."
    return None


def is_trusted(folder: str, path: Path | None = None) -> bool:
    try:
        data = json.loads((path or config_path()).read_text())
    except (OSError, ValueError):
        return False
    return bool(data.get("projects", {}).get(trust_key(folder), {}).get("hasTrustDialogAccepted"))


class _Lock:
    """The `<file>.lock` directory convention (proper-lockfile) bundled in Claude Code."""

    def __init__(self, target: Path, timeout: float = 5.0, stale: float = 10.0):
        self.dir = target.with_name(target.name + ".lock")
        self.timeout, self.stale = timeout, stale

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.dir.mkdir()
                return self
            except FileExistsError:
                try:
                    if time.time() - self.dir.stat().st_mtime > self.stale:
                        self.dir.rmdir()  # left behind by a crashed writer
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise TrustError("Claude's config file is locked by another process; try again.")
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            self.dir.rmdir()
        except OSError:
            pass


def trust(folder: str, path: Path | None = None) -> str:
    """Set hasTrustDialogAccepted for `folder`, leaving everything else untouched."""
    reason = refuse_reason(folder)
    if reason:
        raise TrustError(reason)
    path = path or config_path()
    key = trust_key(folder)
    with _Lock(path):
        try:
            raw = path.read_text()
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            raise TrustError(f"{path} not found; run `claude` once on this machine first.") from None
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise TrustError(f"{path} is not valid JSON; not touching it.") from exc
        project = data.setdefault("projects", {}).setdefault(key, {})
        if project.get("hasTrustDialogAccepted") is True:
            return key
        project["hasTrustDialogAccepted"] = True
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".coderemote-")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            os.chmod(tmp, mode)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    return key
