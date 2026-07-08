# -*- coding: utf-8 -*-
"""测试公共配置：确定性语言、默认禁用磁盘缓存、不真实 sleep、清空进程缓存。"""

import os

# 必须在导入 zread 之前设置（zread.config 在导入时读取环境）
os.environ.setdefault("ZREAD_LANG", "en")
os.environ.setdefault("ZREAD_NO_CACHE", "1")

import pytest  # noqa: E402

import zread.http as zhttp  # noqa: E402
from zread.github import _GH_REPO_CACHE, _GH_TREE_CACHE  # noqa: E402


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """重试退避不真实等待；记录每次的延迟供断言。"""
    sleeps = []
    monkeypatch.setattr(zhttp, "_sleep", lambda seconds: sleeps.append(seconds))

    async def fake_async_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(zhttp, "_async_sleep", fake_async_sleep)
    return sleeps


@pytest.fixture(autouse=True)
def clear_process_caches():
    _GH_REPO_CACHE.clear()
    _GH_TREE_CACHE.clear()
    yield
    _GH_REPO_CACHE.clear()
    _GH_TREE_CACHE.clear()


@pytest.fixture(autouse=True)
def no_ambient_token(monkeypatch, tmp_path):
    """测试默认无 token、无用户配置文件（单测里再按需设置）。"""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ZREAD_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ZREAD_GITHUB_API_URL", raising=False)
    monkeypatch.delenv("ZREAD_GITHUB_RAW_URL", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
