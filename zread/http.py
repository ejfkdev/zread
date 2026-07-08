# -*- coding: utf-8 -*-
"""HTTP 层：带默认超时、重定向和指数退避重试的 httpx 包装。"""

import asyncio
import sys
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Callable, Dict, Optional

import httpx as _httpx

from zread.config import tr

HTTPX_TIMEOUT_SECONDS = 5.0
HTTPX_MAX_REDIRECTS = 2
HTTPX_MAX_RETRIES = 3
HTTPX_RETRY_STATUS_CODES = {429, 502, 503, 504}
# 指数退避基础延迟（秒）；429/503 带 Retry-After 时优先遵循（上限见下）
HTTPX_BACKOFF_SECONDS = (0.5, 1.0, 2.0)
HTTPX_MAX_RETRY_AFTER = 30.0

# 可注入的 sleep（测试时替换，避免真实等待）
_sleep = time.sleep
_async_sleep = asyncio.sleep


def _apply_httpx_client_defaults(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """为 httpx Client/AsyncClient 注入统一默认配置。"""
    merged = dict(kwargs)
    merged.setdefault("follow_redirects", True)
    merged.setdefault("max_redirects", HTTPX_MAX_REDIRECTS)
    merged.setdefault("timeout", HTTPX_TIMEOUT_SECONDS)
    return merged


def _apply_httpx_request_defaults(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """为单次请求注入统一默认配置。"""
    merged = dict(kwargs)
    merged.setdefault("follow_redirects", True)
    merged.setdefault("timeout", HTTPX_TIMEOUT_SECONDS)
    return merged


def _retry_delay(attempt: int, exc: Exception) -> Optional[float]:
    """计算第 attempt 次失败后的等待时长；返回 None 表示不再重试。"""
    if attempt >= HTTPX_MAX_RETRIES - 1:
        return None
    delay = HTTPX_BACKOFF_SECONDS[min(attempt, len(HTTPX_BACKOFF_SECONDS) - 1)]
    if isinstance(exc, _httpx.HTTPStatusError) and exc.response is not None:
        retry_after = exc.response.headers.get("retry-after", "")
        if retry_after:
            try:
                delay = max(delay, min(float(retry_after), HTTPX_MAX_RETRY_AFTER))
            except ValueError:
                pass
    return delay


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, _httpx.HTTPStatusError):
        response = exc.response
        return response is not None and response.status_code in HTTPX_RETRY_STATUS_CODES
    return isinstance(exc, _httpx.RequestError)


def _retry_sync_request(request_fn: Callable[[], Any]) -> Any:
    """同步请求自动重试（指数退避，遵循 Retry-After）。"""
    last_error: Optional[Exception] = None
    for attempt in range(HTTPX_MAX_RETRIES):
        try:
            return request_fn()
        except (_httpx.RequestError, _httpx.HTTPStatusError) as exc:
            if not _is_retryable(exc):
                raise
            last_error = exc
            delay = _retry_delay(attempt, exc)
            if delay is None:
                break
            _sleep(delay)
    if last_error:
        raise last_error
    raise RuntimeError(tr("errors.http_request_failed"))


async def _retry_async_request(request_fn: Callable[[], Any]) -> Any:
    """异步请求自动重试（指数退避，遵循 Retry-After）。"""
    last_error: Optional[Exception] = None
    for attempt in range(HTTPX_MAX_RETRIES):
        try:
            return await request_fn()
        except (_httpx.RequestError, _httpx.HTTPStatusError) as exc:
            if not _is_retryable(exc):
                raise
            last_error = exc
            delay = _retry_delay(attempt, exc)
            if delay is None:
                break
            await _async_sleep(delay)
    if last_error:
        raise last_error
    raise RuntimeError(tr("errors.http_request_failed"))


def _raise_for_retryable_status(response: _httpx.Response) -> None:
    """对可重试状态码抛出 HTTPStatusError，交给统一重试层处理。"""
    if response.status_code in HTTPX_RETRY_STATUS_CODES:
        try:
            request = response.request
        except RuntimeError:
            request = _httpx.Request("GET", str(response.url))
        raise _httpx.HTTPStatusError(
            f"Retryable HTTP error: {response.status_code}",
            request=request,
            response=response,
        )


class WrappedHTTPXClient(_httpx.Client):
    """带默认超时、重定向和重试的同步 httpx Client。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **_apply_httpx_client_defaults(kwargs))

    def request(self, method: str, url: str, *args, **kwargs):
        request_kwargs = _apply_httpx_request_defaults(kwargs)
        return _retry_sync_request(
            lambda: self._request_once(method, url, *args, **request_kwargs)
        )

    def _request_once(self, method: str, url: str, *args, **kwargs):
        response = super(WrappedHTTPXClient, self).request(method, url, *args, **kwargs)
        _raise_for_retryable_status(response)
        return response

    @contextmanager
    def stream(self, method: str, url: str, *args, **kwargs):
        stream_kwargs = _apply_httpx_request_defaults(kwargs)
        stream_cm, response = _retry_sync_request(
            lambda: self._open_stream_once(method, url, *args, **stream_kwargs)
        )
        try:
            yield response
        finally:
            stream_cm.__exit__(None, None, None)

    def _open_stream_once(self, method: str, url: str, *args, **kwargs):
        stream_cm = super(WrappedHTTPXClient, self).stream(method, url, *args, **kwargs)
        response = stream_cm.__enter__()
        try:
            _raise_for_retryable_status(response)
        except Exception:
            stream_cm.__exit__(*sys.exc_info())
            raise
        return stream_cm, response


class WrappedHTTPXAsyncClient(_httpx.AsyncClient):
    """带默认超时、重定向和重试的异步 httpx Client。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **_apply_httpx_client_defaults(kwargs))

    async def request(self, method: str, url: str, *args, **kwargs):
        request_kwargs = _apply_httpx_request_defaults(kwargs)
        return await _retry_async_request(
            lambda: self._request_once(method, url, *args, **request_kwargs)
        )

    async def _request_once(self, method: str, url: str, *args, **kwargs):
        response = await super(WrappedHTTPXAsyncClient, self).request(
            method, url, *args, **kwargs
        )
        _raise_for_retryable_status(response)
        return response

    @asynccontextmanager
    async def stream(self, method: str, url: str, *args, **kwargs):
        stream_kwargs = _apply_httpx_request_defaults(kwargs)
        stream_cm, response = await _retry_async_request(
            lambda: self._open_stream_once(method, url, *args, **stream_kwargs)
        )
        try:
            yield response
        finally:
            await stream_cm.__aexit__(None, None, None)

    async def _open_stream_once(self, method: str, url: str, *args, **kwargs):
        stream_cm = super(WrappedHTTPXAsyncClient, self).stream(
            method, url, *args, **kwargs
        )
        response = await stream_cm.__aenter__()
        try:
            _raise_for_retryable_status(response)
        except Exception:
            await stream_cm.__aexit__(*sys.exc_info())
            raise
        return stream_cm, response


class WrappedHTTPXModule:
    """兼容 httpx 常用接口的包装器。"""

    Client = WrappedHTTPXClient
    AsyncClient = WrappedHTTPXAsyncClient
    Timeout = _httpx.Timeout
    Limits = _httpx.Limits
    RequestError = _httpx.RequestError
    HTTPStatusError = _httpx.HTTPStatusError

    def request(self, method: str, url: str, *args, **kwargs):
        request_kwargs = _apply_httpx_request_defaults(kwargs)
        return self._request_via_client(method, url, *args, **request_kwargs)

    def get(self, url: str, *args, **kwargs):
        return self.request("GET", url, *args, **kwargs)

    def post(self, url: str, *args, **kwargs):
        return self.request("POST", url, *args, **kwargs)

    def delete(self, url: str, *args, **kwargs):
        return self.request("DELETE", url, *args, **kwargs)

    def _request_via_client(self, method: str, url: str, *args, **kwargs):
        with self.Client() as client:
            return client.request(method, url, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(_httpx, name)


httpx = WrappedHTTPXModule()
