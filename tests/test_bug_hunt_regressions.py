# -*- coding: utf-8 -*-
"""bug-hunt 回归：负缓存、ref 链接、--code 守卫、TOML 转义、磁盘缓存上限。"""

import httpx
import respx
from typer.testing import CliRunner

from zread.cache import HTTPDiskCache
from zread.cli import cli_app
from zread.github import _gh_repo_get

API = "https://api.github.com"

runner = CliRunner()


@respx.mock
def test_transient_failure_is_not_negative_cached():
    route = respx.get(f"{API}/repos/o/r")
    route.side_effect = [
        httpx.Response(500),
        httpx.Response(200, json={"name": "r", "stargazers_count": 1}),
    ]
    # 第一次失败（500 不可重试，直接失败）
    assert _gh_repo_get("o", "r") is None
    # 之前的 bug：None 被 TTL 缓存 15 分钟，之后的调用也拿到 None
    assert _gh_repo_get("o", "r") == {"name": "r", "stargazers_count": 1}


@respx.mock
def test_ls_plain_links_use_requested_ref():
    respx.get(f"{API}/repos/o/r/git/trees/v7").mock(
        return_value=httpx.Response(
            200,
            json={
                "tree": [{"path": "docs/a.md", "type": "blob", "size": 1}],
                "truncated": False,
            },
        )
    )
    result = runner.invoke(cli_app, ["ls", "o/r", "--ref", "v7", "--plain"])
    assert result.exit_code == 0, result.output
    # 之前的 bug：链接指向 blob/HEAD 而不是请求的 ref
    assert "blob/v7/docs/a.md" in result.output
    assert "blob/HEAD" not in result.output


def test_find_code_without_repo_is_an_error():
    # 之前的 bug：--code 被静默忽略，退化成仓库搜索
    result = runner.invoke(cli_app, ["find", "somequery", "--code"])
    assert result.exit_code == 1


def test_config_value_with_newline_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    evil = "line1\nline2\t\"quoted\""
    result = runner.invoke(cli_app, ["config", "set", "github_token", evil])
    assert result.exit_code == 0, result.output

    from zread.config import config_from_file

    # 之前的 bug：未转义的换行会写出损坏的 TOML，之后所有读取都失败
    assert config_from_file().get("github_token") == evil


def test_disk_cache_shard_pruning(tmp_path, monkeypatch):
    cache = HTTPDiskCache(root=tmp_path)
    monkeypatch.setattr(HTTPDiskCache, "_SHARD_LIMIT", 5)
    # 同一分片：手动往一个分片目录塞条目
    shard = tmp_path / "aa"
    shard.mkdir(parents=True)
    for i in range(10):
        (shard / f"entry{i}.json").write_text("{}", encoding="utf-8")
    cache._prune_shard(shard)
    remaining = list(shard.glob("*.json"))
    assert len(remaining) == 5
