"""Is Claude Code / Codex installed on this machine and able to do remote control?

Every check here is read-only: it never starts a session, a daemon, or a pairing
flow, and it never reads credential files.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from coderemote import runner

VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")


def parse_version(text: str) -> str | None:
    """'2.1.294 (Claude Code)' -> '2.1.294'; 'codex-cli 0.146.0' -> '0.146.0'."""
    match = VERSION_RE.search(text)
    return match.group(1) if match else None


def help_lists_command(help_text: str, command: str) -> bool:
    """True when `command` appears in the 'Commands:' block of a --help page."""
    in_block = False
    for line in help_text.splitlines():
        if line.strip().lower().startswith("commands:"):
            in_block = True
            continue
        if in_block:
            if line and not line[0].isspace():
                break  # next top-level section
            first = line.strip().split(" ", 1)[0]
            if command in first.split("|"):
                return True
    return False


def _check(label: str, ok: bool | None, detail: str = "") -> dict:
    # ok: True = passed, False = failed, None = could not be determined
    return {"label": label, "ok": ok, "detail": detail}


def _verdict(installed: bool, checks: list[dict]) -> str:
    if not installed:
        return "missing"
    if all(c["ok"] is True for c in checks):
        return "ready"
    if any(c["ok"] is False for c in checks):
        return "not_ready"
    return "unknown"


_claude_rc_cache: dict[tuple[str, str | None], bool] = {}


def _claude_rc_supported(path: str, version: str | None) -> bool:
    """Does this Claude Code build have `claude remote-control`?

    It is a hidden command (not listed in `claude --help`), so ask for its help.
    That call prints the help and then keeps running, and it rewrites
    ~/.claude.json each time, so stop at the first marker and only ask once per
    installed version.
    """
    key = (path, version)
    if key not in _claude_rc_cache:
        res = runner.run([path, "remote-control", "--help"], 10, "--spawn")
        _claude_rc_cache[key] = "remote-control" in res.output and "--spawn" in res.output
    return _claude_rc_cache[key]


def check_claude() -> dict:
    path = shutil.which("claude")
    if not path:
        return {"tool": "claude", "name": "Claude Code", "installed": False, "path": None,
                "version": None, "checks": [], "verdict": "missing"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_version = pool.submit(runner.run, [path, "--version"], 10)
        f_auth = pool.submit(runner.run, [path, "auth", "status"], 15)
    version_res, auth_res = f_version.result(), f_auth.result()
    version = parse_version(version_res.output)

    checks = []
    rc_supported = _claude_rc_supported(path, version)
    checks.append(_check(
        "Remote Control supported",
        rc_supported,
        "" if rc_supported else "this version has no `claude remote-control`; run `claude update`",
    ))

    try:
        auth = json.loads(auth_res.output)
    except ValueError:
        auth = None
    if auth is None:
        checks.append(_check("Signed in", None, "could not read `claude auth status`"))
    elif not auth.get("loggedIn"):
        checks.append(_check("Signed in", False, "run `claude auth login`"))
    else:
        method = auth.get("authMethod") or "unknown"
        plan = auth.get("subscriptionType")
        detail = f"{method}" + (f" · {plan} plan" if plan else "")
        checks.append(_check("Signed in", True, detail))
        # Remote Control runs through a claude.ai account, not an API key.
        checks.append(_check(
            "Signed in with a claude.ai account",
            method == "claude.ai",
            "" if method == "claude.ai" else f"signed in via {method}; Remote Control needs a claude.ai login",
        ))

    return {
        "tool": "claude",
        "name": "Claude Code",
        "installed": True,
        "path": path,
        "version": version,
        "checks": checks,
        "verdict": _verdict(True, checks),
        "notes": ["An organization policy can still turn Remote Control off; that is not checked here."],
    }


def check_codex() -> dict:
    path = shutil.which("codex")
    if not path:
        return {"tool": "codex", "name": "Codex", "installed": False, "path": None,
                "version": None, "checks": [], "verdict": "missing"}

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_version = pool.submit(runner.run, [path, "--version"], 10)
        # Unknown subcommands fall back to the top-level help with exit 0, so parse
        # the Commands: list instead of trusting an exit code.
        f_help = pool.submit(runner.run, [path, "--help"], 10)
        f_login = pool.submit(runner.run, [path, "login", "status"], 15)
    version_res, help_res, login_res = f_version.result(), f_help.result(), f_login.result()

    checks = []
    rc_supported = help_lists_command(help_res.output, "remote-control")
    checks.append(_check(
        "Remote control supported",
        rc_supported,
        "experimental in Codex" if rc_supported else "this version has no `codex remote-control`; update Codex",
    ))

    login_text = login_res.output.strip().splitlines()[-1] if login_res.output.strip() else ""
    if login_res.timed_out or login_res.error:
        checks.append(_check("Signed in", None, "could not read `codex login status`"))
    elif login_res.returncode == 0 and "logged in" in login_text.lower():
        checks.append(_check("Signed in", True, login_text))
    else:
        checks.append(_check("Signed in", False, login_text or "run `codex login`"))

    return {
        "tool": "codex",
        "name": "Codex",
        "installed": True,
        "path": path,
        "version": parse_version(version_res.output),
        "checks": checks,
        "verdict": _verdict(True, checks),
        "notes": ["Pairing with the ChatGPT app is not checked yet."],
    }


class StatusCache:
    """Checks spawn several CLIs, so reuse the result for a short while."""

    def __init__(self, ttl: float = 30.0):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._value: dict | None = None
        self._at = 0.0

    def get(self, refresh: bool = False) -> dict:
        with self._lock:
            if refresh or self._value is None or time.monotonic() - self._at > self.ttl:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    claude, codex = pool.submit(check_claude), pool.submit(check_codex)
                    self._value = {"claude": claude.result(), "codex": codex.result()}
                self._at = time.monotonic()
            return self._value
