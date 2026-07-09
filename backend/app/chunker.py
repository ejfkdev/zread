# -*- coding: utf-8 -*-
"""Markdown chunker.

Splits on ATX headers; a section larger than CHUNK_MAX_TOKENS is further
split by token windows with CHUNK_OVERLAP. Each chunk carries a heading
path like "Installation > Docker".
"""

import re
from dataclasses import dataclass
from typing import List

import tiktoken

from app.config import settings

# ATX headers: lines starting with 1-6 '#' (not a closing fence).
_HEADER_RE = re.compile(r"^( {0,3})(#{1,6})(?:\s+)(.+?)\s*#*\s*$", re.MULTILINE)


@dataclass
class Chunk:
    file_path: str
    heading: str  # full heading path, e.g. "Install > Docker"
    ordinal: int
    content: str
    token_count: int = 0


@dataclass
class _Section:
    level: int
    title: str
    path: str  # accumulated "A > B > C"
    body: str


def _enc() -> "tiktoken.Encoding":
    return tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str, enc: "tiktoken.Encoding") -> int:
    return len(enc.encode(text, disallowed_special=()))


def _split_by_headers(text: str) -> List[_Section]:
    """Split markdown into sections by ATX headers, preserving heading paths."""
    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        return [_Section(level=0, title="", path="", body=text)]

    sections: List[_Section] = []
    # Anything before the first header is a preamble.
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append(_Section(level=0, title="", path="", body=preamble))

    # Track the active heading stack to build "A > B > C" paths.
    stack: List[tuple[int, str]] = []  # (level, title)
    for idx, m in enumerate(matches):
        level = len(m.group(2))
        title = m.group(3).strip()
        # Pop deeper-or-equal levels to keep the path hierarchical.
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        path = " > ".join(t for _, t in stack)

        body_start = m.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append(_Section(level=level, title=title, path=path, body=body))

    return sections


def _window_split(
    text: str, enc: "tiktoken.Encoding", max_tokens: int, overlap: int
) -> List[str]:
    """Token-window split with overlap, decoded back to text."""
    tokens = enc.encode(text, disallowed_special=())
    if not tokens:
        return []
    if len(tokens) <= max_tokens:
        return [text]
    step = max(1, max_tokens - overlap)
    pieces: List[str] = []
    i = 0
    while i < len(tokens):
        chunk_tokens = tokens[i : i + max_tokens]
        pieces.append(enc.decode(chunk_tokens))
        if i + max_tokens >= len(tokens):
            break
        i += step
    return pieces


def chunk_markdown(
    file_path: str,
    text: str,
    max_tokens: int | None = None,
    overlap: int | None = None,
) -> List[Chunk]:
    """Chunk a single markdown file into retrievable units.

    Each chunk's content is prefixed with a context line ("file_path § heading")
    to improve retrieval quality and let the LLM cite sources.
    """
    max_t = max_tokens or settings.chunk_max_tokens
    ov = overlap if overlap is not None else settings.chunk_overlap_tokens
    enc = _enc()
    sections = _split_by_headers(text)

    chunks: List[Chunk] = []
    ordinal = 0
    for sec in sections:
        # Skip header-only sections with no body — they carry no retrievable content.
        if not sec.body.strip():
            continue
        # Prepend a context anchor so embeddings "know" where they came from.
        anchor = sec.path or "(top)"
        section_text = f"[{file_path} § {anchor}]\n{sec.body}"

        for piece in _window_split(section_text, enc, max_t, ov):
            tc = _count_tokens(piece, enc)
            if tc == 0:
                continue
            chunks.append(
                Chunk(
                    file_path=file_path,
                    heading=sec.path,
                    ordinal=ordinal,
                    content=piece,
                    token_count=tc,
                )
            )
            ordinal += 1
    return chunks
