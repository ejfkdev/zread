# -*- coding: utf-8 -*-
"""LLM streaming tests: delta normalization (content + reasoning_content)."""

import httpx
import pytest
import respx

from app.config import settings
from app.llm import build_messages, stream_chat


def _sse_line(payload: dict | None = None, done: bool = False) -> str:
    if done:
        return "data: [DONE]"
    import json

    return f"data: {json.dumps(payload)}"


def test_build_messages_includes_context_and_citation_instruction():
    chunks = [
        {"file_path": "docs.md", "heading": "Install", "content": "run make"},
        {"file_path": "api.md", "heading": "Usage", "content": "call foo()"},
    ]
    msgs = build_messages("o/r", chunks, [], "how?")
    assert msgs[0]["role"] == "system"
    sys = msgs[0]["content"]
    assert "o/r" in sys
    assert "docs.md" in sys
    assert "Install" in sys
    assert "call foo()" in sys
    assert msgs[-1] == {"role": "user", "content": "how?"}


def test_build_messages_includes_history():
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]
    msgs = build_messages("o/r", [], history, "q2")
    # system, history(2), query(1) = 4
    assert len(msgs) == 4
    assert msgs[1]["content"] == "q1"
    assert msgs[-1]["content"] == "q2"


@respx.mock
async def test_stream_chat_yields_text_and_reasoning():
    body = "\n".join(
        [
            _sse_line({"choices": [{"delta": {"content": "Hel"}}]}),
            _sse_line({"choices": [{"delta": {"reasoning_content": "thinking"}}]}),
            _sse_line({"choices": [{"delta": {"content": "lo"}}]}),
            _sse_line(done=True),
        ]
    )
    respx.post(f"{settings.llm_base_url}/chat/completions").mock(
        return_value=httpx.Response(200, text=body)
    )
    async with httpx.AsyncClient() as c:
        deltas = [d async for d in stream_chat(c, [{"role": "user", "content": "hi"}])]

    assert ("Hel", "") in deltas
    assert ("", "thinking") in deltas
    assert ("lo", "") in deltas


@respx.mock
async def test_stream_chat_empty_delta_skipped():
    body = "\n".join(
        [
            _sse_line({"choices": [{"delta": {}}]}),  # empty delta
            _sse_line({"choices": [{"delta": {"content": "x"}}]}),
            _sse_line(done=True),
        ]
    )
    respx.post(f"{settings.llm_base_url}/chat/completions").mock(
        return_value=httpx.Response(200, text=body)
    )
    async with httpx.AsyncClient() as c:
        deltas = [d async for d in stream_chat(c, [{"role": "user", "content": "hi"}])]
    # Empty delta filtered out.
    assert deltas == [("x", "")]


@respx.mock
async def test_stream_chat_handles_missing_choices():
    body = "\n".join(
        [
            _sse_line({"choices": []}),  # malformed
            _sse_line({"choices": [{"delta": {"content": "y"}}]}),
            _sse_line(done=True),
        ]
    )
    respx.post(f"{settings.llm_base_url}/chat/completions").mock(
        return_value=httpx.Response(200, text=body)
    )
    async with httpx.AsyncClient() as c:
        deltas = [d async for d in stream_chat(c, [{"role": "user", "content": "hi"}])]
    assert deltas == [("y", "")]
