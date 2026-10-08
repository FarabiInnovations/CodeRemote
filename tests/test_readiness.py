from coderemote import readiness

CODEX_HELP = """Codex CLI

Commands:
  exec            Run Codex non-interactively [aliases: e]
  remote-control  [experimental] Manage the app-server daemon with remote control enabled
  help            Print this message

Arguments:
  [PROMPT]
"""


def test_parse_version_formats():
    assert readiness.parse_version("2.1.294 (Claude Code)") == "2.1.294"
    assert readiness.parse_version("codex-cli 0.146.0") == "0.146.0"
    assert readiness.parse_version("no version here") is None


def test_help_lists_command():
    assert readiness.help_lists_command(CODEX_HELP, "remote-control")
    assert not readiness.help_lists_command(CODEX_HELP, "remote")
    # A mention outside the Commands: block does not count.
    assert not readiness.help_lists_command("Usage: x\n  remote-control is cool\n", "remote-control")


def test_verdicts():
    ok, bad, unsure = {"ok": True}, {"ok": False}, {"ok": None}
    assert readiness._verdict(False, []) == "missing"
    assert readiness._verdict(True, [ok, ok]) == "ready"
    assert readiness._verdict(True, [ok, bad, unsure]) == "not_ready"
    assert readiness._verdict(True, [ok, unsure]) == "unknown"


def test_missing_tool(monkeypatch):
    monkeypatch.setattr(readiness.shutil, "which", lambda name: None)
    assert readiness.check_claude()["verdict"] == "missing"
    assert readiness.check_codex()["verdict"] == "missing"
