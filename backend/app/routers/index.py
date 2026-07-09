# -*- coding: utf-8 -*-
"""Indexing router: POST .../index, GET .../status."""

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.db import get_db
from app.models import Envelope, IndexRequest, RepoStatus, err, ok
from app.indexer import index_repo

router = APIRouter(tags=["index"])
_log = logging.getLogger("zread_ai.index_router")


def _repo_id(owner: str, name: str, ref: str) -> str:
    return f"{owner}/{name}@{ref}"


@router.post("/repos/{owner}/{name}/index")
async def index_endpoint(
    owner: str,
    name: str,
    ref: str = Query(default="", description="Branch/tag/commit; empty = default branch"),
) -> Dict[str, Any]:
    """Kick off background indexing. Idempotent per {owner}/{name}@{ref}."""
    import asyncio

    repo_ref = ref or ""  # resolved inside index_repo
    repo_id = _repo_id(owner, name, repo_ref or "default")

    # Mark indexing immediately so a concurrent status check sees it.
    db = get_db()
    db.execute(
        "INSERT INTO repos(repo_id, owner, repo, ref, status, indexed_at) "
        "VALUES(?,?,?,?, 'indexing', ?) "
        "ON CONFLICT(repo_id) DO UPDATE SET status='indexing', error=NULL, indexed_at=excluded.indexed_at",
        (repo_id, owner, name, repo_ref or "", time.time()),
    )
    db.commit()

    # Fire and forget; the task updates repos.status when done.
    asyncio.create_task(index_repo(owner, name, repo_ref))
    return ok({"repo_id": repo_id, "status": "indexing"})


@router.get("/repos/{owner}/{name}/status")
async def status_endpoint(owner: str, name: str, ref: str = Query(default="")) -> Dict[str, Any]:
    """Return indexing status + counts."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM repos WHERE owner=? AND repo=? AND (ref=? OR ?='') ORDER BY indexed_at DESC LIMIT 1",
        (owner, name, ref, ref),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{owner}/{name} not indexed")
    status = RepoStatus(
        repo_id=row["repo_id"],
        owner=row["owner"],
        repo=row["repo"],
        ref=row["ref"],
        status=row["status"],
        file_count=row["file_count"],
        chunk_count=row["chunk_count"],
        indexed_at=row["indexed_at"],
        error=row["error"],
    )
    return ok(status.model_dump())
