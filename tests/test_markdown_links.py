# -*- coding: utf-8 -*-
"""Markdown 链接改写：仓库内相对链接改写为 blob 链接，外部链接保持原样。"""

from zread.render import _process_markdown_links

REPO = "o/r"


def test_relative_file_link_rewritten_to_blob():
    result = _process_markdown_links("[guide](docs/guide.md)", REPO)
    assert result == "[🐙guide](https://github.com/o/r/blob/HEAD/docs/guide.md)"


def test_dot_slash_prefix_stripped():
    # 之前的 bug：链接包含 /./ 段
    result = _process_markdown_links("[guide](./docs/guide.md)", REPO)
    assert result == "[🐙guide](https://github.com/o/r/blob/HEAD/docs/guide.md)"


def test_mailto_link_untouched():
    # 之前的 bug：mailto: 被改写为 blob/HEAD/mailto:... 的坏链接
    text = "[email us](mailto:foo@bar.com)"
    assert _process_markdown_links(text, REPO) == text


def test_external_absolute_url_untouched():
    # 之前的 bug：example.com 被加上 🐙 代码文件标记
    for text in (
        "[site](https://example.com)",
        "[ext doc](https://readthedocs.io/en/index.html)",
        "[dl](ftp://mirror.example.com/file.tar.gz)",
    ):
        assert _process_markdown_links(text, REPO) == text


def test_anchor_only_link_untouched():
    text = "[usage](#usage)"
    assert _process_markdown_links(text, REPO) == text


def test_image_untouched():
    text = "![logo](docs/logo.png)"
    assert _process_markdown_links(text, REPO) == text


def test_slug_link_rewritten_with_number_prefix():
    result = _process_markdown_links("[overview](1-overview)", REPO)
    assert result == "[🔗1.overview](https://github.com/o/r/blob/HEAD/1-overview)"


def test_link_with_anchor_keeps_anchor():
    result = _process_markdown_links("[cfg](docs/config.md#usage)", REPO)
    assert result == "[🐙cfg](https://github.com/o/r/blob/HEAD/docs/config.md#usage)"


def test_repo_string_with_ref_still_builds_clean_repo_path():
    result = _process_markdown_links("[guide](docs/guide.md)", "o/r@v1.0")
    assert "blob/HEAD/docs/guide.md" in result
    assert "@" not in result.split("](")[1]
