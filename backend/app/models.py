# -*- coding: utf-8 -*-
"""Pydantic request/response DTOs for the API."""

from typing import Any, Dict, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


class IndexRequest(BaseModel):
    ref: Optional[str] = None  # default branch resolved server-side


class RepoStatus(BaseModel):
    repo_id: str
    owner: str
    repo: str
    ref: str
    status: str
    file_count: int = 0
    chunk_count: int = 0
    indexed_at: Optional[float] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Talk / chat
# ---------------------------------------------------------------------------


class TalkCreate(BaseModel):
    # The " " placeholder mirrors upstream's contract; repo_id carries the target.
    repo_id: str
    query: str = " "


class TalkRef(BaseModel):
    talk_id: str


class MessageSend(BaseModel):
    query: str
    model: Optional[str] = None  # fall back to settings.llm_model


# ---------------------------------------------------------------------------
# Envelope — matches upstream {"code":0,"data":...} shape the client expects
# ---------------------------------------------------------------------------


class Envelope(BaseModel):
    code: int = 0
    data: Any = None
    message: Optional[str] = None


def ok(data: Any = None) -> Dict[str, Any]:
    return {"code": 0, "data": data}


def err(message: str, code: int = 1) -> Dict[str, Any]:
    return {"code": code, "message": message}
