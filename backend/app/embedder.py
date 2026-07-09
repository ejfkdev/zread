# -*- coding: utf-8 -*-
"""Embeddings via an OpenAI-compatible endpoint.

Batches texts up to embed_batch_size; any provider implementing
POST {base}/embeddings with the OpenAI shape works.
"""

import logging
from typing import List

import httpx

from app.config import settings

_log = logging.getLogger("zread_ai.embedder")

_EMBED_TIMEOUT = 60.0


async def embed_texts(client: httpx.AsyncClient, texts: List[str]) -> List[List[float]]:
    """Embed a list of texts, batching to respect provider limits.

    Returns one vector per input text, in order. Raises on provider error.
    """
    if not texts:
        return []
    out: List[List[float]] = []
    bs = settings.embed_batch_size
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    url = f"{settings.llm_base_url.rstrip('/')}/embeddings"
    for i in range(0, len(texts), bs):
        batch = texts[i : i + bs]
        resp = await client.post(
            url,
            headers=headers,
            json={"model": settings.embed_model, "input": batch},
            timeout=_EMBED_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        # OpenAI returns {"data": [{"embedding": [...]}, ...]} ordered by index.
        items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
        for item in items:
            out.append(item["embedding"])
    return out


async def embed_query(client: httpx.AsyncClient, query: str) -> List[float]:
    """Embed a single query string."""
    vecs = await embed_texts(client, [query])
    return vecs[0]
