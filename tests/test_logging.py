"""Log output shape.

A misconfigured structlog/stdlib bridge renders each record twice and buries the
real fields inside a stringified copy. These tests pin the emitted line down to
a single flat JSON object.
"""

from __future__ import annotations

import json
import logging
from io import StringIO

import pytest

from app.core.config import settings
from app.core.context import RequestContext
from app.core.logging import configure_logging, get_logger


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> StringIO:
    """Reconfigure logging onto an in-memory stream for one test."""
    monkeypatch.setattr(settings, "LOG_FORMAT", "json")
    monkeypatch.setattr(settings, "LOG_LEVEL", "INFO")
    configure_logging()

    buffer = StringIO()
    handler = logging.getLogger().handlers[0]
    monkeypatch.setattr(handler, "stream", buffer)
    return buffer


def _last_record(buffer: StringIO) -> dict[str, object]:
    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    assert lines, "nothing was logged"
    return json.loads(lines[-1])


def test_event_is_a_flat_json_object(captured_logs: StringIO) -> None:
    get_logger("test").info("thing.happened", widget="sprocket")
    record = _last_record(captured_logs)

    assert record["event"] == "thing.happened"
    assert record["widget"] == "sprocket"
    assert record["level"] == "info"


def test_event_is_not_double_encoded(captured_logs: StringIO) -> None:
    """The event field must be the message, never a nested JSON document."""
    get_logger("test").info("thing.happened")
    event = _last_record(captured_logs)["event"]

    assert isinstance(event, str)
    with pytest.raises(json.JSONDecodeError):
        json.loads(str(event))


def test_service_metadata_is_attached(captured_logs: StringIO) -> None:
    get_logger("test").info("thing.happened")
    record = _last_record(captured_logs)

    assert record["service"] == settings.PROJECT_NAME
    assert record["version"] == settings.VERSION
    assert record["logger"] == "test"
    assert str(record["timestamp"]).endswith("Z")


def test_request_id_is_attached_inside_a_request_scope(captured_logs: StringIO) -> None:
    with RequestContext("req-42"):
        get_logger("test").info("inside.request")
    assert _last_record(captured_logs)["request_id"] == "req-42"


def test_records_from_the_standard_library_get_the_same_shape(captured_logs: StringIO) -> None:
    logging.getLogger("third.party").warning("a plain stdlib message")
    record = _last_record(captured_logs)

    assert record["event"] == "a plain stdlib message"
    assert record["level"] == "warning"
    assert record["service"] == settings.PROJECT_NAME


def test_exceptions_are_rendered_into_the_record(captured_logs: StringIO) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        get_logger("test").exception("it.broke")

    record = _last_record(captured_logs)
    assert record["event"] == "it.broke"
    assert "ValueError: boom" in str(record["exception"])


def test_console_format_is_selectable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LOG_FORMAT", "console")
    monkeypatch.setattr(settings, "LOG_LEVEL", "INFO")
    configure_logging()

    buffer = StringIO()
    handler = logging.getLogger().handlers[0]
    monkeypatch.setattr(handler, "stream", buffer)

    get_logger("test").info("human.readable")
    output = buffer.getvalue()

    assert "human.readable" in output
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)
