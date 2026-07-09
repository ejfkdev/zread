# -*- coding: utf-8 -*-
"""RAG orchestration: ensure repo indexed → retrieve → stream answer."""

import logging
from typing import AsyncIterator, Tuple

import httpx

from app.config import settings
from app.db import get_db
from app.embedder import embed_query
from app.github import GitHubError
from app.indexer import index_repo, _repo_id
from app.llm import build_messages, stream_chat
from app.retriever import retrieve

_log = logging.getLogger("zread_ai.rag")


async def ensure_indexed(repo_id: str) -> None:
    """If the repo isn't indexed, index it now (blocks the first question).

    The talk router calls this before streaming so the client path is simply
    "ask a question" — no separate index step required.
    """
    db = get_db()
    row = db.execute(
        "SELECT status FROM repos WHERE repo_id=?", (repo_id,)
    ).fetchone()
    if row and row["status"] == "success":
        return
    # Parse repo_id "{owner}/{repo}@{ref}" and index.
    owner, rest = repo_id.split("/", 1)
    repo, _, ref = rest.partition("@")
    try:
        await index_repo(owner, repo, ref)
    except (GitHubError, httpx.HTTPError) as exc:
        _log.warning("ensure_indexed failed for %s: %s", repo_id, exc)


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
    """
    db = get_db()
    talk = db.execute("SELECT * FROM talks WHERE talk_id=?", (talk_id,)).fetchone()
    if talk is None:
        raise ValueError(f"talk {talk_id} not found")
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

    # Persist assistant reply.
    db.execute(
        "INSERT INTO talk_messages(talk_id, role, content, created_at) VALUES(?,?,?,?)",
        (talk_id, "assistant", full_text, time.time()),
    )
    db.commit()
