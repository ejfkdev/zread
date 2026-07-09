# -*- coding: utf-8 -*-
"""文档大纲 / 文档搜索：排序、ref 透传、truncated 警告、README 回退。"""

import httpx
import respx

from zread.github import fetch_markdown, fetch_repo_outline

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


@respx.mock
def test_outline_sorted_readme_first():
    respx.get(f"{API}/repos/o/r").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"})
    )
    respx.get(f"{API}/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(
            200,
            json={
                "tree": [
                    {"path": "docs/a.md", "type": "blob", "size": 1},
                    {"path": "zz.md", "type": "blob", "size": 1},
                    {"path": "README.md", "type": "blob", "size": 1},
                    {"path": "src/x.py", "type": "blob", "size": 1},
                ],
                "truncated": False,
            },
        )
    )
    outline = fetch_repo_outline("o/r")
    slugs = [p["slug"] for p in outline]
    assert slugs == ["README.md", "zz.md", "docs/a.md"]
    docs_page = outline[2]
    assert docs_page["section"] == "docs"
    assert docs_page["topic"] == "a.md"


@respx.mock
def test_outline_with_explicit_ref_skips_repo_lookup():
    tree_route = respx.get(f"{API}/repos/o/r/git/trees/v9").mock(
        return_value=httpx.Response(
            200,
            json={
                "tree": [{"path": "README.md", "type": "blob", "size": 1}],
                "truncated": False,
            },
        )
    )
    outline = fetch_repo_outline("o/r", ref="v9")
    assert [p["slug"] for p in outline] == ["README.md"]
    assert tree_route.call_count == 1


@respx.mock
def test_truncated_tree_warns_on_stderr(capsys):
    respx.get(f"{API}/repos/big/repo/git/trees/v1").mock(
        return_value=httpx.Response(
            200,
            json={
                "tree": [{"path": "README.md", "type": "blob", "size": 1}],
                "truncated": True,
            },
        )
    )
    outline = fetch_repo_outline("big/repo", ref="v1")
    assert outline  # 仍返回可用结果
    captured = capsys.readouterr()
    assert "big/repo" in captured.err
    assert captured.out == ""  # 绝不写 stdout（MCP stdio 通道）


@respx.mock
def test_fetch_markdown_readme_fallback_candidates():
    respx.get(f"{RAW}/o/r/HEAD/README.md").mock(return_value=httpx.Response(404))
    respx.get(f"{RAW}/o/r/HEAD/README.rst").mock(
        return_value=httpx.Response(200, text="reST readme")
    )
    assert fetch_markdown("o/r", "1-overview") == "reST readme"


@respx.mock
def test_fetch_markdown_uses_ref_from_repo_string():
    respx.get(f"{RAW}/o/r/v3/docs/x.md").mock(
        return_value=httpx.Response(200, text="pinned")
    )
    assert fetch_markdown("o/r@v3", "docs/x.md") == "pinned"


@respx.mock
def test_github_error_paths_never_write_stdout(capsys):
    respx.get(f"{API}/repos/o/r").mock(
        return_value=httpx.Response(
            403,
            headers={
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": "1780000000",
            },
        )
    )
    outline = fetch_repo_outline("o/r")
    assert outline is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "GITHUB_TOKEN" in captured.err or "rate limit" in captured.err.lower()
