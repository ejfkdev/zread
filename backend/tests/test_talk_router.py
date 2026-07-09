# -*- coding: utf-8 -*-
"""Talk router tests: create → message (SSE) → finish → delete.

The LLM stream is mocked so no real provider is hit. The repo is pre-seeded
with chunks so retrieval returns context without network access.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

from app.chunker import Chunk
from app.main import app
from fastapi.testclient import TestClient

from app.indexer import _replace_chunks

client = TestClient(app)


def _seed_repo(repo_id="owner/repo@main"):
    """Insert chunks so retrieval finds context without hitting the embedder."""
    from app.db import get_db

    db = get_db()
    db.execute(
        "INSERT INTO repos(repo_id, owner, repo, ref, status, indexed_at) "
        "VALUES(?,?,?,?, 'success', 0)",
        (repo_id, "owner", "repo", "main"),
    )
    db.commit()
    chunks = [Chunk("docs.md", "Intro", 0, "Goroutines are scheduled cooperatively.", 8)]
    vectors = [[1.0, 0.0] + [0.0] * 6]
    _replace_chunks(db, repo_id, chunks, vectors)


async def _fake_answer_stream(*args, **kwargs):
    """Yield two text deltas then stop — simulates a streamed LLM reply."""
    yield ("Hello ", "")
    yield ("world.", "")


def _parse_sse(raw: str):
    """Parse a raw SSE stream into [(event, data_dict), ...]."""
    events = []
    for block in raw.strip().split("\n\n"):
        lines = block.strip().split("\n")
        event = None
        data = None
        for line in lines:
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        if event:
            events.append((event, data))
    return events


def test_create_talk():
    _seed_repo()
    r = client.post("/api/v1/talk", json={"repo_id": "owner/repo@main"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert "talk_id" in body["data"]


def test_full_talk_lifecycle_sse():
    _seed_repo()
    # Create talk.
    r = client.post("/api/v1/talk", json={"repo_id": "owner/repo@main"})
    talk_id = r.json()["data"]["talk_id"]

    with patch("app.routers.talk.answer_stream", _fake_answer_stream), patch(
        "app.routers.talk.ensure_indexed", new=AsyncMock(return_value=None)
    ):
        # Send message — expect an SSE stream.
        r = client.post(
            f"/api/v1/talk/{talk_id}/message",
            json={"query": "How are goroutines scheduled?"},
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        events = _parse_sse(r.text)

    # Must contain at least: answer deltas, round_finish, finish.
    event_names = [e for e, _ in events]
    assert "answer" in event_names
    assert "round_finish" in event_names
    assert events[-1][0] == "finish"

    # round_finish carries the full concatenated text.
    round_finish = [d for e, d in events if e == "round_finish"][0]
    assert round_finish["text"] == "Hello world."

    # Delete talk.
    d = client.delete(f"/api/v1/talk/{talk_id}")
    assert d.status_code == 200
    assert d.json()["data"]["deleted"] is True


def test_message_unknown_talk_404():
    r = client.post(
        "/api/v1/talk/does-not-exist/message",
        json={"query": "anything"},
    )
    assert r.status_code == 404


def test_error_event_on_failure():
    _seed_repo()
    r = client.post("/api/v1/talk", json={"repo_id": "owner/repo@main"})
    talk_id = r.json()["data"]["talk_id"]

    async def _boom(*a, **kw):
        raise RuntimeError("boom")
        yield  # noqa: unreachable — makes this an async generator

    with patch("app.routers.talk.answer_stream", _boom), patch(
        "app.routers.talk.ensure_indexed", new=AsyncMock(return_value=None)
    ):
        r = client.post(f"/api/v1/talk/{talk_id}/message", json={"query": "x"})

    events = _parse_sse(r.text)
    assert any(e == "error" for e, _ in events)
