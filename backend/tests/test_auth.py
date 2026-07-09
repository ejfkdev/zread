# -*- coding: utf-8 -*-
"""Authentication tests for the AI backend API (CWE-306 fix).

Covers:
  - With BACKEND_API_KEY set: missing token -> 401, wrong token -> 401,
    valid token -> 200, /healthz stays open without any token.
  - Constant-time compare semantics (valid prefix still rejected).
  - Talk endpoints gated identically to index endpoints.
"""


import pytest

from app.main import app
from fastapi.testclient import TestClient


VALID_KEY = "s3cret-shared-key-123"


@pytest.fixture
def authed_client(monkeypatch):
    """A TestClient against an app instance configured with a backend API key.

    We rebuild the settings + the auth module's view of it, then instantiate
    a fresh TestClient so the router-level dependency picks up the new value.
    """
    monkeypatch.setenv("BACKEND_API_KEY", VALID_KEY)
    from app import config as _config
    from app import auth as _auth

    monkeypatch.setattr(_config.settings, "backend_api_key", VALID_KEY)
    # Reset the one-shot open-mode warning so it doesn't leak into other tests.
    monkeypatch.setattr(_auth, "_WARNED_OPEN", False)
    return TestClient(app)


def _seed_repo(repo_id="owner/repo@main"):
    from app.db import get_db

    db = get_db()
    db.execute(
        "INSERT INTO repos(repo_id, owner, repo, ref, status, indexed_at) "
        "VALUES(?,?,?,?, 'success', 0)",
        (repo_id, "owner", "repo", "main"),
    )
    db.commit()


# ---------------------------------------------------------------------------
# /healthz is always open (no auth) — it's the Docker healthcheck target.
# ---------------------------------------------------------------------------


def test_healthz_open_without_token(authed_client):
    r = authed_client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_healthz_open_no_auth_header(authed_client):
    # Explicitly no Authorization header.
    r = authed_client.get("/healthz", headers={})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Index endpoints require the key.
# ---------------------------------------------------------------------------


def test_index_rejects_missing_token(authed_client):
    r = authed_client.post("/api/v1/repos/o/r/index")
    assert r.status_code == 401


def test_index_rejects_wrong_token(authed_client):
    r = authed_client.post(
        "/api/v1/repos/o/r/index",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert r.status_code == 401


def test_index_rejects_prefix_match(authed_client):
    # A valid prefix of the key must NOT be accepted (no substring match).
    r = authed_client.post(
        "/api/v1/repos/o/r/index",
        headers={"Authorization": f"Bearer {VALID_KEY[:5]}"},
    )
    assert r.status_code == 401


def test_index_accepts_valid_token(authed_client):
    r = authed_client.post(
        "/api/v1/repos/o/r/index",
        headers={"Authorization": f"Bearer {VALID_KEY}"},
    )
    assert r.status_code == 200
    assert r.json()["code"] == 0


def test_status_rejects_missing_token(authed_client):
    r = authed_client.get("/api/v1/repos/o/r/status")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Talk endpoints require the key.
# ---------------------------------------------------------------------------


def test_talk_create_rejects_missing_token(authed_client):
    r = authed_client.post("/api/v1/talk", json={"repo_id": "owner/repo@main"})
    assert r.status_code == 401


def test_talk_create_accepts_valid_token(authed_client):
    _seed_repo()
    r = authed_client.post(
        "/api/v1/talk",
        json={"repo_id": "owner/repo@main"},
        headers={"Authorization": f"Bearer {VALID_KEY}"},
    )
    assert r.status_code == 200
    assert "talk_id" in r.json()["data"]


def test_talk_message_rejects_missing_token(authed_client):
    _seed_repo()
    r = authed_client.post(
        "/api/v1/talk/any/message",
        json={"query": "hi"},
    )
    assert r.status_code == 401


def test_talk_delete_rejects_missing_token(authed_client):
    r = authed_client.delete("/api/v1/talk/any")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# When the key is UNSET, the API is open (documented fail-open for dev).
# This preserves backward compatibility; the warning is logged at startup.
# ---------------------------------------------------------------------------


def test_api_open_when_key_unset(fresh_db):
    # No BACKEND_API_KEY configured in conftest -> API is open (fail-open).
    c = TestClient(app)
    r = c.post("/api/v1/repos/o/r/index")
    # Not 401 — the endpoint is reachable (it'll then try to index and fail,
    # but the auth gate itself is open).
    assert r.status_code != 401
