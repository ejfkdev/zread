# -*- coding: utf-8 -*-
"""SSE parser tests for ai_client — the most format-sensitive piece.

Validates byte-for-byte against the exact wire format the backend emits:
    event:answer
    data:{"reasoning_content":"","text":"<incremental>"}
    event:round_finish
    data:{"reasoning_content":"","text":"<full>"}
    event:finish
    data:{}

Follows the fork's convention: sync test functions wrapping asyncio.run()
(no pytest-asyncio dependency).
"""

import asyncio
import json

import httpx
import pytest
import respx

from zread.ai_client import (
    SSEEvent,
    create_talk,
    delete_talk,
    parse_sse_stream,
    stream_message,
    stream_sse_lines,
)


def _answer_delta(text="", reasoning=""):
    return f"event:answer\ndata:{json.dumps({'reasoning_content': reasoning, 'text': text})}\n\n"


def _round_finish(full_text, reasoning=""):
    return f"event:round_finish\ndata:{json.dumps({'reasoning_content': reasoning, 'text': full_text})}\n\n"


def _finish():
    return "event:finish\ndata:{}\n\n"


# ---------------------------------------------------------------------------
# parse_sse_stream (batch parser)
# ---------------------------------------------------------------------------


def test_parse_basic_stream():
    raw = (_answer_delta("Hello ") + _answer_delta("world.") + _round_finish("Hello world.") + _finish()).encode()
    events = parse_sse_stream(raw)
    assert len(events) == 4
    assert events[0].event == "answer"
    assert events[0].text == "Hello "
    assert events[1].text == "world."
    assert events[2].event == "round_finish"
    assert events[2].text == "Hello world."
    assert events[3].event == "finish"


def test_parse_reasoning_content():
    raw = (_answer_delta("", "thinking...") + _answer_delta("answer") + _finish()).encode()
    events = parse_sse_stream(raw)
    assert events[0].reasoning_content == "thinking..."
    assert events[0].text == ""
    assert events[1].text == "answer"


def test_parse_empty_fields_tolerated():
    # Both fields empty is still a valid event the client must tolerate.
    raw = (b'event:answer\ndata:{"reasoning_content":"","text":""}\n\n' + _finish().encode())
    events = parse_sse_stream(raw)
    assert events[0].text == ""
    assert events[0].reasoning_content == ""


def test_parse_malformed_data_does_not_crash():
    raw = (b"event:answer\ndata:not-json\n\n" + _finish().encode())
    events = parse_sse_stream(raw)
    assert len(events) == 2
    assert events[0].event == "answer"
    assert events[0].text == ""  # fell back gracefully


def test_parse_ignores_comment_lines():
    raw = (b":keepalive\n\n" + _answer_delta("hi").encode() + _finish().encode())
    events = parse_sse_stream(raw)
    # Comment block has no event name, so it's skipped.
    assert len(events) == 2
    assert events[0].text == "hi"


def test_is_finish_and_is_error_properties():
    assert SSEEvent(event="finish").is_finish
    assert SSEEvent(event="error", text="boom").is_error
    assert not SSEEvent(event="answer").is_finish


# ---------------------------------------------------------------------------
# stream_sse_lines (incremental parser over a real httpx stream)
# ---------------------------------------------------------------------------


@respx.mock
def test_stream_sse_lines_incremental():
    body = (_answer_delta("A") + _answer_delta("B") + _finish()).encode()
    respx.post("https://backend/api/v1/talk/t1/message").mock(
        return_value=httpx.Response(200, content=body)
    )

    async def _run():
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", "https://backend/api/v1/talk/t1/message") as resp:
                return [e async for e in stream_sse_lines(resp)]

    events = asyncio.run(_run())
    assert [e.event for e in events] == ["answer", "answer", "finish"]
    assert events[0].text == "A"
    assert events[1].text == "B"


# ---------------------------------------------------------------------------
# create_talk / delete_talk (HTTP envelope handling)
# ---------------------------------------------------------------------------


@respx.mock
def test_create_talk_returns_id():
    respx.post("https://backend/api/v1/talk").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"talk_id": "abc123"}})
    )

    async def _run():
        async with httpx.AsyncClient() as client:
            return await create_talk(client, "https://backend", "owner/repo@main")

    assert asyncio.run(_run()) == "abc123"


@respx.mock
def test_create_talk_error_envelope_raises():
    respx.post("https://backend/api/v1/talk").mock(
        return_value=httpx.Response(200, json={"code": 1, "message": "bad repo"})
    )

    async def _run():
        async with httpx.AsyncClient() as client:
            await create_talk(client, "https://backend", "owner/repo@main")

    with pytest.raises(RuntimeError, match="bad repo"):
        asyncio.run(_run())


@respx.mock
def test_delete_talk_best_effort_no_raise():
    respx.delete("https://backend/api/v1/talk/t1").mock(
        return_value=httpx.Response(500)
    )

    async def _run():
        async with httpx.AsyncClient() as client:
            await delete_talk(client, "https://backend", "t1")

    # Should not raise despite the 500.
    asyncio.run(_run())


@respx.mock
def test_stream_message_yields_until_finish():
    body = (_answer_delta("hi") + _round_finish("hi") + _finish()).encode()
    respx.post("https://backend/api/v1/talk/t1/message").mock(
        return_value=httpx.Response(200, content=body)
    )

    async def _run():
        async with httpx.AsyncClient() as client:
            return [
                e
                async for e in stream_message(
                    client, "https://backend", "t1", "question?"
                )
            ]

    events = asyncio.run(_run())
    assert events[-1].is_finish
    texts = [e.text for e in events if e.event == "answer"]
    assert texts == ["hi"]


@respx.mock
def test_stream_message_sends_api_key_header():
    body = _finish().encode()
    route = respx.post("https://backend/api/v1/talk/t1/message").mock(
        return_value=httpx.Response(200, content=body)
    )

    async def _run():
        async with httpx.AsyncClient() as client:
            async for _ in stream_message(
                client, "https://backend", "t1", "q", api_key="secret"
            ):
                pass

    asyncio.run(_run())
    assert route.calls.last.request.headers["authorization"] == "Bearer secret"
