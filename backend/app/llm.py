# -*- coding: utf-8 -*-
"""LLM streaming over an OpenAI-compatible chat completions endpoint.

Normalizes provider variance in delta shape:
  - delta.content            → text (standard OpenAI)
  - delta.reasoning_content  → reasoning (GLM/o1-style thinking)
Falls back gracefully when either field is absent.
"""

import json
import logging
from typing import AsyncIterator, List, Tuple

import httpx

from app.config import settings

_log = logging.getLogger("zread_ai.llm")

_CHAT_TIMEOUT = 120.0


def build_messages(
    repo_label: str,
    context_chunks: List[dict],
    history: List[dict],
    query: str,
) -> List[dict]:
    """Assemble the chat message list: system prompt + RAG context + history + query."""
    ctx_parts = []
    for i, ch in enumerate(context_chunks, 1):
        loc = ch.get("heading") or "(top)"
        ctx_parts.append(f"[{i}] {ch['file_path']} — {loc}\n{ch['content']}")
    context_block = "\n\n".join(ctx_parts) if ctx_parts else "(no indexed context yet)"

    system = (
        f"You are answering questions about the repository {repo_label}. "
        "Use ONLY the provided context chunks to answer. "
        "When you use a chunk, cite it as [file_path](section). "
        "If the context does not contain the answer, say you don't know "
        "rather than guessing.\n\n"
        f"--- CONTEXT ---\n{context_block}\n--- END CONTEXT ---"
    )
    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": query})
    return messages


async def stream_chat(
    client: httpx.AsyncClient,
    messages: List[dict],
    model: str | None = None,
) -> AsyncIterator[Tuple[str, str]]:
    """Yield (text_delta, reasoning_delta) from a streaming chat completion.

    Uses the raw stream (no retry wrapper) to avoid buffering; failures
    surface as exceptions that the caller turns into SSE error events.
    """
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model or settings.llm_model,
        "messages": messages,
        "stream": True,
    }
    async with client.stream(
        "POST", url, headers=headers, json=payload, timeout=settings.llm_timeout
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[len("data:") :].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            text = delta.get("content") or ""
            reasoning = delta.get("reasoning_content") or ""
            if text or reasoning:
                yield text, reasoning
