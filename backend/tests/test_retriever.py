# -*- coding: utf-8 -*-
"""Retriever tests: deterministic vectors, top-k ordering, repo isolation."""

from app.chunker import Chunk
from app.indexer import _replace_chunks
from app.retriever import retrieve


def _vec(dim: int, *vals: float) -> list:
    """Build a unit-length-ish vector with given leading components, rest 0."""
    v = [0.0] * dim
    for i, x in enumerate(vals):
        v[i] = x
    return v


def test_retrieve_returns_top_k_ordered(db):
    dim = 8
    chunks = [
        Chunk("a.md", "Intro", 0, "alpha content", 5),
        Chunk("b.md", "Setup", 1, "beta content", 5),
        Chunk("c.md", "Usage", 2, "gamma content", 5),
    ]
    # Clearly distinct vectors: a is closest to query, then b, then c.
    vectors = [
        _vec(dim, 1.0, 0.0),   # a: exact match to query
        _vec(dim, 0.7, 0.7),   # b: moderate
        _vec(dim, 0.0, 1.0),   # c: far from query
    ]
    _replace_chunks(db, "owner/repo@main", chunks, vectors)

    q = _vec(dim, 1.0, 0.0)
    results = retrieve("owner/repo@main", q, top_k=2)
    assert len(results) == 2
    # Closest first.
    assert results[0]["file_path"] == "a.md"
    assert results[1]["file_path"] == "b.md"
    # Distances ascending.
    dists = [r["distance"] for r in results]
    assert dists[0] <= dists[1]


def test_retrieve_repo_isolation(db):
    dim = 8
    chunks = [Chunk("a.md", "H", 0, "shared content", 5)]
    vectors = [_vec(dim, 1.0, 0.0)]
    _replace_chunks(db, "alpha/repo@main", chunks, vectors)
    _replace_chunks(db, "beta/repo@main", chunks, vectors)

    # Query alpha — must NOT return beta's chunk (different chunk_id).
    results = retrieve("alpha/repo@main", _vec(dim, 1.0, 0.0), top_k=5)
    assert len(results) == 1
    alpha_id = results[0]["chunk_id"]
    results_beta = retrieve("beta/repo@main", _vec(dim, 1.0, 0.0), top_k=5)
    assert len(results_beta) == 1
    assert results_beta[0]["chunk_id"] != alpha_id


def test_retrieve_empty_repo(db):
    results = retrieve("nobody/empty@main", _vec(8, 1.0), top_k=5)
    assert results == []


def test_re_index_replaces_old_chunks(db):
    """Re-indexing the same repo_id wipes old chunks/embeddings (idempotency)."""
    dim = 8
    chunks1 = [Chunk("old.md", "Old", 0, "old content", 5)]
    _replace_chunks(db, "owner/repo@main", chunks1, [_vec(dim, 1.0, 0.0)])
    assert len(retrieve("owner/repo@main", _vec(dim, 1.0, 0.0), top_k=10)) == 1

    chunks2 = [Chunk("new.md", "New", 0, "new content", 5)]
    _replace_chunks(db, "owner/repo@main", chunks2, [_vec(dim, 1.0, 0.0)])
    results = retrieve("owner/repo@main", _vec(dim, 1.0, 0.0), top_k=10)
    assert len(results) == 1
    assert results[0]["file_path"] == "new.md"
