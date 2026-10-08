import os
import signal
import stat
import sys
import time

import pytest

from coderemote import launcher

URL = "https://claude.ai/code?environment=env_016XDvBrr4DPZ3AXvhHS6znr"

# Trimmed from a real `claude remote-control` log (2.1.294): redraws, cursor moves, an OSC-8 link.
CLAUDE_CONNECTED = (
    "\n·|· Connecting · CodeRemote · main\n"
    "\x1b[1A\x1b[J·✔︎· Connected · CodeRemote · main\n"
    "    Capacity: 1/32 · New sessions will be created in the current directory\n"
    f"    \x1b]8;;{URL}\x07session\x1b]8;;\x07\n\n"
    f"Continue coding in the Claude mobile app or {URL}\n"
)
CLAUDE_UNTRUSTED = ("Error: Workspace not trusted. Please run `claude` in /tmp/x first to review "
                    "and accept the workspace trust dialog.\n")
# Trimmed from a real `codex remote-control` run (0.146.0) with RUST_LOG set.
CODEX_MFA = (
    "Starting app-server with remote control enabled...\n"
    "\x1b[2m2026-10-08T14:51:03Z\x1b[0m \x1b[33m WARN\x1b[0m failed to connect error=remote control server "
    "enrollment failed at `https://chatgpt.com/backend-api/wham/remote/control/server/enroll`: "
    'HTTP 403 Forbidden, body: {"detail":"Multi-factor authentication required"}; retrying\n'
    "Error: Remote control is enabled on bacteria but the connection is errored.\n"
)


def test_strip_ansi_removes_colors_cursor_moves_and_links():
    assert launcher.strip_ansi("\x1b[2mdim\x1b[0m \x1b[1A\x1b[Jx \x1b]8;;http://a\x07link\x1b]8;;\x07") == "dim x link"


def test_claude_connected():
    r = launcher.parse_claude(CLAUDE_CONNECTED, exited=False)
    assert r["status"] == "connected" and r["url"] == URL


def test_claude_still_connecting_is_pending():
    assert launcher.parse_claude("·|· Connecting · x\n", exited=False)["status"] == "pending"


def test_claude_untrusted():
    assert launcher.parse_claude(CLAUDE_UNTRUSTED, exited=True)["status"] == "untrusted"


def test_claude_other_failure_shows_error_line():
    r = launcher.parse_claude("Error: You must be logged in to use Remote Control\n", exited=True)
    assert r["status"] == "failed" and r["message"] == "You must be logged in to use Remote Control"


def test_codex_mfa_failure_is_explained():
    r = launcher.parse_codex(CODEX_MFA, exited=True)
    assert r["status"] == "failed"
    assert "multi-factor authentication" in r["message"]


# Real output from codex-cli 0.161.0 while signed out, with RUST_LOG set (trimmed).
CODEX_SIGNED_OUT = (
    "Starting app-server with remote control enabled...\n"
    "2026-10-08T15:58:45Z  WARN codex_app_server_transport::transport::remote_control::websocket: "
    "failed to connect to app-server remote control websocket websocket_url=wss://chatgpt.com/x "
    "server_name=bacteria error=remote control requires ChatGPT authentication error_kind=PermissionDenied "
    "reconnect_attempt=1\n"
    "2026-10-08T15:58:45Z  WARN codex_core_plugins: error=remote featured plugin request failed with "
    'status 401 Unauthorized: {"detail":"Unauthorized"}\n'
    "Error: Remote control is enabled on bacteria but the connection is errored.\n"
)
# codex-cli 0.161.0 with umask 002 (stderr of the CLI itself).
CODEX_SOCKET = (
    "Starting app-server with remote control enabled...\n"
    "Error: foreground app-server exited before remote control became ready\n"
    "Caused by:\n    socket parent must be owned by the user or root and prevent other users from "
    "replacing socket entries\n"
)


def test_codex_signed_out_ignores_unrelated_plugin_error():
    r = launcher.parse_codex(CODEX_SIGNED_OUT, exited=True)
    assert "isn't signed in" in r["message"]
    assert "codex login --device-auth" in r["message"]


def test_codex_socket_folder_error_is_recognised():
    assert "socket folder" in launcher.parse_codex(CODEX_SOCKET, exited=True)["message"]


def test_codex_unknown_connect_error_is_passed_through():
    text = ("WARN x: failed to connect to app-server remote control websocket url=y "
            "error=something new broke error_kind=Other\nError: connection is errored\n")
    assert launcher.parse_codex(text, exited=True)["message"] == "something new broke"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX umask")
def test_codex_launch_drops_group_write_from_umask(monkeypatch):
    monkeypatch.setattr(launcher, "_UMASK", 0o002)
    assert launcher._detach_kwargs("codex")["umask"] == 0o022
    assert "umask" not in launcher._detach_kwargs("claude")  # Claude keeps the user's umask
    monkeypatch.setattr(launcher, "_UMASK", 0o022)
    assert "umask" not in launcher._detach_kwargs("codex")


def test_codex_failure_without_detail_uses_error_line():
    r = launcher.parse_codex("Error: Not logged in\n", exited=True)
    assert r["message"] == "Not logged in"


