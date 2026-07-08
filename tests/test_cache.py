# -*- coding: utf-8 -*-
"""缓存：TTL-LRU 行为、磁盘 ETag 缓存与 304 复用。"""

import httpx
import respx

from zread.cache import MISSING, TTLCache
from zread.github import _gh_api_get, _gh_fetch_raw

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


def test_ttlcache_stores_none_as_value():
    cache = TTLCache(maxsize=4, ttl=60)
    cache.set("k", None)
    assert cache.get("k") is None
    assert cache.get("absent") is MISSING


def test_ttlcache_expiry(monkeypatch):
    import zread.cache as zcache

    clock = [1000.0]
    monkeypatch.setattr(zcache.time, "monotonic", lambda: clock[0])
    cache = TTLCache(maxsize=4, ttl=10)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    clock[0] += 11
    assert cache.get("k") is MISSING


def test_ttlcache_eviction():
    cache = TTLCache(maxsize=2, ttl=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is MISSING
    assert cache.get("b") == 2
    assert cache.get("c") == 3


@respx.mock
def test_api_etag_revalidation(tmp_path, monkeypatch):
    monkeypatch.setenv("ZREAD_NO_CACHE", "0")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    route = respx.get(f"{API}/repos/o/r")
    route.side_effect = [
        httpx.Response(
            200, json={"name": "r", "stargazers_count": 5}, headers={"etag": 'W/"abc"'}
        ),
        httpx.Response(304),
    ]

    first = _gh_api_get("/repos/o/r")
    assert first["stargazers_count"] == 5

    second = _gh_api_get("/repos/o/r")
    assert second == first  # 304 时返回磁盘缓存内容

    revalidation = route.calls[1].request
    assert revalidation.headers["if-none-match"] == 'W/"abc"'


@respx.mock
def test_raw_etag_revalidation(tmp_path, monkeypatch):
    monkeypatch.setenv("ZREAD_NO_CACHE", "0")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    route = respx.get(f"{RAW}/o/r/HEAD/README.md")
    route.side_effect = [
        httpx.Response(200, text="cached body", headers={"etag": '"raw-1"'}),
        httpx.Response(304),
    ]

    assert _gh_fetch_raw("o", "r", "README.md") == "cached body"
    assert _gh_fetch_raw("o", "r", "README.md") == "cached body"
    assert route.calls[1].request.headers["if-none-match"] == '"raw-1"'


@respx.mock
def test_cache_disabled_by_default_in_tests(tmp_path):
    # conftest 设置了 ZREAD_NO_CACHE=1：不发送条件头
    route = respx.get(f"{API}/repos/o/rr")
    route.side_effect = [
        httpx.Response(200, json={"name": "rr"}, headers={"etag": 'W/"x"'}),
        httpx.Response(200, json={"name": "rr"}, headers={"etag": 'W/"x"'}),
    ]
    _gh_api_get("/repos/o/rr")
    _gh_api_get("/repos/o/rr")
    assert "if-none-match" not in route.calls[1].request.headers
