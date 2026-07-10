# -*- coding: utf-8 -*-
"""Talk router tests: create → message (SSE) → finish → delete.

The LLM stream is mocked so no real provider is hit. The repo is pre-seeded
with chunks so retrieval returns context without network access.
"""

import asyncio
import json
import time
from unittest.mock import patch

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
        "app.routers.talk.ensure_indexed_with_progress", _noop_index_progress
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
        yield  # makes this an async generator (unreachable)

    with patch("app.routers.talk.answer_stream", _boom), patch(
        "app.routers.talk.ensure_indexed_with_progress", _noop_index_progress
    ):
        r = client.post(f"/api/v1/talk/{talk_id}/message", json={"query": "x"})

    events = _parse_sse(r.text)
    assert any(e == "error" for e, _ in events)


# ---------------------------------------------------------------------------
# New tests: non-blocking index, talk-deleted race, concurrent first-question
# ---------------------------------------------------------------------------


def test_message_on_unindexed_repo_does_not_block():
    """A first question against an un-indexed repo must not block the HTTP
    response: it streams ``event:status`` progress then the answer.
    """
    repo_id = "owner/repo@main"
    # NOTE: deliberately no _seed_repo() — repo is un-indexed.

    started = []

    async def _slow_index(repo_id):
        """Simulate a non-trivial index that emits progress then succeeds."""
        started.append(time.time())
        yield ("status", {"status": "indexing", "repo_id": repo_id})
        await asyncio.sleep(0.3)  # simulate work
        yield ("status", {"status": "success", "repo_id": repo_id, "chunk_count": 1})

    r = client.post("/api/v1/talk", json={"repo_id": repo_id})
    talk_id = r.json()["data"]["talk_id"]

    # Seed the repo row as success so answer_stream's retrieve() works after
    # the "index" completes, but keep it absent initially so the progress path
    # is exercised. _slow_index simulates the index finishing.
    _seed_repo(repo_id)

    with patch(
        "app.routers.talk.ensure_indexed_with_progress", _slow_index
    ), patch("app.routers.talk.answer_stream", _fake_answer_stream):
        r = client.post(
            f"/api/v1/talk/{talk_id}/message",
            json={"query": "How are goroutines scheduled?"},
        )

    assert r.status_code == 200
    events = _parse_sse(r.text)
    event_names = [e for e, _ in events]

    # Progress events precede the answer.
    assert "status" in event_names
    status_idx = event_names.index("status")
    answer_idx = event_names.index("answer")
    assert status_idx < answer_idx
    # The answer still arrives.
    assert "round_finish" in event_names
    assert events[-1][0] == "finish"


def test_index_failure_emits_error_event():
    """If indexing fails, the stream emits event:error (not a 500/crash)."""
    repo_id = "owner/repo@main"

    async def _failed_index(repo_id):
        yield ("status", {"status": "indexing", "repo_id": repo_id})
        yield (
            "status",
            {"status": "error", "repo_id": repo_id, "error": "boom"},
        )

    r = client.post("/api/v1/talk", json={"repo_id": repo_id})
    talk_id = r.json()["data"]["talk_id"]

    with patch(
        "app.routers.talk.ensure_indexed_with_progress", _failed_index
    ), patch("app.routers.talk.answer_stream", _fake_answer_stream):
        r = client.post(
            f"/api/v1/talk/{talk_id}/message", json={"query": "x"}
        )

    assert r.status_code == 200
    events = _parse_sse(r.text)
    # The error event is emitted and the stream terminates without an answer.
    assert any(e == "error" for e, _ in events)
    assert not any(e == "answer" for e, _ in events)


def test_talk_deleted_mid_stream_emits_error_not_500():
    """If the talk row is deleted while the stream is open, the client gets
    a clean event:error (talk closed), not a 500 or traceback.
    """
    _seed_repo()
    r = client.post("/api/v1/talk", json={"repo_id": "owner/repo@main"})
    talk_id = r.json()["data"]["talk_id"]

    async def _boom_talk_gone(*a, **kw):
        from app.rag import TalkGoneError

        raise TalkGoneError(talk_id)
        yield  # unreachable — makes this an async generator

    with patch(
        "app.routers.talk.ensure_indexed_with_progress", _noop_index_progress
    ), patch("app.routers.talk.answer_stream", _boom_talk_gone):
        r = client.post(
            f"/api/v1/talk/{talk_id}/message", json={"query": "x"}
        )

    assert r.status_code == 200
    events = _parse_sse(r.text)
    err = [d for e, d in events if e == "error"]
    assert err and err[0]["text"] == "talk closed"


def test_concurrent_first_questions_index_once():
    """Two simultaneous first-questions on the same un-indexed repo must
    trigger indexing exactly once (per-repo lock).
    """
    repo_id = "owner/repo@main"
    # Don't seed success — force the index path. We patch index_repo so no
    # network is hit, and count how many times it's called.
    call_count = {"n": 0}

    async def _counting_index(owner, repo, ref=""):
        call_count["n"] += 1
        # Yield control so the second concurrent caller can reach the lock.
        await asyncio.sleep(0.05)
        # Mark the repo success so the lock re-check short-circuits the second
        # caller.
        from app.db import get_db
        import time as _t

        db = get_db()
        db.execute(
            "INSERT INTO repos(repo_id, owner, repo, ref, status, chunk_count, indexed_at) "
            "VALUES(?,?,?,?, 'success', 1, ?) "
            "ON CONFLICT(repo_id) DO UPDATE SET status='success', chunk_count=1",
            (repo_id, owner, repo, ref or "main", _t.time()),
        )
        db.commit()

    from app.rag import ensure_indexed_with_progress

    async def _consume():
        async for _ in ensure_indexed_with_progress(repo_id):
            pass

    async def _driver():
        await asyncio.gather(_consume(), _consume())

    with patch("app.rag.index_repo", _counting_index):
        asyncio.run(_driver())

    assert call_count["n"] == 1


# Helper used by several tests: a no-op index progress generator for repos
# that are already indexed (fast path).
async def _noop_index_progress(repo_id):
    return
    yield  # unreachable — makes this an async generator
