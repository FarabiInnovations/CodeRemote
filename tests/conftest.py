import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Never read or write the real ~/.config/coderemote during tests."""
    home = tmp_path / "coderemote-home"
    monkeypatch.setenv("CODEREMOTE_HOME", str(home))
    return home
