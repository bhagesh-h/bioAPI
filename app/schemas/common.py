"""The response envelope shared by every JSON endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.context import get_request_id, get_warnings


class ErrorDetail(BaseModel):
    """Machine-readable description of a failure."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "INVALID_SEQUENCE",
                "message": "Sequence contains characters outside the dna alphabet: Z",
                "details": {"invalid_characters": ["Z"]},
            }
        }
    )

    code: str = Field(description="Stable error identifier, safe to branch on in client code.")
    message: str = Field(description="Human-readable explanation of what went wrong.")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Structured context for the error."
    )


class EnvelopeResponse[T](BaseModel):
    """Uniform wrapper around every successful and failed response.

    ``warnings`` and ``request_id`` are filled in from the per-request context,
    so a handler only ever has to supply the payload.
    """

    success: bool = Field(description="True when the operation completed.")
    message: str | None = Field(default=None, description="Optional human-readable note.")
    data: T | None = Field(default=None, description="The result payload.")
    error: ErrorDetail | None = Field(default=None, description="Set only when success is false.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal notes about the result, such as ambiguity codes being present.",
    )
    request_id: str | None = Field(
        default=None, description="Correlation id, also returned in the X-Request-ID header."
    )

    @classmethod
    def ok(cls, data: T, message: str | None = None) -> EnvelopeResponse[T]:
        """Build a success envelope, pulling warnings and the request id from context."""
        return cls(
            success=True,
            message=message,
            data=data,
            warnings=get_warnings(),
            request_id=get_request_id(),
        )


class ErrorEnvelope(BaseModel):
    """The failure shape, declared so it appears in the OpenAPI document."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "Request validation failed.",
                "data": None,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "details": {},
                },
                "warnings": [],
                "request_id": "0f7c0a6e-2c5b-4a8e-9d0f-6f7a1b2c3d4e",
            }
        }
    )

    success: bool = False
    message: str
    data: None = None
    error: ErrorDetail
    warnings: list[str] = Field(default_factory=list)
    request_id: str | None = None


#: Reusable ``responses=`` fragment so every route documents its error shape.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorEnvelope, "description": "The request was rejected as invalid."},
    401: {"model": ErrorEnvelope, "description": "The API key header is missing."},
    403: {"model": ErrorEnvelope, "description": "The supplied API key was rejected."},
    413: {"model": ErrorEnvelope, "description": "The payload exceeds the configured limit."},
    422: {"model": ErrorEnvelope, "description": "The document could not be parsed."},
    429: {"model": ErrorEnvelope, "description": "The rate limit has been exceeded."},
    500: {"model": ErrorEnvelope, "description": "An unexpected internal error occurred."},
}
