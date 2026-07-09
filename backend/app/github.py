# -*- coding: utf-8 -*-
"""GitHub client for the backend.

Self-contained: resolves the default branch, fetches the recursive tree,
filters to docs, and downloads raw file content concurrently. Uses the
backend's own GITHUB_TOKEN (independent of the fork client's token).
"""

import asyncio
import fnmatch
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings

_log = logging.getLogger("zread_ai.github")

_TREE_TIMEOUT = 30.0
_RAW_TIMEOUT = 30.0


class GitHubError(Exception):
    pass


async def get_default_branch(
    client: httpx.AsyncClient, owner: str, repo: str
) -> str:
    """Resolve the default branch via GET /repos/{o}/{r}."""
    url = f"{settings.github_api_url}/repos/{owner}/{repo}"
    resp = await client.get(url, headers=settings.github_headers, timeout=_TREE_TIMEOUT)
    if resp.status_code == 404:
        raise GitHubError(f"Repository {owner}/{repo} not found")
    resp.raise_for_status()
    data = resp.json()
    branch = data.get("default_branch") or "HEAD"
    return branch


async def fetch_tree(
    client: httpx.AsyncClient, owner: str, repo: str, ref: str
) -> List[Dict[str, Any]]:
    """Fetch the recursive tree; return list of {path, size} blobs."""
    import urllib.parse

    quoted = urllib.parse.quote(ref, safe="")
    url = f"{settings.github_api_url}/repos/{owner}/{repo}/git/trees/{quoted}"
    resp = await client.get(
        url,
        headers=settings.github_headers,
        params={"recursive": "1"},
        timeout=_TREE_TIMEOUT,
    )
    if resp.status_code == 404:
        raise GitHubError(f"Ref '{ref}' not found in {owner}/{repo}")
    resp.raise_for_status()
    data = resp.json()
    if data.get("truncated"):
        _log.warning("Tree for %s/%s@%s is truncated; some files may be missing", owner, repo, ref)
    return [
        {"path": item.get("path", ""), "size": item.get("size", 0)}
        for item in data.get("tree", [])
        if item.get("type") == "blob"
    ]


def is_doc(path: str) -> bool:
    """Match the configured doc allowlist (extensions + filename globs)."""
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    for ext in settings.doc_extensions:
        if lower.endswith(ext):
            return True
    for pat in settings.doc_globs:
        if fnmatch.fnmatch(name, pat.lower()):
            return True
    return False


def filter_doc_files(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep docs only, drop oversized files, cap by index_max_files."""
    kept = []
    for f in files:
        p = f.get("path", "")
        if not p or not is_doc(p):
            continue
        if f.get("size", 0) > settings.index_max_file_bytes:
            continue
        kept.append(f)
    # Stable, importance-aware ordering: README/root first, then docs/.
    kept.sort(key=_doc_rank)
    return kept[: settings.index_max_files]


def _doc_rank(f: Dict[str, Any]) -> Tuple[int, str]:
    path = f.get("path", "")
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    if "/" not in path and name.startswith("readme"):
        rank = 0
    elif "/" not in path:
        rank = 1
    elif lower.startswith(("docs/", "doc/", "documentation/")):
        rank = 2
    else:
        rank = 3
    return (rank, lower)


async def fetch_raw(
    client: httpx.AsyncClient, owner: str, repo: str, ref: str, path: str
) -> Optional[str]:
    """Download a single file's raw text.

    Public repos work anonymously; a 404 triggers a token-authenticated retry
    (private repos). Retries on 429/503 with exponential backoff (respects
    Retry-After) so a large monorepo doesn't die on GitHub's rate limit.
    """
    url = f"{settings.github_raw_url}/{owner}/{repo}/{ref}/{path}"
    base_headers = {"User-Agent": "zread-ai-backend"}

    for attempt in range(4):
        resp = await client.get(url, headers=base_headers, timeout=_RAW_TIMEOUT)
        if resp.status_code == 404 and settings.github_token:
            resp = await client.get(
                url,
                headers={**base_headers, "Authorization": f"Bearer {settings.github_token}"},
                timeout=_RAW_TIMEOUT,
            )
        if resp.status_code == 404:
            return None
        if resp.status_code in (429, 503):
            delay = _retry_after(resp, attempt)
            _log.warning("fetch_raw %s got %d, retrying in %.1fs", path, resp.status_code, delay)
            await asyncio.sleep(delay)
            continue
        resp.raise_for_status()
        return resp.text
    # Exhausted retries — raise so the caller logs it, but don't crash the batch.
    resp.raise_for_status()
    return None


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    """Compute a backoff delay; honors Retry-After, capped at 30s."""
    ra = resp.headers.get("retry-after", "")
    if ra:
        try:
            return min(float(ra), 30.0)
        except ValueError:
            pass
    return min(2.0 * (2 ** attempt), 30.0)


async def fetch_files_concurrent(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    ref: str,
    paths: List[str],
    concurrency: Optional[int] = None,
) -> List[Tuple[str, str]]:
    """Download many files concurrently; return [(path, text)] for successes."""
    sem = asyncio.Semaphore(concurrency or settings.index_concurrency)
    results: List[Tuple[str, str]] = []

    async def _one(p: str) -> None:
        async with sem:
            try:
                text = await fetch_raw(client, owner, repo, ref, p)
                if text is not None:
                    results.append((p, text))
            except Exception as exc:
                _log.warning("Failed to fetch %s: %s", p, exc)

    await asyncio.gather(*[_one(p) for p in paths])
    return results
