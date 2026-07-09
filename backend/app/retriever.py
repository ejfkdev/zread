# -*- coding: utf-8 -*-
"""Vector retrieval: embed query → top-k chunks via sqlite-vec."""

import logging
import struct
from typing import Any, Dict, List

from app.config import settings
from app.db import get_db

_log = logging.getLogger("zread_ai.retriever")


def _vec_to_blob(vec: List[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def retrieve(repo_id: str, query_vec: List[float], top_k: int | None = None) -> List[Dict[str, Any]]:
    """Return the top-k chunks for a query vector within a repo.

    sqlite-vec KNN: SELECT chunk_id, distance FROM embeddings
    WHERE embedding MATCH ? AND k = ? ORDER BY distance.
    We then join back to the chunks table and re-filter by repo_id (vec0
    KNN is global, so repo isolation is enforced at the join level).
    """
    k = top_k or settings.retrieval_top_k
    db = get_db()
    qblob = _vec_to_blob(query_vec)
    # vec0 KNN returns chunk_id + distance for the globally-nearest vectors;
    # we over-fetch (k * 4) because other repos' chunks will be filtered out
    # at the join, then re-limit to the requested k after repo filtering.
    fetch_k = max(k * 4, k + 16)
    rows = db.execute(
        """
        SELECT c.chunk_id, c.file_path, c.heading, c.content, c.token_count,
               v.distance
        FROM (
          SELECT chunk_id, distance
          FROM embeddings
          WHERE embedding MATCH ? AND k = ?
          ORDER BY distance ASC
        ) v
        JOIN chunks c ON c.chunk_id = v.chunk_id
        WHERE c.repo_id = ?
        ORDER BY v.distance ASC
        LIMIT ?
        """,
        (qblob, fetch_k, repo_id, k),
    ).fetchall()
    return [dict(r) for r in rows]
