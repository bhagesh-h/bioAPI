"""Liveness, readiness and service metadata.

These live at the application root rather than under ``/api/v1`` so an
orchestrator's probes never need an API key and never move between versions.
"""

from __future__ import annotations

import platform
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.schemas.common import EnvelopeResponse
from app.schemas.health import (
    DependencyCheck,
    LivenessStatus,
    ReadinessStatus,
    ServiceInfo,
    VersionInfo,
)

router = APIRouter(tags=["Health"])


def _installed_version(distribution: str) -> str:
    """Look a dependency's version up from package metadata.

    Reading metadata rather than a ``__version__`` attribute keeps this working
    for packages that do not re-export one.
    """
    try:
        return installed_version(distribution)
    except PackageNotFoundError:  # pragma: no cover — the image always installs both
        return "unknown"


def _probe_biopython() -> DependencyCheck:
    """Parse a tiny FASTA record to prove Biopython works, not just imports."""
    try:
        from io import StringIO

        from Bio import SeqIO

        records = list(SeqIO.parse(StringIO(">probe\nACGT\n"), "fasta"))
        healthy = len(records) == 1 and str(records[0].seq) == "ACGT"
        return DependencyCheck(
            name="biopython",
            healthy=healthy,
            detail=None if healthy else "the FASTA probe returned unexpected output",
        )
    except Exception as exc:
        return DependencyCheck(name="biopython", healthy=False, detail=str(exc))


def _probe_pysam() -> DependencyCheck:
    """Confirm the pysam C extension loaded; a broken htslib fails here."""
    try:
        import pysam

        # Touching AlignmentFile proves the compiled extension imported, not
        # merely that the Python package is on the path.
        return DependencyCheck(name="pysam", healthy=pysam.AlignmentFile is not None, detail=None)
    except Exception as exc:
        return DependencyCheck(name="pysam", healthy=False, detail=str(exc))


@router.get(
    "/",
    response_model=EnvelopeResponse[ServiceInfo],
    summary="Service information",
    description="Name, version and where to find the documentation.",
)
async def root() -> EnvelopeResponse[ServiceInfo]:
    return EnvelopeResponse.ok(
        ServiceInfo(
            name=settings.PROJECT_NAME,
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
            docs_url="/docs" if settings.DOCS_ENABLED else None,
            redoc_url="/redoc" if settings.DOCS_ENABLED else None,
            openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DOCS_ENABLED else None,
        ),
        message=f"Welcome to {settings.PROJECT_NAME}",
    )


@router.get(
    "/health",
    response_model=EnvelopeResponse[LivenessStatus],
    summary="Liveness probe",
    description="Returns 200 as long as the process can serve requests.",
)
async def health() -> EnvelopeResponse[LivenessStatus]:
    return EnvelopeResponse.ok(LivenessStatus())


@router.get(
    "/health/live",
    response_model=EnvelopeResponse[LivenessStatus],
    summary="Liveness probe",
    description="Kubernetes-style liveness path. Identical to GET /health.",
)
async def liveness() -> EnvelopeResponse[LivenessStatus]:
    return EnvelopeResponse.ok(LivenessStatus())


@router.get(
    "/health/ready",
    response_model=EnvelopeResponse[ReadinessStatus],
    summary="Readiness probe",
    description=(
        "Exercise the parsing libraries the API depends on. Returns 503 when a "
        "dependency is unusable, so a broken image is taken out of the load balancer "
        "instead of failing real requests."
    ),
)
async def readiness(response: Response) -> EnvelopeResponse[ReadinessStatus]:
    checks = [_probe_biopython(), _probe_pysam()]
    healthy = all(check.healthy for check in checks)
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return EnvelopeResponse.ok(
        ReadinessStatus(status="ready" if healthy else "degraded", checks=checks)
    )


@router.get(
    "/ready",
    response_model=EnvelopeResponse[ReadinessStatus],
    summary="Readiness probe (alias)",
    description="Kept for backwards compatibility; behaves identically to /health/ready.",
    deprecated=True,
)
async def readiness_alias(response: Response) -> EnvelopeResponse[ReadinessStatus]:
    return await readiness(response)


@router.get(
    "/version",
    response_model=EnvelopeResponse[VersionInfo],
    summary="Build and runtime versions",
    description="Application version plus the versions of the libraries doing the work.",
)
async def version() -> EnvelopeResponse[VersionInfo]:
    return EnvelopeResponse.ok(
        VersionInfo(
            name=settings.PROJECT_NAME,
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
            python_version=platform.python_version(),
            biopython_version=_installed_version("biopython"),
            pysam_version=_installed_version("pysam"),
        )
    )
