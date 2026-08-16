"""Root, health, readiness, version and metrics endpoints."""

from __future__ import annotations

from httpx import AsyncClient

from app import __version__


async def test_root_reports_service_metadata(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200

    body = response.json()
    assert body["success"] is True
    assert "bioAPI" in body["message"]
    assert body["data"]["version"] == __version__
    assert body["data"]["docs_url"] == "/docs"


async def test_health_is_alive(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"


async def test_liveness_alias(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"


async def test_readiness_probes_real_dependencies(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["status"] == "ready"
    probed = {check["name"]: check["healthy"] for check in data["checks"]}
    assert probed == {"biopython": True, "pysam": True}


async def test_legacy_ready_alias_still_works(client: AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ready"


async def test_version_reports_library_versions(client: AsyncClient) -> None:
    response = await client.get("/version")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["version"] == __version__
    assert data["python_version"].startswith("3.")
    assert data["biopython_version"]
    assert data["pysam_version"]


async def test_every_response_carries_a_request_id(client: AsyncClient) -> None:
    response = await client.get("/health")
    request_id = response.headers["x-request-id"]
    assert request_id
    assert response.json()["request_id"] == request_id
    assert "x-process-time" in response.headers


async def test_inbound_request_id_is_honoured(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "trace-me-123"})
    assert response.headers["x-request-id"] == "trace-me-123"
    assert response.json()["request_id"] == "trace-me-123"


async def test_security_headers_are_present(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


async def test_unknown_path_returns_the_standard_envelope(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")
    assert response.status_code == 404

    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["request_id"]


async def test_openapi_document_is_served(client: AsyncClient) -> None:
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200

    document = response.json()
    assert document["info"]["title"] == "bioAPI"
    assert "ApiKeyAuth" in document["components"]["securitySchemes"]
