# -*- coding: utf-8 -*-
"""Talk router: create / message (SSE) / delete.

SSE event format the client parses (must match exactly):
    event:answer
    data:{"reasoning_content":"<optional>","text":"<incremental>"}
    event:round_finish
    data:{"reasoning_content":"","text":"<full answer>"}
    event:finish
    data:{}
"""

import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.auth import require_api_key
from app.db import get_db
from app.models import MessageSend, TalkCreate, ok
from app.rag import answer_stream, ensure_indexed

router = APIRouter(tags=["talk"], dependencies=[Depends(require_api_key)])
_log = logging.getLogger("zread_ai.talk_router")


@router.post("/talk")
async def create_talk(body: TalkCreate) -> Dict[str, Any]:
    """Create a talk session bound to an indexed repo."""
    if not body.repo_id:
        raise HTTPException(status_code=400, detail="repo_id is required")
    talk_id = uuid.uuid4().hex
    db = get_db()
    db.execute(
        "INSERT INTO talks(talk_id, repo_id, created_at) VALUES(?,?,?)",
        (talk_id, body.repo_id, time.time()),
    )
    db.commit()
    return ok({"talk_id": talk_id})


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event:{event}\ndata:{json.dumps(data, ensure_ascii=False)}\n\n"


async def _event_stream(
    talk_id: str, query: str, model: str | None
) -> AsyncIterator[str]:
    """Yield SSE events: progressive answer deltas, then round_finish, finish.

    On error yields event:error and terminates.
    """
    full_text = ""
    full_reasoning = ""
    try:
        async for delta_text, delta_reasoning in answer_stream(
            talk_id=talk_id, query=query, model=model
        ):
            if delta_text:
                full_text += delta_text
                yield _sse("answer", {"reasoning_content": "", "text": delta_text})
            if delta_reasoning:
                full_reasoning += delta_reasoning
                yield _sse(
                    "answer", {"reasoning_content": delta_reasoning, "text": ""}
                )
        # At least one non-empty payload must be sent before finish.
        if not full_text and not full_reasoning:
            yield _sse("answer", {"reasoning_content": "", "text": ""})
        yield _sse("round_finish", {"reasoning_content": full_reasoning, "text": full_text})
        yield _sse("finish", {})
    except Exception as exc:
        _log.exception("talk %s failed", talk_id)
        yield _sse("error", {"text": str(exc)})


@router.post("/talk/{talk_id}/message")
async def send_message(talk_id: str, body: MessageSend):
    """Stream an answer back as SSE."""
    db = get_db()
    row = db.execute("SELECT * FROM talks WHERE talk_id=?", (talk_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"talk {talk_id} not found")

    repo_id = row["repo_id"]
    model = body.model or row["model"] or None

    # Persist the user message before streaming.
    db.execute(
        "INSERT INTO talk_messages(talk_id, role, content, created_at) VALUES(?,?,?,?)",
        (talk_id, "user", body.query, time.time()),
    )
    db.commit()

    # If the repo isn't indexed yet, auto-index now (the first event will
    # surface progress). This keeps the client path simple: just ask.
    await ensure_indexed(repo_id)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
    }
    return StreamingResponse(
        _event_stream(talk_id, body.query, model),
        media_type="text/event-stream",
        headers=headers,
    )


@router.delete("/talk/{talk_id}")
async def delete_talk(talk_id: str) -> Dict[str, Any]:
    """Remove a talk and its messages."""
    db = get_db()
    db.execute("DELETE FROM talk_messages WHERE talk_id=?", (talk_id,))
    db.execute("DELETE FROM talks WHERE talk_id=?", (talk_id,))
    db.commit()
    return ok({"talk_id": talk_id, "deleted": True})
