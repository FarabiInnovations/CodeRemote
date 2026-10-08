"""Start `claude remote-control` / `codex remote-control` in a folder and walk away.

The command runs detached in its own process group (through coderemote.capture, which
keeps the log small), so it keeps running when the daemon restarts. We only watch the
first few seconds of output to tell the user whether it connected or why it failed.
"""

from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from coderemote import capture
from coderemote.config import config_dir

LOG_LIMIT = 64 * 1024
# Codex's remote-control failures (like a 403 from OpenAI) are only logged, not printed.
CODEX_RUST_LOG = "warn,codex_app_server_transport::transport::remote_control=info"

ANSI_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]")
CLAUDE_URL_RE = re.compile(r"https://claude\.ai/code\?environment=env_[A-Za-z0-9]+")
CODEX_CONNECT_ERROR_RE = re.compile(
    r"failed to connect to app-server remote control websocket.*? error=(.+?)(?:; retrying| error_kind=|$)",
    re.M,
)
DETAIL_RE = re.compile(r'"detail"\s*:\s*"([^"]+)"')

# Read once at import (single-threaded) rather than flipping the process umask later.
_UMASK = os.umask(0)
os.umask(_UMASK)

# Handles of launches we started, so finished ones get reaped instead of lingering as zombies.
_children: list[subprocess.Popen] = []


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _tail(text: str, lines: int = 20) -> str:
    kept = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(kept[-lines:])


def _error_line(text: str) -> str | None:
    errors = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("Error:")]
    return errors[-1].removeprefix("Error:").strip() if errors else None


def parse_claude(raw: str, exited: bool) -> dict:
    text = strip_ansi(raw)
    url = CLAUDE_URL_RE.search(text)
    if "Workspace not trusted" in text:
        return {"status": "untrusted", "message": "Claude hasn't been trusted in this folder yet."}
    if "Connected" in text and url:
        return {"status": "connected", "url": url.group(0),
                "message": "Connected. Open it in the Claude app or at the link."}
    # Some errors are printed while the process lingers (e.g. "already served" waits ~72 s
    # before exiting), so an Error: line counts as a failure without waiting for the exit.
    error = _error_line(text)
    if "already served by" in text:
        return {"status": "failed", "already_running": True,
                "message": "Claude is already running for this folder. Open it in the Claude app."}
    if error or exited:
        return {"status": "failed", "message": error or "Claude stopped right after starting.",
                "log_tail": _tail(text)}
    return {"status": "pending"}


CODEX_REASONS = [
    ("multi-factor", "Your ChatGPT account needs multi-factor authentication turned on before "
                     "Codex remote control can register this machine."),
    ("requires chatgpt authentication", "Codex isn't signed in with ChatGPT. Run `codex login --device-auth` "
                                        "on the machine."),
    ("socket parent must be owned", "Codex refused its own socket folder because it was writable by other "
                                    "users (umask). CodeRemote should have prevented this; please report it."),
]


def codex_failure_reason(text: str) -> str:
    """The most useful explanation in Codex's output, in plain words when we recognise it."""
    connect_errors = CODEX_CONNECT_ERROR_RE.findall(text)
    if connect_errors:
        last = connect_errors[-1]
        detail = DETAIL_RE.search(last)
        reason = detail.group(1) if detail else last.strip()
    else:
        reason = None
    # Prefer the connection error, then the CLI's own error lines ("Error:" plus its cause).
    candidates = [r for r in (reason, text) if r]
    for needle, friendly in CODEX_REASONS:
        if any(needle in c.lower() for c in candidates):
            return friendly
    return reason or _error_line(text) or "Codex stopped right after starting."


def parse_codex(raw: str, exited: bool) -> dict:
    text = strip_ansi(raw)
    if exited:
        return {"status": "failed", "message": codex_failure_reason(text), "log_tail": _tail(text)}
    # Never seen succeed yet (blocked by the MFA requirement), so this marker is a best guess.
    if "next_status=Connected" in text:
        return {"status": "connected", "message": "Connected. Open Codex in the ChatGPT app."}
    return {"status": "pending"}


PARSERS = {"claude": parse_claude, "codex": parse_codex}


def logs_dir() -> Path:
    path = config_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def log_path(tool: str, folder: str) -> Path:
    """One log per tool and folder, overwritten by each launch."""
    digest = hashlib.sha1(os.path.realpath(folder).encode("utf-8", "surrogateescape")).hexdigest()[:12]
    return logs_dir() / f"{tool}-{digest}.log"


def command(tool: str, binary: str, folder: str) -> tuple[list[str], dict]:
    env = dict(os.environ)
    if tool == "claude":
        # One argv entry, so a folder named like "-x" can't be read as a flag.
        return [binary, "remote-control", f"--name={Path(folder).name or folder}"], env
    env["RUST_LOG"] = CODEX_RUST_LOG
    return [binary, "remote-control"], env


def _detach_kwargs(tool: str) -> dict:
    if sys.platform == "win32":  # untested
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
        return {"creationflags": flags}
    kwargs = {"start_new_session": True}
    if tool == "codex" and _UMASK & 0o022 != 0o022:
        # Codex creates its socket folder with mode 0777 and relies on the umask; with a
        # group-writable umask like 002 its own safety check then rejects the folder.
        kwargs["umask"] = _UMASK | 0o022
    return kwargs


def _stop(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _reap() -> None:
    _children[:] = [p for p in _children if p.poll() is None]


def launch(tool: str, binary: str, folder: str, timeout: float = 20.0) -> dict:
    """Start the tool in `folder` and report what happened in the first seconds."""
    _reap()
    log = log_path(tool, folder)
    # Remove the previous launch's log first: we start reading right away, and stale output
    # (say, an earlier "Workspace not trusted") must not be mistaken for this launch's.
    log.unlink(missing_ok=True)
    argv, env = command(tool, binary, folder)
    try:
        proc = subprocess.Popen(
            # Run capture.py by file path in isolated mode (-I): `-m` would put the user's
            # project folder first on the import path. capture.py only needs the stdlib.
            [sys.executable, "-I", capture.__file__, str(log), str(LOG_LIMIT), "--", *argv],
            cwd=folder, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **_detach_kwargs(tool),
        )
    except OSError as exc:
        return {"status": "failed", "message": f"Could not start {tool}: {exc}"}
    _children.append(proc)

    parse = PARSERS[tool]
    deadline = time.monotonic() + timeout
    while True:
        exited = proc.poll() is not None
        try:
            raw = log.read_text(errors="replace")
        except OSError:
            raw = ""
        result = parse(raw, exited)
        if result["status"] != "pending":
            if result["status"] in ("failed", "untrusted") and proc.poll() is None:
                _stop(proc)  # our own failed launch; don't leave it lingering
            break
        if exited:  # parsers always settle on exit; kept as a guard
            result = {"status": "failed", "message": f"{tool} exited", "log_tail": _tail(strip_ansi(raw))}
            break
        if time.monotonic() >= deadline:
            result = {"status": "started",
                      "message": "Started, but it hasn't confirmed a connection yet. Check the app in a moment.",
                      "log_tail": _tail(strip_ansi(raw))}
            break
        time.sleep(0.25)

    result.update({"tool": tool, "folder": folder, "pid": proc.pid, "log": str(log)})
    return result
