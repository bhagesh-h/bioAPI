"""Self-describing capability endpoint."""

from fastapi import APIRouter

from app.schemas.common import ERROR_RESPONSES, EnvelopeResponse
from app.schemas.conversion import FormatCapabilities
from app.services.conversion_service import ConversionService

router = APIRouter(prefix="/formats", tags=["Formats"], responses=ERROR_RESPONSES)


@router.get(
    "",
    response_model=EnvelopeResponse[FormatCapabilities],
    summary="List supported formats and conversions",
    description=(
        "Report which formats this deployment can analyse, which conversions are "
        "available, and why the remaining pairs are not. Clients can use this instead "
        "of hard-coding the matrix."
    ),
)
async def capabilities() -> EnvelopeResponse[FormatCapabilities]:
    return EnvelopeResponse.ok(ConversionService.capabilities())
