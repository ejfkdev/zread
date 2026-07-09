# -*- coding: utf-8 -*-
"""Chunker unit tests: header splits, oversize split, overlap, heading path."""

from app.chunker import chunk_markdown


def test_simple_header_split():
    md = "# Title\nIntro text.\n\n## Sub\nSub text here."
    chunks = chunk_markdown("README.md", md, max_tokens=500)
    # Two headers + the preamble handling: each header section is a chunk.
    assert len(chunks) >= 2
    headings = [c.heading for c in chunks]
    assert "Title" in headings
    assert "Title > Sub" in headings


def test_heading_path_nested():
    md = "# A\na body\n## B\nb body\n### C\nc body"
    chunks = chunk_markdown("docs.md", md, max_tokens=500)
    paths = [c.heading for c in chunks]
    assert "A" in paths
    assert "A > B" in paths
    assert "A > B > C" in paths


def test_oversize_section_windowed():
    # Build a section whose body far exceeds max_tokens.
    body = " ".join(["word"] * 500)
    md = f"# Big\n{body}"
    chunks = chunk_markdown("big.md", md, max_tokens=50, overlap=10)
    assert len(chunks) > 1
    # Every chunk must carry the same heading path.
    assert all(c.heading == "Big" for c in chunks)
    # Ordinals are sequential.
    ordinals = [c.ordinal for c in chunks]
    assert ordinals == list(range(len(chunks)))


def test_content_has_context_anchor():
    md = "# Install\nDo the thing."
    chunks = chunk_markdown("INSTALL.md", md, max_tokens=500)
    assert len(chunks) == 1
    # Anchor line prepended for retrieval quality.
    assert "INSTALL.md" in chunks[0].content
    assert "Install" in chunks[0].content


def test_no_headers_single_chunk():
    md = "Just a paragraph of plain text with no headers at all."
    chunks = chunk_markdown("plain.txt", md, max_tokens=500)
    assert len(chunks) == 1
    assert chunks[0].heading == ""


def test_empty_input():
    assert chunk_markdown("empty.md", "", max_tokens=500) == []


def test_token_count_positive():
    md = "# H\nSome real content to embed here."
    chunks = chunk_markdown("f.md", md, max_tokens=500)
    assert all(c.token_count > 0 for c in chunks)
