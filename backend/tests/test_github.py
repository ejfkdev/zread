# -*- coding: utf-8 -*-
"""GitHub client tests: tree filtering, default-branch resolution, doc ranking."""

import httpx
import pytest
import respx

from app.config import settings
from app.github import (
    GitHubError,
    fetch_files_concurrent,
    fetch_raw,
    fetch_tree,
    filter_doc_files,
    get_default_branch,
    is_doc,
)


@respx.mock
async def test_get_default_branch():
    respx.get(f"{settings.github_api_url}/repos/o/r").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"})
    )
    async with httpx.AsyncClient() as c:
        branch = await get_default_branch(c, "o", "r")
    assert branch == "main"


@respx.mock
async def test_get_default_branch_404_raises():
    respx.get(f"{settings.github_api_url}/repos/o/missing").mock(
        return_value=httpx.Response(404)
    )
    async with httpx.AsyncClient() as c:
        with pytest.raises(GitHubError):
            await get_default_branch(c, "o", "missing")


@respx.mock
async def test_fetch_tree_returns_blobs():
    respx.get(f"{settings.github_api_url}/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(
            200,
            json={
                "truncated": False,
                "tree": [
                    {"type": "blob", "path": "README.md", "size": 100},
                    {"type": "blob", "path": "src/main.py", "size": 500},
                    {"type": "tree", "path": "src", "sha": "abc"},
                ],
            },
        )
    )
    async with httpx.AsyncClient() as c:
        files = await fetch_tree(c, "o", "r", "main")
    assert len(files) == 2
    paths = [f["path"] for f in files]
    assert "README.md" in paths
    assert "src/main.py" in paths


def test_is_doc_extensions():
    assert is_doc("README.md")
    assert is_doc("docs/guide.mdx")
    assert is_doc("notes.markdown")
    assert is_doc("api.rst")
    assert not is_doc("src/main.py")
    assert not is_doc("image.png")


def test_is_doc_globs():
    assert is_doc("README")  # matches README* glob
    assert is_doc("README.zh.md")


def test_filter_doc_files_caps_size():
    files = [
        {"path": "big.md", "size": settings.index_max_file_bytes + 1},
        {"path": "small.md", "size": 100},
        {"path": "code.py", "size": 10},
    ]
    kept = filter_doc_files(files)
    paths = [f["path"] for f in kept]
    assert "big.md" not in paths  # too large
    assert "small.md" in paths
    assert "code.py" not in paths  # not a doc


def test_filter_doc_files_readme_first():
    files = [
        {"path": "docs/guide.md", "size": 10},
        {"path": "README.md", "size": 10},
        {"path": "CONTRIBUTING.md", "size": 10},
    ]
    kept = filter_doc_files(files)
    # README sorts before docs/ and root non-readme files.
    assert kept[0]["path"] == "README.md"


@respx.mock
async def test_fetch_raw_anonymous():
    respx.get(f"{settings.github_raw_url}/o/r/main/file.md").mock(
        return_value=httpx.Response(200, text="# hi")
    )
    async with httpx.AsyncClient() as c:
        text = await fetch_raw(c, "o", "r", "main", "file.md")
    assert text == "# hi"


@respx.mock
async def test_fetch_raw_404_returns_none():
    respx.get(f"{settings.github_raw_url}/o/r/main/missing.md").mock(
        return_value=httpx.Response(404)
    )
    async with httpx.AsyncClient() as c:
        text = await fetch_raw(c, "o", "r", "main", "missing.md")
    assert text is None


@respx.mock
async def test_fetch_files_concurrent_partial_failure():
    base = f"{settings.github_raw_url}/o/r/main"
    respx.get(f"{base}/a.md").mock(return_value=httpx.Response(200, text="A"))
    respx.get(f"{base}/b.md").mock(return_value=httpx.Response(500))
    respx.get(f"{base}/c.md").mock(return_value=httpx.Response(200, text="C"))
    async with httpx.AsyncClient() as c:
        results = await fetch_files_concurrent(c, "o", "r", "main", ["a.md", "b.md", "c.md"])
    paths = [p for p, _ in results]
    assert "a.md" in paths
    assert "c.md" in paths
    assert "b.md" not in paths  # failed, skipped
