"""Is Claude Code / Codex installed on this machine and able to do remote control?

Every check here is read-only: it never starts a session, a daemon, or a pairing
flow, and it never reads credential files.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from coderemote import install, runner

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


def fix(text: str, command: str | None = None) -> dict:
    """What the user should do: a sentence, plus the command to run on the machine."""
    return {"text": text, "command": command}


def _check(label: str, ok: bool | None, detail: str = "", fix: dict | None = None) -> dict:
    # ok: True = passed, False = failed, None = could not be determined
    return {"label": label, "ok": ok, "detail": detail, "fix": fix if ok is not True else None}


def _verdict(installed: bool, checks: list[dict]) -> str:
    if not installed:
        return "missing"
    if all(c["ok"] is True for c in checks):
        return "ready"
    if any(c["ok"] is False for c in checks):
        return "not_ready"
    return "unknown"


def _missing(tool: str, name: str, install_fix: dict) -> dict:
    return {"tool": tool, "name": name, "installed": False, "path": None, "version": None,
            "checks": [], "verdict": "missing", "fix": install_fix}


# ---- Claude Code -------------------------------------------------------------------------

CLAUDE_INSTALL = (
    fix("Install Claude Code.", "irm https://claude.ai/install.ps1 | iex")
    if sys.platform == "win32"
    else fix("Install Claude Code.", "curl -fsSL https://claude.ai/install.sh | bash")
)
CLAUDE_UPDATE = {
    "native": "claude update",
    "npm": "npm install -g @anthropic-ai/claude-code@latest",
    "homebrew": "brew upgrade claude-code",
}
CLAUDE_LOGIN = fix(
    "Sign in to Claude Code on the machine (over SSH is fine; it prints a link to open).",
    "claude auth login",
)

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


def claude_auth_checks(output: str) -> list[dict]:
    """Checks built from the JSON that `claude auth status` prints."""
    try:
        auth = json.loads(output)
    except ValueError:
        auth = None
    if not isinstance(auth, dict):
        return [_check("Signed in", None, "could not read `claude auth status`",
                       fix("Run this on the machine to see what's wrong.", "claude auth status"))]
    if not auth.get("loggedIn"):
        return [_check("Signed in", False, "not signed in", CLAUDE_LOGIN)]
    method = auth.get("authMethod") or "unknown"
    plan = auth.get("subscriptionType")
    checks = [_check("Signed in", True, method + (f" · {plan} plan" if plan else ""))]
    # Remote Control runs through a claude.ai account, not an API key.
    checks.append(_check(
        "Signed in with a claude.ai account",
        method == "claude.ai",
        "" if method == "claude.ai" else f"signed in via {method}",
        fix("Remote Control needs a claude.ai subscription login, not an API key.", "claude auth login --claudeai"),
    ))
    return checks


def check_claude() -> dict:
    path = shutil.which("claude")
    if not path:
        return _missing("claude", "Claude Code", CLAUDE_INSTALL)

    resolved = os.path.realpath(path)
    kind = install.classify_claude(resolved, str(Path.home()))

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_version = pool.submit(runner.run, [path, "--version"], 10)
        f_auth = pool.submit(runner.run, [path, "auth", "status"], 15)
    version_res, auth_res = f_version.result(), f_auth.result()
    version = parse_version(version_res.output)

    rc_supported = _claude_rc_supported(path, version)
    update = CLAUDE_UPDATE.get(kind)
    checks = [_check(
        "Remote Control supported",
        rc_supported,
        "" if rc_supported else "this version has no `claude remote-control`",
        fix("Update Claude Code.", update),
    )]
    checks += claude_auth_checks(auth_res.output)

    return {
        "tool": "claude",
        "name": "Claude Code",
        "installed": True,
        "path": path,
        "install": install.describe(kind, path, resolved),
        "version": version,
        "checks": checks,
        "verdict": _verdict(True, checks),
        "notes": ["An organization policy can still turn Remote Control off; that is not checked here."],
    }


# ---- Codex -------------------------------------------------------------------------------

CODEX_INSTALL = fix("Install Codex.", "npm install -g @openai/codex")
CODEX_UPDATE = {
    "npm": "npm install -g @openai/codex@latest",
    "homebrew": "brew upgrade codex",
    "standalone": "codex update",
}
CODEX_LOGIN = fix(
    "Sign in to Codex on the machine. Over SSH, device login prints a code to enter in your browser.",
    "codex login --device-auth",
)


def codex_login_check(result: runner.Result) -> dict:
    """Check built from `codex login status` (exit 0 + 'Logged in…' when signed in)."""
    text = result.output.strip().splitlines()[-1] if result.output.strip() else ""
    if result.timed_out or result.error:
        return _check("Signed in", None, "could not read `codex login status`",
                      fix("Run this on the machine to see what's wrong.", "codex login status"))
    if result.returncode == 0 and "logged in" in text.lower() and "not logged in" not in text.lower():
        return _check("Signed in", True, text)
    return _check("Signed in", False, text or "not signed in", CODEX_LOGIN)


def check_codex() -> dict:
    path = shutil.which("codex")
    standalone = install.codex_standalone_binary()
    if not path and not standalone:
        return _missing("codex", "Codex", CODEX_INSTALL)

    if path:
        resolved = os.path.realpath(path)
        kind = install.classify_codex(resolved, str(install.codex_home()))
    else:
        # Not on PATH, but the installer's copy is there.
        path = resolved = str(standalone)
        kind = "standalone"

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_version = pool.submit(runner.run, [path, "--version"], 10)
        # Unknown subcommands fall back to the top-level help with exit 0, so parse
        # the Commands: list instead of trusting an exit code.
        f_help = pool.submit(runner.run, [path, "--help"], 10)
        f_login = pool.submit(runner.run, [path, "login", "status"], 15)
    version_res, help_res, login_res = f_version.result(), f_help.result(), f_login.result()

    rc_supported = help_lists_command(help_res.output, "remote-control")
    checks = [
        _check(
            "Remote control supported",
            rc_supported,
            "experimental in Codex" if rc_supported else "this version has no `codex remote-control`",
            fix("Update Codex.", CODEX_UPDATE.get(kind)),
        ),
        codex_login_check(login_res),
    ]

    return {
        "tool": "codex",
        "name": "Codex",
        "installed": True,
        "path": path,
        "install": install.describe(kind, path, resolved),
        "standalone": str(standalone) if standalone else None,
        "version": parse_version(version_res.output),
        "checks": checks,
        "verdict": _verdict(True, checks),
        "notes": [
            "OpenAI only lets a machine register for remote control when the ChatGPT account "
            "has multi-factor authentication turned on; that is not checked here.",
            "Pairing with the ChatGPT app is not checked yet.",
        ],
    }


def attention(tools: dict) -> list[dict]:
    """Everything the user has to fix, across tools.

    A tool that isn't installed is left out: plenty of people use only one of them.
    """
    items = []
    for t in tools.values():
        if not t.get("installed"):
            continue
        for c in t.get("checks", []):
            if c["ok"] is not True:
                items.append({"tool": t["tool"], "name": t["name"], "problem": c["label"],
                              "detail": c["detail"], "certain": c["ok"] is False, "fix": c["fix"]})
    return items


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
