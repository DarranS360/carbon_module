"""
api/dependencies.py

Shared FastAPI dependencies used across API routes.
"""

from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

from api.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: str | None = Security(_api_key_header)) -> None:
    """
    Enforce API-key authentication when ``API_KEY`` is configured.

    - If ``API_KEY`` is empty (default), all requests are allowed through.
    - If ``API_KEY`` is set, every request to a protected route must include
      the header ``X-API-Key: <value>``.  Requests with a missing or incorrect
      key receive a **403 Forbidden** response.
    """
    if not settings.api_key:
        return  # auth disabled — no key configured

    if key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key.",
        )
