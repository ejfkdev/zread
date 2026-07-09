# -*- coding: utf-8 -*-
"""parse_repo_url：各种输入格式、ref、行号、异常。"""

import pytest

from zread.github import parse_repo_url


def test_basic_owner_repo():
    parsed = parse_repo_url("facebook/react")
    assert parsed["owner"] == "facebook"
    assert parsed["repo"] == "react"
    assert parsed["repo_path"] == "facebook/react"
    assert parsed["file_path"] is None
    assert parsed["ref"] is None


def test_trailing_slash_is_not_a_file_path():
    parsed = parse_repo_url("vuejs/vue/")
    assert parsed["repo_path"] == "vuejs/vue"
    assert parsed["file_path"] is None


def test_git_suffix_stripped():
    parsed = parse_repo_url("https://github.com/vuejs/vue.git")
    assert parsed["repo"] == "vue"


def test_at_ref_syntax():
    parsed = parse_repo_url("golang/go@go1.22.0")
    assert parsed["repo"] == "go"
    assert parsed["ref"] == "go1.22.0"


def test_at_ref_with_file_path():
    parsed = parse_repo_url("golang/go@go1.22.0/src/net/http/server.go")
    assert parsed["ref"] == "go1.22.0"
    assert parsed["file_path"] == "src/net/http/server.go"


def test_blob_url_keeps_ref_and_lines():
    parsed = parse_repo_url(
        "https://github.com/facebook/react/blob/v18.2.0/README.md#L10-L20"
    )
    assert parsed["owner"] == "facebook"
    assert parsed["repo"] == "react"
    assert parsed["ref"] == "v18.2.0"
    assert parsed["file_path"] == "README.md"
    assert parsed["start_line"] == 10
    assert parsed["end_line"] == 20
    assert parsed["source"] == "github"


def test_tree_url_keeps_ref():
    parsed = parse_repo_url("github.com/golang/go/tree/master/src/net")
    assert parsed["ref"] == "master"
    assert parsed["file_path"] == "src/net"


def test_raw_url_keeps_ref():
    parsed = parse_repo_url(
        "https://raw.githubusercontent.com/golang/go/go1.22.0/README.md"
    )
    assert parsed["owner"] == "golang"
    assert parsed["ref"] == "go1.22.0"
    assert parsed["file_path"] == "README.md"
    assert parsed["source"] == "raw_github"


def test_plain_repo_with_path():
    parsed = parse_repo_url("python/cpython/Lib/http/client.py")
    assert parsed["file_path"] == "Lib/http/client.py"


def test_single_segment_raises():
    with pytest.raises(ValueError):
        parse_repo_url("not-a-repo")
