"""Application exceptions and the handlers that turn them into responses.

Every failure leaves the API in the same envelope shape as a success, with an
``error`` object carrying a stable machine-readable ``code``. Clients can branch
on the code without parsing prose.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.context import get_request_id, get_warnings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ErrorCode(StrEnum):
    """Stable error identifiers returned in ``error.code``."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_SEQUENCE = "INVALID_SEQUENCE"
    INVALID_FASTA = "INVALID_FASTA"
    INVALID_FASTQ = "INVALID_FASTQ"
    PARSE_ERROR = "PARSE_ERROR"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    UNSUPPORTED_CONVERSION = "UNSUPPORTED_CONVERSION"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class BioAPIError(Exception):
    """Base class for every error the application raises deliberately."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: ErrorCode = ErrorCode.VALIDATION_ERROR

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details or {}
        self.warnings = warnings or []


class SequenceValidationError(BioAPIError):
    """A submitted sequence contains characters outside its alphabet."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = ErrorCode.INVALID_SEQUENCE


class ParseError(BioAPIError):
    """An uploaded or submitted document could not be parsed."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = ErrorCode.PARSE_ERROR


class FastaParseError(ParseError):
    code = ErrorCode.INVALID_FASTA


class FastqParseError(ParseError):
    code = ErrorCode.INVALID_FASTQ


class UnsupportedFormatError(BioAPIError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = ErrorCode.UNSUPPORTED_FORMAT


class UnsupportedConversionError(BioAPIError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = ErrorCode.UNSUPPORTED_CONVERSION


class PayloadTooLargeError(BioAPIError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = ErrorCode.PAYLOAD_TOO_LARGE


class AuthenticationError(BioAPIError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = ErrorCode.UNAUTHORIZED


class AuthorizationError(BioAPIError):
    status_code = status.HTTP_403_FORBIDDEN
    code = ErrorCode.FORBIDDEN


# Kept so integrations written against v1 keep importing successfully.
BioFastAPIError = BioAPIError


def error_payload(
    *,
    code: ErrorCode | str,
    message: str,
    details: dict[str, Any] | None = None,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build the JSON body shared by every error response."""
    warnings = get_warnings()
    for warning in extra_warnings or []:
        if warning not in warnings:
            warnings.append(warning)
    return {
        "success": False,
        "message": message,
        "data": None,
        "error": {
            "code": str(code),
            "message": message,
            "details": details or {},
        },
        "warnings": warnings,
        "request_id": get_request_id(),
    }


async def bioapi_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Render a deliberate application error."""
    assert isinstance(exc, BioAPIError)
    logger.info(
        "request.rejected",
        error_code=str(exc.code),
        status_code=exc.status_code,
        reason=exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            extra_warnings=exc.warnings,
        ),
    )


_HTTP_STATUS_TO_CODE = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_413_CONTENT_TOO_LARGE: ErrorCode.PAYLOAD_TOO_LARGE,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
}


async def http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Render Starlette/FastAPI HTTP exceptions in the standard envelope."""
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.VALIDATION_ERROR)
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        code = ErrorCode.INTERNAL_ERROR
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(code=code, message=str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Render request-body/query validation failures.

    Pydantic v2 error dicts can hold non-serialisable ``ctx`` values, so the
    payload is normalised to plain strings before it reaches the encoder.
    """
    assert isinstance(exc, RequestValidationError)
    issues = [
        {
            "location": [str(part) for part in issue.get("loc", ())],
            "message": str(issue.get("msg", "")),
            "type": str(issue.get("type", "")),
        }
        for issue in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error_payload(
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            details={"issues": issues},
        ),
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Last line of defence: log with a traceback, never leak internals."""
    logger.exception("request.unhandled_exception", error_type=type(exc).__name__)
    details = {"exception": f"{type(exc).__name__}: {exc}"} if settings.expose_error_details else {}
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload(
            code=ErrorCode.INTERNAL_ERROR,
            message="An internal error occurred while processing the request.",
            details=details,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler to ``app``."""
    app.add_exception_handler(BioAPIError, bioapi_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
