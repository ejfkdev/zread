# -*- coding: utf-8 -*-
"""HTTP 重试：指数退避、Retry-After、不可重试状态码。"""

import httpx
import respx

from zread.http import httpx as zhttpx


@respx.mock
def test_retries_with_backoff_then_succeeds(no_sleep):
    route = respx.get("https://example.com/x")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, text="ok"),
    ]
    response = zhttpx.get("https://example.com/x")
    assert response.status_code == 200
    assert route.call_count == 3
    assert no_sleep == [0.5, 1.0]


@respx.mock
def test_honors_retry_after_header(no_sleep):
    route = respx.get("https://example.com/limited")
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "7"}),
        httpx.Response(200, text="ok"),
    ]
    response = zhttpx.get("https://example.com/limited")
    assert response.status_code == 200
    assert no_sleep == [7.0]


@respx.mock
def test_retry_after_is_capped(no_sleep):
    route = respx.get("https://example.com/limited")
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "3600"}),
        httpx.Response(200, text="ok"),
    ]
    zhttpx.get("https://example.com/limited")
    assert no_sleep == [30.0]


@respx.mock
def test_404_is_not_retried(no_sleep):
    route = respx.get("https://example.com/missing")
    route.side_effect = [httpx.Response(404)]
    response = zhttpx.get("https://example.com/missing")
    assert response.status_code == 404
    assert route.call_count == 1
    assert no_sleep == []


@respx.mock
def test_gives_up_after_max_retries(no_sleep):
    route = respx.get("https://example.com/broken")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(503),
    ]
    try:
        zhttpx.get("https://example.com/broken")
        raised = False
    except httpx.HTTPStatusError:
        raised = True
    assert raised
    assert route.call_count == 3
