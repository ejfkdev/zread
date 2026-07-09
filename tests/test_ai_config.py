# -*- coding: utf-8 -*-
"""AI config + graceful-degradation tests.

Verifies the non-breaking guarantee: when ZREAD_AI_BACKEND_URL is unset,
AI tools are not registered and the env-settings cascade works.
"""

import importlib

from zread.config import ai_api_key, ai_backend_url, ai_llm_model


def test_ai_backend_url_unset_returns_empty(no_ambient_token):
    import os

    assert "ZREAD_AI_BACKEND_URL" not in os.environ
    assert ai_backend_url() == ""


def test_ai_backend_url_from_env(monkeypatch):
    monkeypatch.setenv("ZREAD_AI_BACKEND_URL", "http://localhost:8709/")
    assert ai_backend_url() == "http://localhost:8709"  # trailing slash stripped


def test_ai_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ZREAD_AI_API_KEY", "secret123")
    assert ai_api_key() == "secret123"


def test_ai_llm_model_from_env(monkeypatch):
    monkeypatch.setenv("ZREAD_LLM_MODEL", "gpt-4o")
    assert ai_llm_model() == "gpt-4o"


def test_mcp_does_not_register_ai_tools_when_unconfigured(no_ambient_token):
    """Without ZREAD_AI_BACKEND_URL, ask/chat must NOT be registered."""
    from zread import mcp_server

    # Force re-evaluation by building a fresh MCP instance.
    registered = []

    class FakeMCP:
        def tool(self):
            def deco(fn):
                registered.append(fn.__name__)
                return fn

            return deco

        def resource(self, *a, **k):
            def deco(fn):
                return fn

            return deco

        def prompt(self, *a, **k):
            def deco(fn):
                return fn

            return deco

        def custom_route(self, *a, **k):
            def deco(fn):
                return fn

            return deco

    mcp_server._register_tools(FakeMCP())
    assert "ask" not in registered
    assert "chat" not in registered
    # Core tools still registered.
    assert "read_doc" in registered
    assert "search_code" in registered


def test_mcp_registers_ai_tools_when_configured(monkeypatch):
    """With ZREAD_AI_BACKEND_URL set, ask/chat ARE registered."""
    monkeypatch.setenv("ZREAD_AI_BACKEND_URL", "http://localhost:8709")
    from zread import config, mcp_server

    importlib.reload(config)
    importlib.reload(mcp_server)

    registered = []

    class FakeMCP:
        def tool(self):
            def deco(fn):
                registered.append(fn.__name__)
                return fn

            return deco

        def resource(self, *a, **k):
            def deco(fn):
                return fn

            return deco

        def prompt(self, *a, **k):
            def deco(fn):
                return fn

            return deco

        def custom_route(self, *a, **k):
            def deco(fn):
                return fn

            return deco

    mcp_server._register_tools(FakeMCP())
    assert "ask" in registered
    assert "chat" in registered

    # Restore so other tests aren't affected.
    monkeypatch.delenv("ZREAD_AI_BACKEND_URL", raising=False)
    importlib.reload(config)
    importlib.reload(mcp_server)
