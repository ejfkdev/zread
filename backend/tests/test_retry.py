# -*- coding: utf-8 -*-
"""Retry/backoff tests: GitHub 429 on raw fetch, embedding 503, error-status recording.

These cover the robustness fixes for large repos: transient rate-limiting
and provider exhaustion must not kill the whole indexing run.
"""

import asyncio

import httpx
import pytest
import respx

from app.config import settings
from app.embedder import embed_texts
from app.github import fetch_raw


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Make asyncio.sleep a no-op so retries don't slow the tests."""
    async def _noop(*_a, **_kw):
        return None
    monkeypatch.setattr(asyncio, "sleep", _noop)


# ---------------------------------------------------------------------------
# GitHub raw fetch: retries on 429/503 then succeeds
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_raw_retries_on_429():
    url = f"{settings.github_raw_url}/o/r/main/file.md"
    route = respx.get(url)
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "0"}),
        httpx.Response(200, text="# hi"),
    ]
    async with httpx.AsyncClient() as c:
        text = await fetch_raw(c, "o", "r", "main", "file.md")
    assert text == "# hi"
    assert route.call_count == 2


@respx.mock
async def test_fetch_raw_retries_on_503():
    url = f"{settings.github_raw_url}/o/r/main/file.md"
    route = respx.get(url)
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, text="ok"),
    ]
    async with httpx.AsyncClient() as c:
        text = await fetch_raw(c, "o", "r", "main", "file.md")
    assert text == "ok"
    assert route.call_count == 3


@respx.mock
async def test_fetch_raw_404_still_returns_none():
    respx.get(f"{settings.github_raw_url}/o/r/main/missing.md").mock(
        return_value=httpx.Response(404)
    )
    async with httpx.AsyncClient() as c:
        text = await fetch_raw(c, "o", "r", "main", "missing.md")
    assert text is None


# ---------------------------------------------------------------------------
# Embeddings: retries on 429/503 then succeeds
# ---------------------------------------------------------------------------


@respx.mock
async def test_embed_retries_on_503():
    url = f"{settings.resolved_embed_base_url}/embeddings"
    route = respx.post(url)
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}),
    ]
    async with httpx.AsyncClient() as c:
        vecs = await embed_texts(c, ["hello"])
    assert vecs == [[0.1, 0.2, 0.3]]
    assert route.call_count == 2


@respx.mock
async def test_embed_retries_on_429():
    url = f"{settings.resolved_embed_base_url}/embeddings"
    route = respx.post(url)
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "0"}),
        httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]}),
    ]
    async with httpx.AsyncClient() as c:
        vecs = await embed_texts(c, ["x"])
    assert vecs == [[1.0]]


@respx.mock
async def test_embed_persistent_500_raises():
    """A non-transient 500 should raise immediately, not retry."""
    url = f"{settings.resolved_embed_base_url}/embeddings"
    respx.post(url).mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as c:
        with pytest.raises(httpx.HTTPStatusError):
            await embed_texts(c, ["x"])


# ---------------------------------------------------------------------------
# _mark_error records the failure on all rows for owner/repo
# ---------------------------------------------------------------------------


def test_mark_error_updates_status(db):
    """Even an unresolved '@default' placeholder row gets marked as error."""
    import time
    from app.indexer import _mark_error

    db.execute(
        "INSERT INTO repos(repo_id, owner, repo, ref, status, indexed_at) "
        "VALUES(?,?,?,?, 'indexing', ?)",
        ("RIMTHAN-LAB/mass-monorepo@default", "RIMTHAN-LAB", "mass-monorepo", "", time.time()),
    )
    db.commit()

    _mark_error(db, "RIMTHAN-LAB", "mass-monorepo", "GitHub 429 rate limit")

    row = db.execute(
        "SELECT status, error FROM repos WHERE owner=? AND repo=?",
        ("RIMTHAN-LAB", "mass-monorepo"),
    ).fetchone()
    assert row["status"] == "error"
    assert "429" in row["error"]
