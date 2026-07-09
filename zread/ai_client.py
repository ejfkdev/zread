# -*- coding: utf-8 -*-
"""Thin async client for the zread-ai RAG backend.

Talk lifecycle + SSE streaming, mirroring upstream's raw (non-retry-wrapped)
streaming client. The SSE parser is the most format-sensitive piece — it is
unit-tested byte-for-byte against a recorded fixture.

Endpoints consumed:
    POST {base}/api/v1/repos/{owner}/{name}/index   (optional; auto-triggered)
    GET  {base}/api/v1/repos/{owner}/{name}/status
    POST {base}/api/v1/talk                          -> {"code":0,"data":{"talk_id"}}
    POST {base}/api/v1/talk/{id}/message             -> SSE stream
    DEL  {base}/api/v1/talk/{id}
"""

import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Dict, Optional

import httpx as _httpx

_log = logging.getLogger("zread.ai_client")

DEFAULT_TIMEOUT = 120.0


@dataclass
class SSEEvent:
    """One parsed SSE event from the backend."""

    event: str  # "answer" | "round_finish" | "finish" | "error"
    text: str = ""
    reasoning_content: str = ""

    @property
    def is_finish(self) -> bool:
        return self.event == "finish"

    @property
    def is_error(self) -> bool:
        return self.event == "error"


def parse_sse_stream(raw_bytes: bytes) -> "list[SSEEvent]":
    """Parse a complete raw SSE payload into events (used by tests + fallback).

    The wire format is byte-for-byte:
        event:answer\\ndata:{"reasoning_content":"","text":"hi"}\\n\\n
        event:round_finish\\ndata:{"reasoning_content":"","text":"hi"}\\n\\n
        event:finish\\ndata:{}\\n\\n
    """
    events: list[SSEEvent] = []
    text = raw_bytes.decode("utf-8", errors="replace")
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = ""
        data_str = ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_str = line[len("data:") :].strip()
        if not event_name:
            continue
        text_field = ""
        reasoning = ""
        if data_str:
            try:
                payload = json.loads(data_str)
                text_field = payload.get("text", "") or ""
                reasoning = payload.get("reasoning_content", "") or ""
            except json.JSONDecodeError:
                # Tolerate malformed data lines without crashing the stream.
                pass
        events.append(SSEEvent(event=event_name, text=text_field, reasoning_content=reasoning))
    return events


async def stream_sse_lines(resp: _httpx.Response) -> AsyncIterator[SSEEvent]:
    """Incrementally parse SSE events from a streaming httpx response.

    Yields each event as it completes. A ``finish`` event terminates iteration.
    """
    event_name = ""
    data_lines: list[str] = []

    async def _flush():
        nonlocal event_name, data_lines
        if not event_name:
            data_lines = []
            return None
        data_str = "\n".join(data_lines).strip()
        text_field = ""
        reasoning = ""
        if data_str:
            try:
                payload = json.loads(data_str)
                text_field = payload.get("text", "") or ""
                reasoning = payload.get("reasoning_content", "") or ""
            except json.JSONDecodeError:
                pass
        ev = SSEEvent(event=event_name, text=text_field, reasoning_content=reasoning)
        event_name = ""
        data_lines = []
        return ev

    async for line in resp.aiter_lines():
        line = line.rstrip("\r\n")
        if line == "":
            # Blank line = event boundary.
            ev = await _flush()
            if ev is not None:
                yield ev
                if ev.is_finish:
                    return
        elif line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
        # Other lines (comments ":keepalive", id:, retry:) are ignored.

    # Flush any trailing event if the stream ended without a blank line.
    ev = await _flush()
    if ev is not None:
        yield ev


async def create_talk(
    client: _httpx.AsyncClient, backend_url: str, repo_id: str, api_key: Optional[str] = None
) -> str:
    """Create a talk session; return the talk_id."""
    headers = _auth_headers(api_key)
    resp = await client.post(
        f"{backend_url.rstrip('/')}/api/v1/talk",
        json={"repo_id": repo_id, "query": " "},
        headers=headers,
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(body.get("message") or "create_talk failed")
    return body["data"]["talk_id"]


async def stream_message(
    client: _httpx.AsyncClient,
    backend_url: str,
    talk_id: str,
    query: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> AsyncIterator[SSEEvent]:
    """Stream an answer as SSE events.

    Uses the raw stream (no retry wrapper) to avoid buffering token deltas.
    """
    headers = _auth_headers(api_key)
    payload: Dict = {"query": query}
    if model:
        payload["model"] = model
    async with client.stream(
        "POST",
        f"{backend_url.rstrip('/')}/api/v1/talk/{talk_id}/message",
        json=payload,
        headers=headers,
        timeout=DEFAULT_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        async for ev in stream_sse_lines(resp):
            yield ev
            if ev.is_finish or ev.is_error:
                return


async def delete_talk(
    client: _httpx.AsyncClient, backend_url: str, talk_id: str, api_key: Optional[str] = None
) -> None:
    """Delete a talk session (best-effort)."""
    headers = _auth_headers(api_key)
    try:
        await client.delete(
            f"{backend_url.rstrip('/')}/api/v1/talk/{talk_id}",
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
    except _httpx.HTTPError as exc:
        _log.debug("delete_talk best-effort failed: %s", exc)


def _auth_headers(api_key: Optional[str]) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}