def test_codex_running_without_marker_is_pending():
    assert launcher.parse_codex("Starting app-server with remote control enabled...\n", False)["status"] == "pending"


def test_codex_gets_rust_log_and_claude_gets_name(tmp_path):
    argv, env = launcher.command("claude", "/bin/claude", str(tmp_path / "my-proj"))
    assert argv == ["/bin/claude", "remote-control", "--name=my-proj"]
    argv, _ = launcher.command("claude", "/bin/claude", str(tmp_path / "-rf"))
    assert argv[-1] == "--name=-rf"
    argv, env = launcher.command("codex", "/bin/codex", str(tmp_path))
    assert argv == ["/bin/codex", "remote-control"]
    assert "remote_control=info" in env["RUST_LOG"]


def test_log_path_is_per_tool_and_folder(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert launcher.log_path("claude", str(a)) == launcher.log_path("claude", str(a))
    assert launcher.log_path("claude", str(a)) != launcher.log_path("claude", str(b))
    assert launcher.log_path("claude", str(a)) != launcher.log_path("codex", str(a))
    if os.name == "posix":
        assert (launcher.logs_dir().stat().st_mode & 0o777) == 0o700


# ---- real launches with fake CLIs ---------------------------------------------------------

def fake_tool(tmp_path, body):
    path = tmp_path / "fake-tool"
    path.write_text(f"#!{sys.executable}\nimport sys, time, os\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def stop(result):
    try:
        os.killpg(result["pid"], signal.SIGTERM)
    except ProcessLookupError:
        pass


pytestmark_posix = pytest.mark.skipif(sys.platform == "win32", reason="fake tools use a shebang")


@pytestmark_posix
def test_launch_connected_runs_detached_in_the_folder(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    binary = fake_tool(tmp_path, (
        "open('cwd.txt', 'w').write(os.getcwd())\n"
        f"print('Connected', flush=True); print({URL!r}, flush=True)\n"
        "time.sleep(60)"
    ))
    result = launcher.launch("claude", binary, str(project), timeout=10)
    try:
        assert result["status"] == "connected" and result["url"] == URL
        assert os.getpgid(result["pid"]) == result["pid"]  # its own process group: detached
        assert os.getpgid(result["pid"]) != os.getpgid(0)
        assert (project / "cwd.txt").read_text() == str(project)
    finally:
        stop(result)


@pytestmark_posix
def test_launch_untrusted(tmp_path):
    binary = fake_tool(tmp_path, f"print({CLAUDE_UNTRUSTED!r}); sys.exit(1)")
    assert launcher.launch("claude", binary, str(tmp_path), timeout=10)["status"] == "untrusted"


@pytestmark_posix
def test_launch_codex_failure_reason(tmp_path):
    binary = fake_tool(tmp_path, f"print({CODEX_MFA!r}); sys.exit(1)")
    result = launcher.launch("codex", binary, str(tmp_path), timeout=10)
    assert result["status"] == "failed" and "multi-factor" in result["message"]


@pytestmark_posix
def test_launch_without_confirmation_reports_started(tmp_path):
    binary = fake_tool(tmp_path, "print('booting', flush=True); time.sleep(60)")
    start = time.monotonic()
    result = launcher.launch("codex", binary, str(tmp_path), timeout=1)
    try:
        assert result["status"] == "started"
        assert time.monotonic() - start < 5
    finally:
        stop(result)


@pytestmark_posix
def test_previous_launch_log_is_not_mistaken_for_this_one(tmp_path):
    # Regression: "Trust and start" read the earlier attempt's "Workspace not trusted" log.
    launcher.log_path("claude", str(tmp_path)).write_text(CLAUDE_UNTRUSTED)
    binary = fake_tool(tmp_path, (
        "time.sleep(0.5)\n"
        f"print('Connected', flush=True); print({URL!r}, flush=True)\n"
        "time.sleep(60)"
    ))
    result = launcher.launch("claude", binary, str(tmp_path), timeout=10)
    try:
        assert result["status"] == "connected"
    finally:
        stop(result)


ALREADY_SERVED = ("Error: This folder is already served by a terminal `claude remote-control` "
                  "on this device. Stop it first.\nExiting in about 72 seconds.\n")


def test_claude_already_running_is_reported_while_the_process_lingers():
    r = launcher.parse_claude(ALREADY_SERVED, exited=False)  # real CLI keeps running ~72 s
    assert r["status"] == "failed" and r["already_running"]
    assert "already running" in r["message"]


def test_claude_error_line_fails_without_waiting_for_exit():
    assert launcher.parse_claude("Error: something broke\n", exited=False)["status"] == "failed"


@pytestmark_posix
def test_lingering_failed_launch_is_reported_fast_and_stopped(tmp_path):
    binary = fake_tool(tmp_path, f"print({ALREADY_SERVED!r}, flush=True); time.sleep(60)")
    start = time.monotonic()
    result = launcher.launch("claude", binary, str(tmp_path), timeout=10)
    assert result["status"] == "failed" and result["already_running"]
    assert time.monotonic() - start < 5
    proc = next(p for p in launcher._children if p.pid == result["pid"])
    try:
        proc.wait(timeout=5)  # the duplicate we started gets stopped
    except Exception:
        stop(result)
        pytest.fail("failed launch was left running")
