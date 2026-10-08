import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path_factory, monkeypatch):
    """Never read or write the real ~/.config/coderemote or ~/.claude.json during tests.

    Kept outside each test's tmp_path so folder-listing tests don't see these folders.
    """
    env = tmp_path_factory.mktemp("env")
    home = env / "coderemote-home"
    monkeypatch.setenv("CODEREMOTE_HOME", str(home))
    claude_dir = env / "claude-config"
    claude_dir.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_dir))
    return home
