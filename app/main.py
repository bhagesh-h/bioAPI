"""Application factory and ASGI entry point."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import register_middleware
from app.core.rate_limit import register_rate_limiting

configure_logging()
logger = get_logger(__name__)

TAGS_METADATA = [
    {"name": "Health", "description": "Liveness, readiness and build metadata."},
    {"name": "Sequences", "description": "Operations on a single sequence supplied as JSON."},
    {
        "name": "FASTA Utilities",
        "description": "Filter, slice, sample, split, merge and rename FASTA records in memory.",
    },
    {
        "name": "FASTQ Utilities",
        "description": "Quality filtering, summary statistics and gzip round-tripping.",
    },
    {
        "name": "Files",
        "description": "Upload FASTA, FASTQ, GenBank, EMBL, SAM/BAM, VCF, GFF or GTF for analysis.",
    },
    {
        "name": "Conversions",
        "description": "Convert between formats and build consensus sequences from a VCF.",
    },
    {"name": "Formats", "description": "What this deployment can parse and convert."},
]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Log the service coming up and going down."""
    logger.info(
        "service.startup",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        docs_enabled=settings.DOCS_ENABLED,
        rate_limit=settings.RATE_LIMIT_DEFAULT if settings.RATE_LIMIT_ENABLED else "disabled",
        api_key_required=bool(settings.API_KEY),
    )
    yield
    logger.info("service.shutdown")


def create_app() -> FastAPI:
    """Build and wire the FastAPI application.

    Exposed as a factory so tests can construct an isolated instance with
    different settings instead of importing a module-level singleton.
    """
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            f"{settings.DESCRIPTION}\n\n"
            "Every JSON endpoint returns the same envelope: `success`, `message`, `data`, "
            "`error`, `warnings` and `request_id`. Errors carry a stable `error.code` you "
            "can branch on. Endpoints that produce a file return it directly with the "
            "relevant metadata in `X-` headers."
        ),
        openapi_tags=TAGS_METADATA,
        openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DOCS_ENABLED else None,
        docs_url="/docs" if settings.DOCS_ENABLED else None,
        redoc_url="/redoc" if settings.DOCS_ENABLED else None,
        lifespan=lifespan,
        contact={"name": "bioAPI", "url": "https://github.com/bhagesh-h/bioAPI"},
        license_info={
            "name": "GPL-3.0-only",
            "url": "https://www.gnu.org/licenses/gpl-3.0.html",
        },
    )

    register_exception_handlers(application)
    register_rate_limiting(application)
    register_middleware(application)

    application.include_router(health_router)
    application.include_router(api_router, prefix=settings.API_V1_STR)

    if settings.METRICS_ENABLED:
        _install_metrics(application)

    return application


def _install_metrics(application: FastAPI) -> None:
    """Expose Prometheus metrics at /metrics.

    Import is local so a deployment that disables metrics does not pay for the
    instrumentator at start-up.
    """
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/metrics", "/health", "/health/live", "/health/ready"],
    ).instrument(application).expose(application, endpoint="/metrics", include_in_schema=False)


app = create_app()
