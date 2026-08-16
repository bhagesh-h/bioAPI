"""HTTP middleware: request context, access logging, body limits, security headers."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import ClassVar

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.context import RequestContext
from app.core.errors import ErrorCode, error_payload
from app.core.logging import get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
PROCESS_TIME_HEADER = "X-Process-Time"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, scope the warning buffer, and log the exchange.

    An inbound ``X-Request-ID`` is honoured so a trace survives a reverse proxy
    or a caller's own correlation id; otherwise a UUID4 is minted.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())

        with RequestContext(request_id):
            request.state.request_id = request_id
            started = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                # The exception handlers build the body; this only records timing.
                logger.exception(
                    "request.failed",
                    method=request.method,
                    path=request.url.path,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                raise

            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            response.headers[REQUEST_ID_HEADER] = request_id
            response.headers[PROCESS_TIME_HEADER] = f"{duration_ms:.2f}"

            logger.info(
                "request.completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client=request.client.host if request.client else None,
            )
            return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies before they are buffered.

    A declared ``Content-Length`` is checked up front, which is what a well
    behaved client sends. Chunked uploads without the header still get caught
    downstream by the per-upload check in the file service.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > self.max_bytes:
                limit_mb = self.max_bytes / (1024 * 1024)
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content=error_payload(
                        code=ErrorCode.PAYLOAD_TOO_LARGE,
                        message=f"Request body exceeds the {limit_mb:.0f} MB limit.",
                        details={
                            "limit_bytes": self.max_bytes,
                            "received_bytes": declared,
                        },
                    ),
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add the baseline hardening headers to every response."""

    _HEADERS: ClassVar[dict[str, str]] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in self._HEADERS.items():
            response.headers.setdefault(header, value)
        return response


def register_middleware(app: FastAPI) -> None:
    """Install middleware.

    Starlette runs middleware in reverse registration order, so the last one
    added is the outermost. Request context is registered last on purpose: it
    then wraps everything else and every log line carries a request id.
    """
    if settings.SECURITY_HEADERS_ENABLED:
        app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_size_bytes)

    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_credentials="*" not in settings.BACKEND_CORS_ORIGINS,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=[REQUEST_ID_HEADER, PROCESS_TIME_HEADER],
        )

    app.add_middleware(RequestContextMiddleware)
