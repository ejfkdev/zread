# -*- coding: utf-8 -*-
"""Backend test config: temp DB, deterministic settings, no real network."""

import os
import tempfile

# Must be set before importing app (pydantic-settings reads env at import).
_tmp = tempfile.mkdtemp(prefix="zread-ai-test-")
os.environ["DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["LLM_API_KEY"] = "test-key"
os.environ["EMBED_DIM"] = "8"  # small, fast deterministic vectors in tests
os.environ["CHUNK_MAX_TOKENS"] = "50"
os.environ["CHUNK_OVERLAP_TOKENS"] = "10"

import pytest  # noqa: E402

from app.db import get_db, reset_db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Wipe all tables before each test for isolation."""
    reset_db()
    yield
    reset_db()


@pytest.fixture
def db():
    return get_db()
