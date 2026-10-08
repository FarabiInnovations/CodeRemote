"""How Claude Code and Codex were installed, which decides how to update or fix them.

Codex note: `codex remote-control start` (the background daemon) only works with the
standalone install in ~/.codex/packages/standalone, but `codex remote-control` with no
subcommand runs in the foreground from any install, npm included. CodeRemote uses that.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

LABELS = {
    "native": "native installer",
    "standalone": "standalone installer",
    "npm": "npm package",
    "homebrew": "Homebrew",
    "unknown": "unknown install",
}


def _norm(path: str) -> str:
    return path.replace("\\", "/").lower()


def _is_homebrew(p: str) -> bool:
    return any(part in p for part in ("/cellar/", "/caskroom/", "/opt/homebrew/", "/linuxbrew/"))


def classify_claude(resolved: str, home: str) -> str:
    """Install kind for the real (symlink-resolved) path of `claude`."""
    p, h = _norm(resolved), _norm(home).rstrip("/")
    if p.startswith(f"{h}/.local/share/claude/") or "/.claude/local/" in p:
        return "native"
    if "/node_modules/@anthropic-ai/claude-code/" in p:
        return "npm"
    if _is_homebrew(p):
        return "homebrew"
    return "unknown"


def classify_codex(resolved: str, codex_home: str) -> str:
    """Install kind for the real (symlink-resolved) path of `codex`."""
    p, ch = _norm(resolved), _norm(codex_home).rstrip("/")
    if p.startswith(f"{ch}/packages/standalone/"):
        return "standalone"
    if "/node_modules/@openai/codex/" in p:
        return "npm"
    if _is_homebrew(p):
        return "homebrew"
    return "unknown"


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def codex_standalone_binary(home: Path | None = None) -> Path | None:
    """The managed standalone Codex that `codex remote-control` needs, if installed."""
    base = (home or codex_home()) / "packages" / "standalone" / "current"
    for name in ("codex.exe", "codex") if sys.platform == "win32" else ("codex",):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def describe(kind: str, which_path: str, resolved: str) -> dict:
    return {"kind": kind, "label": LABELS.get(kind, kind), "path": which_path, "resolved": resolved}
