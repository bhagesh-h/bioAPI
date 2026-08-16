"""Per-request context.

Carrying the request id and non-fatal warnings in context variables lets the
service layer stay free of HTTP concerns while still contributing to the
response envelope. The middleware opens a scope for each request; anything that
runs inside it can call :func:`add_warning` without threading a collector
through every function signature.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from types import TracebackType

_request_id: ContextVar[str | None] = ContextVar("bioapi_request_id", default=None)
_warnings: ContextVar[tuple[str, ...]] = ContextVar("bioapi_warnings", default=())


def get_request_id() -> str | None:
    """Return the id of the request being handled, if any."""
    return _request_id.get()


def add_warning(message: str) -> None:
    """Attach a non-fatal warning to the current response envelope.

    Duplicates are collapsed so a loop over many records cannot flood the
    response with the same sentence.
    """
    current = _warnings.get()
    if message in current:
        return
    _warnings.set((*current, message))


def get_warnings() -> list[str]:
    """Return the warnings collected so far for this request."""
    return list(_warnings.get())


class RequestContext:
    """Context manager that scopes the request id and warning buffer."""

    def __init__(self, request_id: str) -> None:
        self._request_id = request_id
        self._id_token: Token[str | None] | None = None
        self._warn_token: Token[tuple[str, ...]] | None = None

    def __enter__(self) -> RequestContext:
        self._id_token = _request_id.set(self._request_id)
        self._warn_token = _warnings.set(())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._id_token is not None:
            _request_id.reset(self._id_token)
        if self._warn_token is not None:
            _warnings.reset(self._warn_token)
