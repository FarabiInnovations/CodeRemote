import os
import stat

from fastapi.testclient import TestClient

from coderemote.config import load_or_create_token
from coderemote.server import create_app


class FakeCache:
    def get(self, refresh=False):
        return {"claude": {"verdict": "ready"}, "codex": {"verdict": "missing"}}


def client():
    return TestClient(create_app("secret-token", cache=FakeCache()))


def test_status_requires_token():
    assert client().get("/api/status").status_code == 401
    assert client().get("/api/status", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_status_with_token():
    res = client().get("/api/status", headers={"Authorization": "Bearer secret-token"})
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
