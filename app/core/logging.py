"""Structured logging.

Logs are emitted as one JSON object per line so a log aggregator can index the
fields directly; a developer can switch to a human-readable renderer with
``LOG_FORMAT=console``.

structlog and the standard library share a single pipeline. structlog's chain
ends at ``wrap_for_formatter``, which hands the event dictionary — not a
rendered string — to a ``ProcessorFormatter`` attached to the stdlib handler.
That formatter owns the only renderer in the system. Ending structlog's own
chain with a renderer as well would serialise each record twice and nest the
whole JSON document inside the next one's ``event`` field.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.config import settings
from app.core.context import get_request_id


def _add_request_id(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Stamp every record with the current request id when one is in scope."""
    request_id = get_request_id()
    if request_id is not None:
        event_dict.setdefault("request_id", request_id)
    return event_dict


def _add_service_metadata(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    event_dict.setdefault("service", settings.PROJECT_NAME)
    event_dict.setdefault("version", settings.VERSION)
    event_dict.setdefault("environment", settings.ENVIRONMENT)
    return event_dict


def _shared_processors() -> list[structlog.typing.Processor]:
    """Processors applied to structlog and stdlib records alike."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_request_id,
        _add_service_metadata,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]


def _renderer() -> structlog.typing.Processor:
    if settings.LOG_FORMAT == "json":
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=False)


def configure_logging() -> None:
    """Install the logging pipeline. Safe to call more than once."""
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    shared = _shared_processors()

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            # Hands the event dict to the stdlib formatter, which renders it.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            # Records from libraries that log through the stdlib get the same
            # fields as our own before they reach the renderer.
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                _renderer(),
            ],
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    # Access logging is produced by our middleware with richer fields.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for ``name``."""
    return structlog.stdlib.get_logger(name)
