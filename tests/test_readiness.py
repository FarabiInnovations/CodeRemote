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


# ---- sign-in parsing and fixes -------------------------------------------------------------

from coderemote.runner import Result  # noqa: E402


def test_claude_signed_in_with_claude_ai():
    out = '{"loggedIn": true, "authMethod": "claude.ai", "subscriptionType": "max"}'
    checks = readiness.claude_auth_checks(out)
    assert [c["ok"] for c in checks] == [True, True]
    assert checks[0]["detail"] == "claude.ai · max plan"
    assert all(c["fix"] is None for c in checks)  # nothing to fix


def test_claude_logged_out_tells_user_to_log_in():
    (check,) = readiness.claude_auth_checks('{"loggedIn": false}')
    assert check["ok"] is False
    assert check["fix"]["command"] == "claude auth login"


def test_claude_api_key_login_is_not_enough():
    checks = readiness.claude_auth_checks('{"loggedIn": true, "authMethod": "apiKey"}')
    assert [c["ok"] for c in checks] == [True, False]
    assert checks[1]["fix"]["command"] == "claude auth login --claudeai"


def test_claude_unreadable_status_is_unknown_not_failed():
    (check,) = readiness.claude_auth_checks("something went wrong")
    assert check["ok"] is None
    assert check["fix"]["command"] == "claude auth status"


def test_codex_logged_in():
    check = readiness.codex_login_check(Result("Logged in using ChatGPT\n", 0, False))
    assert check["ok"] is True and check["fix"] is None


def test_codex_logged_out():
    # Real output after `codex logout` (codex-cli 0.161.0): "Not logged in", exit 1.
    check = readiness.codex_login_check(Result("Not logged in\n", 1, False))
    assert check["ok"] is False
    assert check["fix"]["command"] == "codex login --device-auth"


def test_codex_not_logged_in_even_with_exit_zero():
    assert readiness.codex_login_check(Result("Not logged in\n", 0, False))["ok"] is False


def test_codex_login_timeout_is_unknown():
    assert readiness.codex_login_check(Result("", None, True))["ok"] is None


def tool(name, installed, checks):
    return {"tool": name, "name": name.title(), "installed": installed, "checks": checks}


def test_attention_lists_every_unresolved_check():
    ok = readiness._check("A", True)
    bad = readiness._check("Signed in", False, "Not logged in", readiness.CODEX_LOGIN)
    unsure = readiness._check("Status", None, "timed out")
    items = readiness.attention({"claude": tool("claude", True, [ok]),
                                 "codex": tool("codex", True, [ok, bad, unsure])})
    assert [(i["tool"], i["problem"], i["certain"]) for i in items] == [
        ("codex", "Signed in", True),
        ("codex", "Status", False),
    ]
    assert items[0]["fix"]["command"] == "codex login --device-auth"


def test_attention_ignores_tools_that_are_not_installed():
    assert readiness.attention({"codex": readiness._missing("codex", "Codex", readiness.CODEX_INSTALL)}) == []


def test_missing_tool_carries_install_fix(monkeypatch):
    monkeypatch.setattr(readiness.shutil, "which", lambda name: None)
    monkeypatch.setattr(readiness.install, "codex_standalone_binary", lambda: None)
    assert readiness.check_claude()["fix"]["command"]
    assert readiness.check_codex()["fix"]["command"] == "npm install -g @openai/codex"
