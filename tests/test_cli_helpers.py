# -*- coding: utf-8 -*-
"""CLI 辅助解析与 MCP 地址 / transport 校验。"""

import pytest

from zread.cli import _parse_cat_args, _parse_line_range
from zread.mcp_server import _parse_address, _run_mcp_server


def test_parse_line_range_formats():
    assert _parse_line_range("5") == (5, None)
    assert _parse_line_range("5:20") == (5, 20)
    assert _parse_line_range("5-20") == (5, 20)
    assert _parse_line_range("5~20") == (5, 20)
    assert _parse_line_range("5:") == (5, None)
    assert _parse_line_range(":10") == (1, 10)
    assert _parse_line_range("-10") == (1, 10)
    assert _parse_line_range("#L5-L10") == (5, 10)
    assert _parse_line_range("L7") == (7, None)
    assert _parse_line_range("README.md") == (None, None)


def test_cat_args_default_doc_page():
    assert _parse_cat_args(["vuejs/vue"]) == (
        "vuejs/vue",
        "1-overview",
        None,
        None,
        True,
        None,
    )


def test_cat_args_trailing_slash_still_doc_page():
    # 之前的 bug：owner/repo/ 会被当成空文件路径并报错
    owner_repo, slug, _, _, is_doc, _ = _parse_cat_args(["vuejs/vue/"])
    assert (owner_repo, slug, is_doc) == ("vuejs/vue", "1-overview", True)


def test_cat_args_numeric_doc_index():
    assert _parse_cat_args(["o/r", "3"])[:2] == ("o/r", "3")
    assert _parse_cat_args(["o/r", "3"])[4] is True


def test_cat_args_file_with_range():
    assert _parse_cat_args(["o/r", "README.md", "5:20"]) == (
        "o/r",
        "README.md",
        5,
        20,
        False,
        None,
    )


def test_cat_args_at_ref():
    result = _parse_cat_args(["golang/go@go1.22.0", "README.md"])
    assert result[0] == "golang/go"
    assert result[1] == "README.md"
    assert result[5] == "go1.22.0"


def test_cat_args_blob_url_keeps_ref_and_lines():
    result = _parse_cat_args(
        ["https://github.com/o/r/blob/v2/src/main.py#L3-L9"]
    )
    assert result == ("o/r", "src/main.py", 3, 9, False, "v2")


def test_parse_address_defaults_and_formats():
    assert _parse_address("stdio", None) == ("127.0.0.1", 8708, "/mcp")
    assert _parse_address("http", None) == ("127.0.0.1", 8708, "/mcp")
    assert _parse_address("sse", None) == ("127.0.0.1", 8708, "/sse")
    assert _parse_address("http", ":8080") == ("127.0.0.1", 8080, "/mcp")
    assert _parse_address("http", "0.0.0.0:3000/custom") == (
        "0.0.0.0",
        3000,
        "/custom",
    )
    assert _parse_address("sse", "localhost:8080/events") == (
        "localhost",
        8080,
        "/events",
    )


def test_parse_address_invalid_port():
    with pytest.raises(ValueError):
        _parse_address("http", ":abc")
    with pytest.raises(ValueError):
        _parse_address("http", "host:99999")


def test_run_mcp_server_rejects_unknown_transport():
    # 之前的 bug：未知 transport 打印"已启动"后静默退出
    with pytest.raises(ValueError):
        _run_mcp_server("htto")
