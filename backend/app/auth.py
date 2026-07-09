# -*- coding: utf-8 -*-
"""Shared authentication dependency.

Requires a configured shared secret (ZREAD_BACKEND_API_KEY) on every /api/v1
request via ``Authorization: Bearer <key>``. Comparison is constant-time
(hmac.compare_digest) to resist timing attacks.

When the key is unset the API is left open — but a warning is logged at
startup so a deployment doesn't accidentally expose its GitHub/LLM credits.
"""

import hmac
import logging

from fastapi import HTTPException, Request, status

from app.config import settings

_log = logging.getLogger("zread_ai.auth")

_WARNED_OPEN = False


def require_api_key(request: Request) -> None:
    """FastAPI dependency: reject the request unless the bearer key matches.

    Uses compare_digest to avoid a timing side-channel on the secret. The
    scheme is checked too, so a raw key without the ``Bearer`` prefix fails.
    """
    global _WARNED_OPEN
    expected = settings.backend_api_key
    if not expected:
        if not _WARNED_OPEN:
            _log.warning(
                "ZREAD_BACKEND_API_KEY is unset — the AI API is open (no auth). "
                "Set a shared secret before exposing the service on a network."
            )
            _WARNED_OPEN = True
        return  # fail open (documented) — local dev / first-run convenience

    provided = request.headers.get("authorization", "")
    # Accept only "Bearer <key>"; constant-time compare on the whole header
    # avoids leaking the key length or a prefix match.
    token = f"Bearer {expected}"
    if not hmac.compare_digest(provided, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized: invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
