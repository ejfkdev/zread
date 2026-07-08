# -*- coding: utf-8 -*-
"""MCP 工具：空结果 vs 失败、not-found、截断、weeks 透传、新工具。"""

import httpx
import respx

from zread.tools import (
    get_rate_limit,
    get_releases,
    get_repo_info,
    get_trending,
    list_repo_files,
    read_doc,
    read_source_file,
    search_code,
    search_repos,
    search_wiki,
)

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


@respx.mock
def test_search_repos_empty_is_not_an_error():
    respx.get(f"{API}/search/repositories").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    result = search_repos("definitely-nothing-matches-this")
    assert result == {"repos": []}
    assert "error" not in result


@respx.mock
def test_search_repos_failure_is_an_error():
    respx.get(f"{API}/search/repositories").mock(
        return_value=httpx.Response(500)
    )
    result = search_repos("boom")
    assert "error" in result


@respx.mock
def test_get_repo_info_not_found_returns_error():
    respx.get(f"{API}/repos/nosuch/repo").mock(return_value=httpx.Response(404))
    result = get_repo_info("nosuch/repo")
    assert "error" in result
    # 之前的 bug：返回 {"url": "https://github.com/None/None", ...}
    assert "None/None" not in str(result)


@respx.mock
def test_get_repo_info_success_shape():
    respx.get(f"{API}/repos/golang/go").mock(
        return_value=httpx.Response(
            200,
            json={
                "html_url": "https://github.com/golang/go",
                "owner": {"login": "golang"},
                "name": "go",
                "description": "The Go programming language",
                "language": "Go",
                "topics": ["go"],
                "stargazers_count": 120000,
                "default_branch": "master",
                "pushed_at": "2026-07-01T00:00:00Z",
                "license": {"name": "BSD 3-Clause"},
            },
        )
    )
    result = get_repo_info("golang/go")
    assert result["url"] == "https://github.com/golang/go"
    assert result["default_branch"] == "master"
    assert result["license"] == "BSD 3-Clause"
    assert "error" not in result


@respx.mock
def test_read_doc_empty_file_is_not_an_error():
    respx.get(f"{RAW}/o/r/HEAD/EMPTY.md").mock(
        return_value=httpx.Response(200, text="")
    )
    assert read_doc("o/r", "EMPTY.md") == ""


@respx.mock
def test_read_doc_missing_file_returns_error_text():
    respx.get(f"{RAW}/o/r/HEAD/NOPE.md").mock(return_value=httpx.Response(404))
    result = read_doc("o/r", "NOPE.md")
    assert "NOPE.md" in result


@respx.mock
def test_read_doc_ref_and_truncation():
    respx.get(f"{RAW}/o/r/v1.0/README.md").mock(
        return_value=httpx.Response(200, text="a" * 100)
    )
    result = read_doc("o/r", "README.md", ref="v1.0", max_bytes=10)
    assert result.startswith("a" * 10)
    assert "10" in result and "100" in result  # 截断提示


@respx.mock
def test_get_trending_passes_weeks_through():
    route = respx.get(f"{API}/search/repositories").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    result = get_trending(2)
    assert "groups" in result
    assert len(result["groups"]) == 2
    # 之前的 bug：无论请求几周都固定发 4 个请求
    assert route.call_count == 2


@respx.mock
def test_search_wiki_no_matches_is_not_an_error():
    respx.get(f"{API}/repos/o/r").mock(
        return_value=httpx.Response(200, json={"default_branch": "main"})
    )
    respx.get(f"{API}/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(
            200,
            json={
                "tree": [{"path": "README.md", "type": "blob", "size": 10}],
                "truncated": False,
            },
        )
    )
    respx.get(f"{RAW}/o/r/HEAD/README.md").mock(
        return_value=httpx.Response(200, text="hello world")
    )
    result = search_wiki("o/r", "zzz-not-there")
    assert result == {"results": []}


@respx.mock
def test_read_source_file_line_range():
    respx.get(f"{RAW}/o/r/HEAD/main.py").mock(
        return_value=httpx.Response(200, text="l1\nl2\nl3\nl4\n")
    )
    assert read_source_file("o/r", "main.py", start_line=2, end_line=3) == "l2\nl3"


@respx.mock
def test_list_repo_files_filters_and_limits():
    respx.get(f"{API}/repos/o/r/git/trees/v2").mock(
        return_value=httpx.Response(
            200,
            json={
                "tree": [
                    {"path": "src/a.py", "type": "blob", "size": 10},
                    {"path": "src/b.py", "type": "blob", "size": 20},
                    {"path": "docs/x.md", "type": "blob", "size": 30},
                    {"path": "src", "type": "tree"},
                ],
                "truncated": False,
            },
        )
    )
    result = list_repo_files("o/r", path="src", ref="v2", limit=1)
    assert result["total"] == 2
    assert len(result["files"]) == 1
    assert result["files"][0]["path"] == "src/a.py"
    assert result["truncated"] is False


def test_search_code_requires_token():
    result = search_code("o/r", "anything")
    assert "error" in result
    assert "GITHUB_TOKEN" in result["error"]


@respx.mock
def test_search_code_with_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    route = respx.get(f"{API}/search/code").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "path": "src/server.go",
                        "name": "server.go",
                        "html_url": "https://github.com/o/r/blob/HEAD/src/server.go",
                        "text_matches": [{"fragment": "func ListenAndServe()"}],
                    }
                ]
            },
        )
    )
    result = search_code("o/r", "ListenAndServe")
    assert result["results"][0]["path"] == "src/server.go"
    assert result["results"][0]["fragments"] == ["func ListenAndServe()"]
    sent = route.calls[0].request
    assert "repo%3Ao%2Fr" in str(sent.url) or "repo:o/r" in str(sent.url)
    assert sent.headers["authorization"] == "Bearer ghp_test"


@respx.mock
def test_get_releases():
    respx.get(f"{API}/repos/o/r/releases").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "tag_name": "v1.2.3",
                    "name": "Release 1.2.3",
                    "published_at": "2026-06-01T12:00:00Z",
                    "prerelease": False,
                    "html_url": "https://github.com/o/r/releases/tag/v1.2.3",
                    "body": "notes",
                }
            ],
        )
    )
    result = get_releases("o/r")
    assert result["releases"][0]["tag"] == "v1.2.3"
    assert result["releases"][0]["body"] == "notes"


@respx.mock
def test_get_releases_empty_is_not_an_error():
    respx.get(f"{API}/repos/o/r/releases").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert get_releases("o/r") == {"releases": []}


@respx.mock
def test_get_rate_limit():
    respx.get(f"{API}/rate_limit").mock(
        return_value=httpx.Response(
            200,
            json={
                "resources": {
                    "core": {"limit": 60, "remaining": 42, "reset": 1780000000},
                    "search": {"limit": 10, "remaining": 10, "reset": 1780000000},
                }
            },
        )
    )
    result = get_rate_limit()
    assert result["authenticated"] is False
    assert result["resources"]["core"]["remaining"] == 42
    assert result["resources"]["core"]["reset"]
