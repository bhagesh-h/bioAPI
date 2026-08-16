"""Health, readiness and service-metadata payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ServiceInfo(BaseModel):
    """What the root endpoint reports about the running service."""

    name: str
    version: str
    environment: str
    docs_url: str | None = Field(description="Swagger UI path, null when docs are disabled.")
    redoc_url: str | None = Field(description="ReDoc path, null when docs are disabled.")
    openapi_url: str | None = Field(description="Raw OpenAPI document path.")


class LivenessStatus(BaseModel):
    """Answer to 'is the process alive'."""

    status: Literal["alive"] = "alive"


class DependencyCheck(BaseModel):
    """Result of probing one thing the service needs in order to do its job."""

    name: str
    healthy: bool
    detail: str | None = None


class ReadinessStatus(BaseModel):
    """Answer to 'can this instance serve traffic'.

    Unlike the previous stub, this actually exercises the parsing libraries the
    API depends on, so a broken pysam build fails the probe instead of quietly
    500-ing on the first real request.
    """

    status: Literal["ready", "degraded"]
    checks: list[DependencyCheck]


class VersionInfo(BaseModel):
    """Build and runtime metadata."""

    name: str
    version: str
    environment: str
    python_version: str
    biopython_version: str
    pysam_version: str
