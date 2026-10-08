import json
import os
import time
from pathlib import Path

import pytest

from coderemote import claude_config


@pytest.fixture
def cfg():
    path = claude_config.config_path()
    path.write_text(json.dumps({"numStartups": 3, "projects": {"/other": {"allowedTools": ["x"]}}}, indent=2))
    if os.name == "posix":
        path.chmod(0o600)
    return path


def test_config_path_follows_claude_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert claude_config.config_path() == tmp_path / ".claude.json"
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert claude_config.config_path() == Path.home() / ".claude.json"


def test_trust_sets_only_the_flag(cfg, tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    key = claude_config.trust(str(folder))
    data = json.loads(cfg.read_text())
    assert data["projects"][key] == {"hasTrustDialogAccepted": True}
    assert data["projects"]["/other"] == {"allowedTools": ["x"]}  # untouched
    assert data["numStartups"] == 3
    assert claude_config.is_trusted(str(folder))
    if os.name == "posix":
        assert (cfg.stat().st_mode & 0o777) == 0o600
    assert not any(p.name.startswith(".claude.json.coderemote-") for p in cfg.parent.iterdir())


def test_trust_uses_the_real_path(cfg, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert claude_config.trust(str(link)) == str(real.resolve())


def test_trust_keeps_existing_project_settings(cfg, tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    data = json.loads(cfg.read_text())
    data["projects"][claude_config.trust_key(str(folder))] = {"allowedTools": ["Bash"]}
    cfg.write_text(json.dumps(data))
    claude_config.trust(str(folder))
    entry = json.loads(cfg.read_text())["projects"][claude_config.trust_key(str(folder))]
    assert entry == {"allowedTools": ["Bash"], "hasTrustDialogAccepted": True}


def test_refuses_home_and_filesystem_root(cfg, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(claude_config.TrustError, match="home folder"):
        claude_config.trust(str(tmp_path))
    with pytest.raises(claude_config.TrustError, match="top of the filesystem"):
        claude_config.trust(os.path.abspath(os.sep))


def test_missing_or_broken_config_is_not_overwritten(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    with pytest.raises(claude_config.TrustError, match="not found"):
        claude_config.trust(str(folder))
    claude_config.config_path().write_text("{broken")
    with pytest.raises(claude_config.TrustError, match="not valid JSON"):
        claude_config.trust(str(folder))
    assert claude_config.config_path().read_text() == "{broken"


def test_waits_for_lock_then_gives_up(cfg, tmp_path, monkeypatch):
    folder = tmp_path / "proj"
    folder.mkdir()
    lock = cfg.with_name(cfg.name + ".lock")
    lock.mkdir()
    monkeypatch.setattr(claude_config._Lock, "__init__",
                        lambda self, target, timeout=0.3, stale=10.0: (
                            setattr(self, "dir", lock), setattr(self, "timeout", timeout),
                            setattr(self, "stale", stale)) and None)
    with pytest.raises(claude_config.TrustError, match="locked"):
        claude_config.trust(str(folder))
    assert lock.exists()  # someone else's lock is left alone


def test_stale_lock_is_cleared(cfg, tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    lock = cfg.with_name(cfg.name + ".lock")
    lock.mkdir()
    old = time.time() - 60
    os.utime(lock, (old, old))
    claude_config.trust(str(folder))
    assert claude_config.is_trusted(str(folder))
    assert not lock.exists()
