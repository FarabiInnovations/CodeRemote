import os
import stat

import pytest
from fastapi.testclient import TestClient

from coderemote.config import load_or_create_token
from coderemote.server import create_app


class FakeCache:
    def get(self, refresh=False):
        return {"claude": {"verdict": "ready"}, "codex": {"verdict": "missing"}}


AUTH = {"Authorization": "Bearer secret-token"}


def client():
    return TestClient(create_app("secret-token", cache=FakeCache()))


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/status"),
    ("GET", "/api/fs"),
    ("GET", "/api/settings"),
    ("PUT", "/api/settings"),
])
def test_every_api_route_requires_token(method, path):
    # A 404 here would mean the static mount is swallowing the route.
    c = client()
    assert c.request(method, path).status_code == 401
    assert c.request(method, path, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_status_with_token():
    res = client().get("/api/status", headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["tools"]["claude"]["verdict"] == "ready"
    assert "label" in body["platform"]


def test_page_is_served():
    res = client().get("/")
    assert res.status_code == 200 and "CodeRemote" in res.text


def test_token_is_created_once_and_private(tmp_path):
    first = load_or_create_token(tmp_path)
    assert load_or_create_token(tmp_path) == first
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "token").stat().st_mode) == 0o600


def test_fs_lists_given_folder(tmp_path):
    (tmp_path / "proj" / ".git").mkdir(parents=True)
    res = client().get("/api/fs", params={"path": str(tmp_path)}, headers=AUTH)
    assert res.status_code == 200
    assert res.json()["entries"] == [{"name": "proj", "path": str(tmp_path / "proj"), "git": True}]


def test_fs_errors_map_to_status_codes(tmp_path):
    (tmp_path / "f.txt").write_text("x")
    c = client()
    assert c.get("/api/fs", params={"path": str(tmp_path / "nope")}, headers=AUTH).status_code == 404
    assert c.get("/api/fs", params={"path": str(tmp_path / "f.txt")}, headers=AUTH).status_code == 400


def test_fs_without_path_uses_projects_root(tmp_path):
    c = client()
    c.put("/api/settings", json={"projects_root": str(tmp_path)}, headers=AUTH)
    assert c.get("/api/fs", headers=AUTH).json()["path"] == str(tmp_path.resolve())


def test_settings_round_trip(tmp_path):
    c = client()
    assert c.get("/api/settings", headers=AUTH).json()["projects_root"]["source"] == "guessed"
    res = c.put("/api/settings", json={"projects_root": str(tmp_path)}, headers=AUTH)
    assert res.status_code == 200
    assert res.json()["projects_root"] == {"path": str(tmp_path.resolve()), "source": "saved"}
    assert c.get("/api/settings", headers=AUTH).json()["projects_root"]["source"] == "saved"


def test_settings_rejects_missing_folder(tmp_path):
    res = client().put("/api/settings", json={"projects_root": str(tmp_path / "nope")}, headers=AUTH)
    assert res.status_code == 404


def test_saved_root_that_disappears_falls_back_to_guess(tmp_path):
    gone = tmp_path / "gone"
    gone.mkdir()
    c = client()
    c.put("/api/settings", json={"projects_root": str(gone)}, headers=AUTH)
    gone.rmdir()
    assert c.get("/api/settings", headers=AUTH).json()["projects_root"]["source"] == "guessed"
