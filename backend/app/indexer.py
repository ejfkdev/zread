# -*- coding: utf-8 -*-
"""Indexing pipeline: fetch repo → filter docs → chunk → embed → store.

Idempotent: re-indexing the same {owner}/{repo}@{ref} wipes old rows in a
transaction before inserting fresh ones.
"""

import logging
import struct
import time
from typing import List

import httpx

from app.chunker import Chunk, chunk_markdown
from app.config import settings
from app.db import get_db
from app.embedder import embed_texts
from app.github import (
    GitHubError,
    fetch_files_concurrent,
    fetch_tree,
    filter_doc_files,
    get_default_branch,
)

_log = logging.getLogger("zread_ai.indexer")


def _vec_to_blob(vec: List[float]) -> bytes:
    """Pack a float vector into the little-endian blob sqlite-vec expects."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _repo_id(owner: str, repo: str, ref: str) -> str:
    return f"{owner}/{repo}@{ref}"


async def index_repo(owner: str, repo: str, ref: str = "") -> None:
    """Full indexing run for one repo. Updates repos.status throughout."""
    db = get_db()
    async with httpx.AsyncClient() as client:
        try:
            resolved = ref or await get_default_branch(client, owner, repo)
            repo_id = _repo_id(owner, repo, resolved)
            _log.info("Indexing %s ...", repo_id)

            # Update the tracking row with the resolved ref.
            db.execute(
                "UPDATE repos SET ref=?, status='indexing' WHERE repo_id=?",
                (resolved, _repo_id(owner, repo, "")),
            )
            db.execute(
                "INSERT INTO repos(repo_id, owner, repo, ref, status, indexed_at) "
                "VALUES(?,?,?,?, 'indexing', ?) "
                "ON CONFLICT(repo_id) DO UPDATE SET status='indexing', error=NULL, indexed_at=excluded.indexed_at",
                (repo_id, owner, repo, resolved, time.time()),
            )
            db.commit()

            files = await fetch_tree(client, owner, repo, resolved)
            doc_files = filter_doc_files(files)
            _log.info("Found %d doc files for %s", len(doc_files), repo_id)

            downloaded = await fetch_files_concurrent(
                client, owner, repo, resolved, [f["path"] for f in doc_files]
            )

            all_chunks: List[Chunk] = []
            for path, text in downloaded:
                all_chunks.extend(chunk_markdown(path, text))
            _log.info("Produced %d chunks for %s", len(all_chunks), repo_id)

            # Embed in batches.
            texts = [c.content for c in all_chunks]
            vectors = await embed_texts(client, texts) if texts else []

            # Atomic replace: delete old chunks/embeddings, insert new.
            _replace_chunks(db, repo_id, all_chunks, vectors)

            db.execute(
                "UPDATE repos SET status='success', file_count=?, chunk_count=?, indexed_at=?, error=NULL WHERE repo_id=?",
                (len(downloaded), len(all_chunks), time.time(), repo_id),
            )
            db.commit()
            _log.info("Indexed %s: %d files, %d chunks", repo_id, len(downloaded), len(all_chunks))
        except (GitHubError, httpx.HTTPError) as exc:
            _log.exception("Indexing failed for %s/%s", owner, repo)
            _mark_error(db, owner, repo, ref, str(exc))
        except Exception as exc:  # noqa: BLE001 — never crash the task worker
            _log.exception("Unexpected indexing error for %s/%s", owner, repo)
            _mark_error(db, owner, repo, ref, str(exc))


def _replace_chunks(
    db,
    repo_id: str,
    chunks: List[Chunk],
    vectors: List[List[float]],
) -> None:
    """Delete old rows for repo_id, then insert chunks + embeddings."""
    from app.db import _lock

    with _lock:
        old_ids = [
            r[0]
            for r in db.execute(
                "SELECT chunk_id FROM chunks WHERE repo_id=?", (repo_id,)
            ).fetchall()
        ]
        # vec0 rows must be deleted one-by-one (no WHERE on virtual tables).
        for cid in old_ids:
            db.execute("DELETE FROM embeddings WHERE chunk_id=?", (cid,))
        db.execute("DELETE FROM chunks WHERE repo_id=?", (repo_id,))

        for chunk, vec in zip(chunks, vectors):
            cur = db.execute(
                "INSERT INTO chunks(repo_id, file_path, heading, ordinal, content, token_count) "
                "VALUES(?,?,?,?,?,?)",
                (repo_id, chunk.file_path, chunk.heading, chunk.ordinal, chunk.content, chunk.token_count),
            )
            cid = cur.lastrowid
            db.execute(
                "INSERT INTO embeddings(chunk_id, embedding) VALUES (?, ?)",
                (cid, _vec_to_blob(vec)),
            )
        db.commit()


def _mark_error(db, owner: str, repo: str, ref: str, message: str) -> None:
    """Record an indexing failure so the status endpoint can report it."""
    rid = _repo_id(owner, repo, ref or "")
    db.execute(
        "UPDATE repos SET status='error', error=?, indexed_at=? WHERE repo_id=?",
        (message[:500], time.time(), rid),
    )
    db.commit()
