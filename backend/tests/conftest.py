# -*- coding: utf-8 -*-
"""Backend test config: temp DB, deterministic settings, no real network."""

import os
import tempfile

# Must be set before importing app (pydantic-settings reads env at import).
# All fields use the ZREAD_ env prefix (see app/config.py).
_tmp = tempfile.mkdtemp(prefix="zread-ai-test-")
os.environ["ZREAD_DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["ZREAD_LLM_API_KEY"] = "test-key"
os.environ["ZREAD_EMBED_DIM"] = "8"  # small, fast deterministic vectors in tests
os.environ["ZREAD_CHUNK_MAX_TOKENS"] = "50"
os.environ["ZREAD_CHUNK_OVERLAP_TOKENS"] = "10"

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
