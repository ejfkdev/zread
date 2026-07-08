# -*- coding: utf-8 -*-
"""CLI 命令：config 读写、mcp transport 校验、tree/limits 输出。"""

import httpx
import respx
from typer.testing import CliRunner

from zread.cli import cli_app

API = "https://api.github.com"

runner = CliRunner()


def test_mcp_unknown_transport_exits_nonzero():
    result = runner.invoke(cli_app, ["mcp", "bogus"])
    assert result.exit_code == 2


def test_mcp_invalid_address_exits_nonzero():
    result = runner.invoke(cli_app, ["mcp", "http", ":abc"])
    assert result.exit_code == 2


def test_config_set_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(cli_app, ["config", "set", "lang", "en"])
    assert result.exit_code == 0, result.output

    config_file = tmp_path / ".config" / "zread" / "zread.toml"
    assert config_file.exists()
    assert oct(config_file.stat().st_mode & 0o777) == "0o600"

    result = runner.invoke(cli_app, ["config", "get", "lang"])
    assert result.exit_code == 0
    assert "en" in result.output


def test_config_token_is_masked(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    runner.invoke(cli_app, ["config", "set", "github_token", "ghp_supersecret123"])

    result = runner.invoke(cli_app, ["config", "get", "github_token"])
    assert result.exit_code == 0
    assert "ghp_supersecret123" not in result.output
    assert "ghp_" in result.output  # 前缀可见


def test_config_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    runner.invoke(cli_app, ["config", "set", "lang", "zh"])
    result = runner.invoke(cli_app, ["config", "unset", "lang"])
    assert result.exit_code == 0

    from zread.config import config_from_file

    assert "lang" not in config_from_file()


def test_config_rejects_unknown_key(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(cli_app, ["config", "set", "bogus", "x"])
    assert result.exit_code == 1


def test_config_path_command(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(cli_app, ["config", "path"])
    assert result.exit_code == 0
    assert "zread.toml" in result.output


@respx.mock
def test_tree_plain_output():
    respx.get(f"{API}/repos/o/r/git/trees/v1").mock(
        return_value=httpx.Response(
            200,
            json={
                "tree": [
                    {"path": "src/a.py", "type": "blob", "size": 11},
                    {"path": "src/b.py", "type": "blob", "size": 22},
                ],
                "truncated": False,
            },
        )
    )
    result = runner.invoke(
        cli_app, ["tree", "o/r", "--ref", "v1", "--plain"]
    )
    assert result.exit_code == 0, result.output
    assert "src/a.py" in result.output
    assert "src/b.py" in result.output


@respx.mock
def test_limits_plain_output():
    respx.get(f"{API}/rate_limit").mock(
        return_value=httpx.Response(
            200,
            json={
                "resources": {
                    "core": {"limit": 60, "remaining": 13, "reset": 1780000000}
                }
            },
        )
    )
    result = runner.invoke(cli_app, ["limits", "--plain"])
    assert result.exit_code == 0, result.output
    assert "13/60" in result.output


@respx.mock
def test_releases_plain_output():
    respx.get(f"{API}/repos/o/r/releases").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "tag_name": "v9.9",
                    "name": "Niner",
                    "published_at": "2026-01-02T00:00:00Z",
                    "prerelease": False,
                    "html_url": "https://github.com/o/r/releases/tag/v9.9",
                    "body": "",
                }
            ],
        )
    )
    result = runner.invoke(cli_app, ["releases", "o/r", "--plain"])
    assert result.exit_code == 0, result.output
    assert "v9.9" in result.output
    assert "2026-01-02" in result.output
