# -*- coding: utf-8 -*-
"""RAG orchestration: ensure repo indexed → retrieve → stream answer."""

import asyncio
import logging
from typing import AsyncIterator, Tuple

import httpx

from app.config import settings
from app.db import get_db
from app.embedder import embed_query
from app.github import GitHubError
from app.indexer import index_repo
from app.llm import build_messages, stream_chat
from app.retriever import retrieve

_log = logging.getLogger("zread_ai.rag")


class TalkGoneError(Exception):
    """Raised when the talk row was deleted while a stream was open."""


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------
# Per-repo locks so two concurrent first-questions on the same repo don't both
# trigger a full index. Keyed by repo_id "{owner}/{repo}@{ref}".
_index_locks: dict[str, asyncio.Lock] = {}


def _get_index_lock(repo_id: str) -> asyncio.Lock:
    lock = _index_locks.get(repo_id)
    if lock is None:
        lock = asyncio.Lock()
        _index_locks[repo_id] = lock
    return lock


def _repo_status(repo_id: str) -> str | None:
    """Return the current repos.status for repo_id, or None if no row."""
    db = get_db()
    row = db.execute(
        "SELECT status FROM repos WHERE repo_id=?", (repo_id,)
    ).fetchone()
    return row["status"] if row else None


async def ensure_indexed(repo_id: str) -> None:
    """If the repo isn't indexed, index it now (blocks the first question).

    The talk router calls this before streaming so the client path is simply
    "ask a question" — no separate index step required. Safe under concurrency:
    a per-repo lock serializes concurrent first-questions.
    """
    async with _get_index_lock(repo_id):
        status = _repo_status(repo_id)
        if status == "success":
            return
        owner, rest = repo_id.split("/", 1)
        repo, _, ref = rest.partition("@")
        try:
            await index_repo(owner, repo, ref)
        except (GitHubError, httpx.HTTPError) as exc:
            _log.warning("ensure_indexed failed for %s: %s", repo_id, exc)


async def ensure_indexed_with_progress(
    repo_id: str,
) -> AsyncIterator[Tuple[str, dict]]:
    """Non-blocking variant of ``ensure_indexed`` that yields SSE-friendly
    progress events while the stream is already open.

    Yields ``(event_name, data_dict)`` pairs:
        ("status", {"status": "indexing" | "success" | "error", ...})
    Before returning, guarantees the repo is either 'success' or has failed.
    Holds the per-repo lock so concurrent first-questions only index once.
    """
    # Fast path: already indexed.
    if _repo_status(repo_id) == "success":
        return
    yield ("status", {"status": "indexing", "repo_id": repo_id})

    async with _get_index_lock(repo_id):
        # Another concurrent caller may have finished indexing while we waited
        # on the lock; re-check.
        status = _repo_status(repo_id)
        if status == "success":
            yield ("status", {"status": "success", "repo_id": repo_id})
            return

        owner, rest = repo_id.split("/", 1)
        repo, _, ref = rest.partition("@")
        try:
            await index_repo(owner, repo, ref)
        except (GitHubError, httpx.HTTPError) as exc:
            _log.warning("ensure_indexed failed for %s: %s", repo_id, exc)
            yield (
                "status",
                {"status": "error", "repo_id": repo_id, "error": str(exc)},
            )
            return

    final = _repo_status(repo_id)
    yield (
        "status",
        {
            "status": final or "error",
            "repo_id": repo_id,
            "chunk_count": _repo_chunk_count(repo_id),
        },
    )


def _repo_chunk_count(repo_id: str) -> int:
    db = get_db()
    row = db.execute(
        "SELECT chunk_count FROM repos WHERE repo_id=?", (repo_id,)
    ).fetchone()
    return row["chunk_count"] if row else 0


def _load_history(talk_id: str) -> list[dict]:
    """Load prior messages (user/assistant) for this talk, most-recent-last."""
    db = get_db()
    rows = db.execute(
        "SELECT role, content FROM talk_messages WHERE talk_id=? ORDER BY id ASC",
        (talk_id,),
    ).fetchall()
    msgs = [{"role": r["role"], "content": r["content"]} for r in rows]
    # Keep only the configured window (drop oldest beyond it).
    if len(msgs) > settings.talk_max_history:
        msgs = msgs[-settings.talk_max_history :]
    return msgs


async def answer_stream(
    talk_id: str, query: str, model: str | None
) -> AsyncIterator[Tuple[str, str]]:
    """Yield (text_delta, reasoning_delta) for one RAG turn.

    Persists the final assistant answer to talk_messages after streaming.
    Raises ``TalkGoneError`` if the talk was deleted mid-stream (e.g. the
    client timed out and cleaned up) — the router converts this into a clean
    SSE error event instead of crashing.
    """
    db = get_db()
    talk = db.execute("SELECT * FROM talks WHERE talk_id=?", (talk_id,)).fetchone()
    if talk is None:
        raise TalkGoneError(talk_id)
    repo_id = talk["repo_id"]

    import time

    full_text = ""
    full_reasoning = ""
    async with httpx.AsyncClient() as client:
        # Retrieve context.
        query_vec = await embed_query(client, query)
        chunks = retrieve(repo_id, query_vec)
        history = _load_history(talk_id)

        owner, rest = repo_id.split("/", 1)
        repo_name = rest.split("@", 1)[0]
        messages = build_messages(f"{owner}/{repo_name}", chunks, history, query)

        async for text_delta, reasoning_delta in stream_chat(client, messages, model):
            if text_delta:
                full_text += text_delta
            if reasoning_delta:
                full_reasoning += reasoning_delta
            yield text_delta, reasoning_delta

    # Persist assistant reply — but no-op if the talk was deleted mid-stream.
    still_there = db.execute(
        "SELECT 1 FROM talks WHERE talk_id=?", (talk_id,)
    ).fetchone()
    if still_there is None:
        raise TalkGoneError(talk_id)
    db.execute(
        "INSERT INTO talk_messages(talk_id, role, content, created_at) VALUES(?,?,?,?)",
        (talk_id, "assistant", full_text, time.time()),
    )
    db.commit()
