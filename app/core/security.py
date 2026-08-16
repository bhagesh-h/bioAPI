"""API key authentication.

Using ``APIKeyHeader`` rather than a bare ``Header`` parameter means the scheme
shows up in the OpenAPI document, so Swagger UI renders an *Authorize* button
instead of an anonymous string field on every operation.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyHeader

from app.core.config import settings
from app.core.errors import AuthenticationError, AuthorizationError

API_KEY_HEADER_NAME = "X-API-Key"

api_key_scheme = APIKeyHeader(
    name=API_KEY_HEADER_NAME,
    auto_error=False,
    scheme_name="ApiKeyAuth",
    description=(
        "Set the `API_KEY` environment variable to require this header on every "
        "`/api/v1` route. When it is unset the API accepts unauthenticated requests."
    ),
)


async def require_api_key(
    provided_key: Annotated[str | None, Security(api_key_scheme)] = None,
) -> str | None:
    """Enforce the API key when one is configured.

    A missing header is a 401 (the client never presented credentials); a wrong
    value is a 403 (credentials were presented and rejected). The comparison is
    constant-time so response latency cannot be used to guess the key.
    """
    if not settings.API_KEY:
        return None

    if provided_key is None:
        raise AuthenticationError(
            f"Missing {API_KEY_HEADER_NAME} header.",
            details={"header": API_KEY_HEADER_NAME},
        )

    if not secrets.compare_digest(provided_key, settings.API_KEY):
        raise AuthorizationError(
            "The supplied API key is not valid.",
            details={"header": API_KEY_HEADER_NAME},
        )

    return provided_key
