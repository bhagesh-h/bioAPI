"""Shared route dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, UploadFile

from app.core.config import settings
from app.core.security import require_api_key

#: Applied to every ``/api/v1`` router. When ``API_KEY`` is unset this is a no-op.
AuthenticatedRoute = [Depends(require_api_key)]

ApiKey = Annotated[str | None, Depends(require_api_key)]


def upload_limit_bytes() -> int:
    """The configured per-file ceiling, injected so tests can override it."""
    return settings.max_upload_size_bytes


UploadLimit = Annotated[int, Depends(upload_limit_bytes)]

__all__ = ["ApiKey", "AuthenticatedRoute", "UploadFile", "UploadLimit", "upload_limit_bytes"]
