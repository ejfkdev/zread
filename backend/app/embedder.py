# -*- coding: utf-8 -*-
"""Embeddings via an OpenAI-compatible endpoint.

Batches texts up to embed_batch_size; any provider implementing
POST {base}/embeddings with the OpenAI shape works.
"""

import asyncio
import logging
from typing import List

import httpx

from app.config import settings

_log = logging.getLogger("zread_ai.embedder")

_EMBED_TIMEOUT = 60.0
_MAX_RETRIES = 4
# Status codes treated as transient (retryable). 502/503/429 are all gateway
# overload or rate-limit signals — safe to back off and retry.
_RETRYABLE = {429, 502, 503}


async def embed_texts(client: httpx.AsyncClient, texts: List[str]) -> List[List[float]]:
    """Embed a list of texts, batching to respect provider limits.

    Returns one vector per input text, in order. Batches are embedded
    concurrently up to ``settings.embed_concurrency`` at a time, with an
    optional ``settings.embed_pace_s`` delay between dispatches. Retries on
    429/502/503 with exponential backoff (transient upstream provider
    exhaustion). Raises on persistent provider error.
    """
    if not texts:
        return []
    bs = settings.embed_batch_size
    headers = {"Authorization": f"Bearer {settings.resolved_embed_api_key}"}
    url = f"{settings.resolved_embed_base_url}/embeddings"

    # Slice into batches; embed concurrently (bounded) while preserving order.
    batches = [texts[i : i + bs] for i in range(0, len(texts), bs)]
    semaphore = asyncio.Semaphore(max(1, settings.embed_concurrency))
    pace = max(0.0, settings.embed_pace_s)

    async def _embed_indexed(idx: int, batch: List[str]) -> List[List[float]]:
        async with semaphore:
            if pace and idx > 0:
                # Stagger dispatches so concurrent batches don't all hit the
                # gateway in the same instant.
                await asyncio.sleep(pace * (idx % max(1, settings.embed_concurrency)))
            return await _embed_batch_with_retry(client, url, headers, batch)

    results = await asyncio.gather(
        *(_embed_indexed(i, b) for i, b in enumerate(batches))
    )
    out: List[List[float]] = []
    for vecs in results:
        out.extend(vecs)
    return out


async def _embed_batch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    batch: List[str],
) -> List[List[float]]:
    """Embed one batch, retrying transient failures with backoff."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = await client.post(
                url,
                headers=headers,
                json={"model": settings.embed_model, "input": batch},
                timeout=_EMBED_TIMEOUT,
            )
            if resp.status_code in _RETRYABLE:
                delay = _backoff(resp, attempt)
                _log.warning(
                    "embeddings got %d (batch of %d), retrying in %.1fs",
                    resp.status_code, len(batch), delay,
                )
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp
                )
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
            items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
            return [item["embedding"] for item in items]
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code in _RETRYABLE:
                await asyncio.sleep(_backoff(exc.response, attempt))
                continue
            raise
    raise last_exc or RuntimeError("embeddings failed after retries")


def _backoff(resp: httpx.Response, attempt: int) -> float:
    """Backoff honoring Retry-After, capped at 30s."""
    ra = resp.headers.get("retry-after", "")
    if ra:
        try:
            return min(float(ra), 30.0)
        except ValueError:
            pass
    return min(2.0 * (2 ** attempt), 30.0)


async def embed_query(client: httpx.AsyncClient, query: str) -> List[float]:
    """Embed a single query string."""
    vecs = await embed_texts(client, [query])
    return vecs[0]
