"""API key enforcement and rate limiting."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.rate_limit import FixedWindowCounter, client_key, parse_limit
from app.main import create_app

SEQUENCE_ENDPOINT = "/api/v1/sequences/reverse"
PAYLOAD = {"sequence": "ACGT"}


# ── API key ───────────────────────────────────────────────────────────────────


async def test_api_is_open_when_no_key_is_configured(client: AsyncClient) -> None:
    response = await client.post(SEQUENCE_ENDPOINT, json=PAYLOAD)
    assert response.status_code == 200


async def test_missing_key_is_401(client: AsyncClient, api_key_required: str) -> None:
    response = await client.post(SEQUENCE_ENDPOINT, json=PAYLOAD)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_wrong_key_is_403(client: AsyncClient, api_key_required: str) -> None:
    response = await client.post(
        SEQUENCE_ENDPOINT, json=PAYLOAD, headers={"X-API-Key": "not-the-key"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_correct_key_is_accepted(client: AsyncClient, api_key_required: str) -> None:
    response = await client.post(
        SEQUENCE_ENDPOINT, json=PAYLOAD, headers={"X-API-Key": api_key_required}
    )
    assert response.status_code == 200


async def test_health_stays_open_when_a_key_is_configured(
    client: AsyncClient, api_key_required: str
) -> None:
    """Orchestrator probes must never need credentials."""
    for path in ("/health", "/health/live", "/health/ready", "/"):
        response = await client.get(path)
        assert response.status_code == 200, path


# ── rate limit expression parsing ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("120/minute", (120, 60)),
        ("5/second", (5, 1)),
        ("1000/hour", (1000, 3600)),
        ("10/DAY", (10, 86400)),
        (" 30 / min ", (30, 60)),
    ],
)
def test_parse_limit(expression: str, expected: tuple[int, int]) -> None:
    assert parse_limit(expression) == expected


@pytest.mark.parametrize("expression", ["120", "abc/minute", "0/minute", "10/fortnight"])
def test_parse_limit_rejects_nonsense(expression: str) -> None:
    with pytest.raises(ValueError):
        parse_limit(expression)


def test_fixed_window_counter_allows_then_blocks() -> None:
    counter = FixedWindowCounter(limit=3, period_seconds=60)
    results = [counter.check("caller", now=1000.0) for _ in range(4)]

    assert [allowed for allowed, _, _ in results] == [True, True, True, False]
    assert [remaining for _, remaining, _ in results] == [2, 1, 0, 0]


def test_fixed_window_counter_resets_in_the_next_window() -> None:
    counter = FixedWindowCounter(limit=1, period_seconds=60)
    assert counter.check("caller", now=1000.0)[0] is True
    assert counter.check("caller", now=1000.0)[0] is False
    # 1060 lands in the following window.
    assert counter.check("caller", now=1080.0)[0] is True


def test_fixed_window_counter_keys_are_independent() -> None:
    counter = FixedWindowCounter(limit=1, period_seconds=60)
    assert counter.check("a", now=1000.0)[0] is True
    assert counter.check("b", now=1000.0)[0] is True


class _FakeRequest:
    def __init__(self, headers: dict[str, str], host: str | None = "10.0.0.1") -> None:
        self.headers = headers
        self.client = type("Client", (), {"host": host})() if host else None


def test_client_key_prefers_the_api_key() -> None:
    assert client_key(_FakeRequest({"x-api-key": "abc"})) == "key:abc"  # type: ignore[arg-type]


def test_client_key_falls_back_to_forwarded_address() -> None:
    request = _FakeRequest({"x-forwarded-for": "203.0.113.7, 10.0.0.1"})
    assert client_key(request) == "ip:203.0.113.7"  # type: ignore[arg-type]


def test_client_key_falls_back_to_the_peer_address() -> None:
    assert client_key(_FakeRequest({})) == "ip:10.0.0.1"  # type: ignore[arg-type]


# ── rate limiting end to end ──────────────────────────────────────────────────


@pytest.fixture
def rate_limited_app(monkeypatch: pytest.MonkeyPatch):
    """An application instance with a deliberately tiny limit."""

    def _build(limit: str):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
        monkeypatch.setattr(settings, "RATE_LIMIT_DEFAULT", limit)
        return create_app()

    return _build


async def test_exceeding_the_limit_returns_the_standard_429_envelope(rate_limited_app) -> None:
    transport = ASGITransport(app=rate_limited_app("3/minute"))

    async with AsyncClient(transport=transport, base_url="http://limited") as limited:
        responses = [await limited.post(SEQUENCE_ENDPOINT, json=PAYLOAD) for _ in range(5)]

    assert [response.status_code for response in responses] == [200, 200, 200, 429, 429]

    blocked = responses[-1]
    body = blocked.json()
    assert body["success"] is False
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["request_id"]
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["x-ratelimit-limit"] == "3"
    assert blocked.headers["x-ratelimit-remaining"] == "0"


async def test_allowed_requests_advertise_the_remaining_budget(rate_limited_app) -> None:
    transport = ASGITransport(app=rate_limited_app("10/minute"))

    async with AsyncClient(transport=transport, base_url="http://limited") as limited:
        first = await limited.post(SEQUENCE_ENDPOINT, json=PAYLOAD)
        second = await limited.post(SEQUENCE_ENDPOINT, json=PAYLOAD)

    assert first.headers["x-ratelimit-remaining"] == "9"
    assert second.headers["x-ratelimit-remaining"] == "8"


async def test_health_is_exempt_from_rate_limiting(rate_limited_app) -> None:
    transport = ASGITransport(app=rate_limited_app("2/minute"))

    async with AsyncClient(transport=transport, base_url="http://limited") as probes:
        statuses = [(await probes.get("/health")).status_code for _ in range(6)]

    assert set(statuses) == {200}


async def test_separate_api_keys_get_separate_budgets(rate_limited_app) -> None:
    transport = ASGITransport(app=rate_limited_app("1/minute"))

    async with AsyncClient(transport=transport, base_url="http://limited") as limited:
        first_tenant = await limited.post(
            SEQUENCE_ENDPOINT, json=PAYLOAD, headers={"X-API-Key": "tenant-a"}
        )
        second_tenant = await limited.post(
            SEQUENCE_ENDPOINT, json=PAYLOAD, headers={"X-API-Key": "tenant-b"}
        )
        repeat = await limited.post(
            SEQUENCE_ENDPOINT, json=PAYLOAD, headers={"X-API-Key": "tenant-a"}
        )

    assert first_tenant.status_code == 200
    assert second_tenant.status_code == 200
    assert repeat.status_code == 429
