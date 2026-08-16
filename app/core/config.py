"""Application settings, sourced from environment variables or a local .env file."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import __version__

Environment = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    """Runtime configuration.

    Every value has a working default so the container starts with no .env at
    all; production deployments override what they need through the environment.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "bioAPI"
    VERSION: str = __version__
    DESCRIPTION: str = "A production-grade REST API for common bioinformatics workflows."
    ENVIRONMENT: Environment = "development"
    DEBUG: bool = False

    # ── HTTP ─────────────────────────────────────────────────────────────────
    API_V1_STR: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DOCS_ENABLED: bool = True

    # CORS origins accept either a comma-separated list or a JSON array.
    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    # ── Security ─────────────────────────────────────────────────────────────
    # When unset the API is open; when set, every /api/v1 route requires X-API-Key.
    API_KEY: str | None = None
    SECURITY_HEADERS_ENABLED: bool = True

    # ── Limits ───────────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = Field(default=50, ge=1, le=2048)
    MAX_SEQUENCE_LENGTH: int = Field(
        default=10_000_000,
        ge=1,
        description="Upper bound on a single sequence submitted as JSON.",
    )

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: str = "120/minute"

    # ── Observability ────────────────────────────────────────────────────────
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"
    METRICS_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept ``a,b``, ``["a","b"]`` or a real list for CORS origins.

        ``NoDecode`` switches off pydantic-settings' automatic JSON decoding so
        a bare ``*`` does not blow up before this validator ever runs.
        """
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                import json

                decoded = json.loads(raw)
                return [str(item).strip() for item in decoded]
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_upload_size_bytes(self) -> int:
        """Upload ceiling in bytes, enforced by the body-size middleware."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def expose_error_details(self) -> bool:
        """Whether unhandled-exception text may be returned to the client."""
        return self.DEBUG and not self.is_production


settings = Settings()
