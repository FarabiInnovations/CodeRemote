import sys

import pytest

from coderemote import install

HOME = "/home/alice"


@pytest.mark.parametrize("resolved,kind", [
    ("/home/alice/.local/share/claude/versions/2.1.294", "native"),
    ("/home/alice/.claude/local/node_modules/.bin/claude", "native"),
    ("/usr/lib/node_modules/@anthropic-ai/claude-code/cli.js", "npm"),
    ("/home/alice/.nvm/versions/node/v22/lib/node_modules/@anthropic-ai/claude-code/cli.js", "npm"),
    ("C:\\Users\\alice\\AppData\\Roaming\\npm\\node_modules\\@anthropic-ai\\claude-code\\cli.js", "npm"),
    ("/opt/homebrew/Caskroom/claude-code/2.1.0/claude", "homebrew"),
    ("/opt/somewhere/else/claude", "unknown"),
])
def test_classify_claude(resolved, kind):
    assert install.classify_claude(resolved, HOME) == kind


@pytest.mark.parametrize("resolved,kind", [
    ("/home/alice/.codex/packages/standalone/current/codex", "standalone"),
    ("/usr/lib/node_modules/@openai/codex/bin/codex.js", "npm"),
    ("/opt/homebrew/Cellar/codex/0.146.0/bin/codex", "homebrew"),
    ("/usr/local/bin/codex-custom", "unknown"),
])
def test_classify_codex(resolved, kind):
    assert install.classify_codex(resolved, "/home/alice/.codex") == kind


def test_codex_standalone_binary(tmp_path):
    assert install.codex_standalone_binary(tmp_path) is None
    binary = tmp_path / "packages" / "standalone" / "current" / ("codex.exe" if sys.platform == "win32" else "codex")
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    assert install.codex_standalone_binary(tmp_path) == binary


def test_codex_home_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert install.codex_home() == tmp_path


def test_describe_has_label():
    assert install.describe("npm", "/usr/bin/codex", "/x")["label"] == "npm package"
