# -*- coding: utf-8 -*-
"""导出：llms.txt 链接修复、front matter、llms-only、源码附带。"""

import asyncio

import httpx
import respx

from zread.export import _export_repo_async

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

PAGES = [
    {
        "slug": "README.md",
        "title": "README.md",
        "topic": "README.md",
        "group": "",
        "section": "",
    },
    {
        "slug": "docs/guide.md",
        "title": "docs/guide.md",
        "topic": "guide.md",
        "group": "",
        "section": "docs",
    },
]


def _mock_repo_api():
    respx.get(f"{API}/repos/o/r").mock(
        return_value=httpx.Response(
            200,
            json={
                "html_url": "https://github.com/o/r",
                "owner": {"login": "o"},
                "name": "r",
                "description": "demo",
                "stargazers_count": 1,
                "default_branch": "main",
            },
        )
    )


def _mock_raw_pages():
    respx.get(f"{RAW}/o/r/HEAD/README.md").mock(
        return_value=httpx.Response(200, text="# Readme body")
    )
    respx.get(f"{RAW}/o/r/HEAD/docs/guide.md").mock(
        return_value=httpx.Response(200, text="# Guide body")
    )


@respx.mock
def test_export_writes_pages_and_correct_llms_links(tmp_path):
    _mock_repo_api()
    _mock_raw_pages()

    result = asyncio.run(
        _export_repo_async("o/r", tmp_path, "en", 2, pages=list(PAGES))
    )
    assert result["success"]
    repo_dir = result["repo_dir"]

    # 单页文件按仓库路径落地
    assert (repo_dir / "README.md").read_text(encoding="utf-8") == "# Readme body"
    assert (repo_dir / "docs" / "guide.md").exists()

    llms = (repo_dir / "llms.txt").read_text(encoding="utf-8")
    # 之前的 bug：链接写成 ./README.md.md（slug 已含扩展名）
    assert "(./README.md)" in llms
    assert "(./docs/guide.md)" in llms
    assert ".md.md" not in llms

    llms_full = (repo_dir / "llms-full.txt").read_text(encoding="utf-8")
    assert "# Readme body" in llms_full
    assert "# Guide body" in llms_full


@respx.mock
def test_export_front_matter(tmp_path):
    _mock_repo_api()
    _mock_raw_pages()

    result = asyncio.run(
        _export_repo_async(
            "o/r", tmp_path, "en", 2, pages=list(PAGES), front_matter=True
        )
    )
    saved = (result["repo_dir"] / "README.md").read_text(encoding="utf-8")
    assert saved.startswith("---\n")
    assert "path: README.md" in saved
    assert "repository: o/r" in saved
    assert saved.endswith("# Readme body")


@respx.mock
def test_export_llms_only(tmp_path):
    _mock_repo_api()
    _mock_raw_pages()

    result = asyncio.run(
        _export_repo_async(
            "o/r", tmp_path, "en", 2, pages=list(PAGES), llms_only=True
        )
    )
    repo_dir = result["repo_dir"]
    # 不落地单页文件，llms.txt 用远程链接，llms-full.txt 仍是完整内容
    assert not (repo_dir / "README.md").exists()
    llms = (repo_dir / "llms.txt").read_text(encoding="utf-8")
    assert "https://github.com/o/r/blob/HEAD/README.md" in llms
    assert "(./" not in llms
    assert "# Readme body" in (repo_dir / "llms-full.txt").read_text(encoding="utf-8")


@respx.mock
def test_export_include_source_skips_binaries_and_docs(tmp_path):
    _mock_repo_api()
    _mock_raw_pages()
    respx.get(f"{API}/repos/o/r/git/trees/main").mock(
        return_value=httpx.Response(
            200,
            json={
                "tree": [
                    {"path": "README.md", "type": "blob", "size": 10},
                    {"path": "src/app.py", "type": "blob", "size": 100},
                    {"path": "logo.png", "type": "blob", "size": 100},
                    {"path": "big.py", "type": "blob", "size": 10_000_000},
                ],
                "truncated": False,
            },
        )
    )
    respx.get(f"{RAW}/o/r/HEAD/src/app.py").mock(
        return_value=httpx.Response(200, text="print('hi')")
    )

    result = asyncio.run(
        _export_repo_async(
            "o/r", tmp_path, "en", 2, pages=list(PAGES), include_source=True
        )
    )
    repo_dir = result["repo_dir"]
    assert (repo_dir / "src" / "app.py").exists()
    assert result["source_files"] == 1
    assert not (repo_dir / "logo.png").exists()
    assert not (repo_dir / "big.py").exists()


@respx.mock
def test_export_rejects_path_traversal_slugs(tmp_path):
    _mock_repo_api()
    _mock_raw_pages()
    evil_pages = [
        {
            "slug": "README.md",
            "title": "README.md",
            "topic": "README.md",
            "group": "",
            "section": "",
        },
        {
            "slug": "../../ESCAPED.md",
            "title": "evil",
            "topic": "evil",
            "group": "",
            "section": "",
        },
    ]
    respx.get(f"{RAW}/o/r/HEAD/../../ESCAPED.md").mock(
        return_value=httpx.Response(200, text="pwn")
    )

    out_dir = tmp_path / "nested" / "out"
    out_dir.mkdir(parents=True)
    result = asyncio.run(
        _export_repo_async("o/r", out_dir, "en", 2, pages=evil_pages)
    )
    # 恶意 slug 记为失败，不写出 output 目录之外
    assert result["failed"] == 1
    assert not (tmp_path / "ESCAPED.md").exists()
    assert not (tmp_path / "nested" / "ESCAPED.md").exists()
    assert (result["repo_dir"] / "README.md").exists()
