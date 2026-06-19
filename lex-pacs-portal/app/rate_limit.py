from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from .config import settings

_hits: dict[str, list[float]] = defaultdict(list)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_login_rate_limit(request: Request) -> None:
    """S10 — limita tentativas de login por IP (complementa nginx)."""
    limit = settings.login_rate_limit_attempts
    window = settings.login_rate_limit_window_seconds
    key = _client_key(request)
    now = time.monotonic()
    recent = [t for t in _hits[key] if now - t < window]
    if len(recent) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de login. Aguarde alguns minutos.",
        )
    recent.append(now)
    _hits[key] = recent
