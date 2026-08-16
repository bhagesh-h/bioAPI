"""Request rate limiting.

This is implemented directly rather than through slowapi. slowapi's middleware
resolves the limit for a request by walking ``app.routes`` and reading each
route's ``endpoint``; FastAPI 0.141 wraps included routers in an internal
container object that exposes no ``endpoint``, so the lookup silently yields
``None`` and no limit is ever applied. A fixed-window counter is a few dozen
lines, has no coupling to FastAPI's routing internals, and lets health probes be
exempted by path.

The counter lives in process memory, which is correct for a single container.
Multiple replicas behind a load balancer each enforce their own share of the
budget; put the limit on the ingress instead if you need a global one.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.errors import ErrorCode, error_payload

#: Paths an orchestrator polls; throttling these would take a healthy instance
#: out of the load balancer.
EXEMPT_PATHS = frozenset({"/health", "/health/live", "/health/ready", "/ready", "/metrics"})

_PERIOD_SECONDS = {
    "second": 1,
    "sec": 1,
    "s": 1,
    "minute": 60,
    "min": 60,
    "m": 60,
    "hour": 3600,
    "h": 3600,
    "day": 86400,
    "d": 86400,
}


def parse_limit(expression: str) -> tuple[int, int]:
    """Turn ``"120/minute"`` into ``(120, 60)``.

    Raises ``ValueError`` on anything it cannot read, so a typo in the
    environment fails at start-up rather than disabling protection quietly.
    """
    raw_count, separator, raw_period = expression.strip().partition("/")
    if not separator:
        raise ValueError(f"Rate limit '{expression}' must look like '120/minute'.")

    try:
        count = int(raw_count.strip())
    except ValueError as exc:
        raise ValueError(f"Rate limit '{expression}' has a non-numeric count.") from exc

    if count < 1:
        raise ValueError(f"Rate limit '{expression}' must allow at least one request.")

    period = _PERIOD_SECONDS.get(raw_period.strip().lower())
    if period is None:
        raise ValueError(
            f"Rate limit '{expression}' has an unknown period. "
            f"Use one of: {', '.join(sorted(set(_PERIOD_SECONDS)))}."
        )
    return count, period


class FixedWindowCounter:
    """Counts requests per key within a fixed time window.

    Windows are aligned to the clock, so every key's allowance resets at the
    same instant. Expired entries are pruned opportunistically, which keeps
    memory bounded without a background task.
    """

    def __init__(self, limit: int, period_seconds: int) -> None:
        self.limit = limit
        self.period = period_seconds
        self._hits: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> tuple[bool, int, int]:
        """Record a request and report ``(allowed, remaining, reset_after)``."""
        timestamp = time.time() if now is None else now
        window = int(timestamp // self.period)
        reset_after = int((window + 1) * self.period - timestamp) + 1

        with self._lock:
            if len(self._hits) > 10_000:
                self._prune(window)

            recorded_window, count = self._hits.get(key, (window, 0))
            if recorded_window != window:
                count = 0

            if count >= self.limit:
                self._hits[key] = (window, count)
                return False, 0, reset_after

            count += 1
            self._hits[key] = (window, count)
            return True, self.limit - count, reset_after

    def reset(self) -> None:
        """Forget every recorded request. Used between tests."""
        with self._lock:
            self._hits.clear()

    def _prune(self, current_window: int) -> None:
        stale = [key for key, (window, _) in self._hits.items() if window < current_window]
        for key in stale:
            del self._hits[key]


def client_key(request: Request) -> str:
    """Identify the caller.

    Keying on the API key when one is present means a single noisy tenant behind
    a shared address cannot exhaust everyone else's budget.
    """
    api_key = request.headers.get("x-api-key")
    if api_key:
        return f"key:{api_key}"

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"

    return f"ip:{request.client.host if request.client else 'unknown'}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply a single default limit to everything except the exempt paths."""

    def __init__(self, app: ASGIApp, limit: str) -> None:
        super().__init__(app)
        count, period = parse_limit(limit)
        self.expression = limit
        self.counter = FixedWindowCounter(count, period)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        allowed, remaining, reset_after = self.counter.check(client_key(request))

        if not allowed:
            response: Response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=error_payload(
                    code=ErrorCode.RATE_LIMITED,
                    message="Rate limit exceeded. Slow down and retry shortly.",
                    details={"limit": self.expression, "retry_after_seconds": reset_after},
                ),
            )
            response.headers["Retry-After"] = str(reset_after)
        else:
            response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(self.counter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_after)
        return response


def register_rate_limiting(app: FastAPI) -> None:
    """Install the limiter when it is switched on."""
    if not settings.RATE_LIMIT_ENABLED:
        return
    app.add_middleware(RateLimitMiddleware, limit=settings.RATE_LIMIT_DEFAULT)
