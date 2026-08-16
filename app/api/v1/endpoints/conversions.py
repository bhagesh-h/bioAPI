"""Format conversion and consensus generation."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response

from app.api.deps import UploadLimit
from app.schemas.common import ERROR_RESPONSES
from app.schemas.conversion import SourceFormat, TargetFormat
from app.services.conversion_service import ConversionService
from app.utils.tempfiles import spool_upload, temporary_paths

router = APIRouter(prefix="/conversions", tags=["Conversions"], responses=ERROR_RESPONSES)

_MEDIA_TYPES: dict[TargetFormat, str] = {
    TargetFormat.json: "application/json",
    TargetFormat.tab: "text/tab-separated-values",
}


@router.post(
    "/convert",
    summary="Convert a sequence file between formats",
    description=(
        "Convert an uploaded file. Only the pairs listed by GET /api/v1/formats are "
        "accepted; anything else is rejected before the file is read, with an "
        "explanation of why. Conversion metadata is returned in the X-Conversion-* "
        "headers and any information loss in X-Conversion-Warnings."
    ),
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "The converted file."},
        **ERROR_RESPONSES,
    },
)
async def convert(
    max_bytes: UploadLimit,
    source_format: Annotated[SourceFormat, Query(description="Format of the uploaded file.")],
    target_format: Annotated[TargetFormat, Query(description="Format to produce.")],
    file: Annotated[UploadFile, File(description="The file to convert.")],
) -> Response:
    # Reject an impossible pair before spending any I/O on the upload.
    ConversionService.validate_pair(source_format, target_format)

    with temporary_paths(f".{source_format.value}", f".{target_format.value}") as (
        source_path,
        output_path,
    ):
        await spool_upload(file, source_path, max_bytes)
        result = ConversionService.convert(source_path, output_path, source_format, target_format)
        payload = output_path.read_bytes()

    return Response(
        content=payload,
        media_type=_MEDIA_TYPES.get(target_format, "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "X-Conversion-Source": result.source_format.value,
            "X-Conversion-Target": result.target_format.value,
            "X-Records-Converted": str(result.records_converted),
            "X-Conversion-Warnings": str(len(result.warnings)),
        },
    )


@router.post(
    "/vcf-to-fasta",
    summary="Build a consensus FASTA from a reference and a VCF",
    description=(
        "Apply the first ALT allele of every VCF record to the matching reference "
        "sequence. Variants are applied from the end of each sequence backwards so "
        "indels cannot shift the coordinates of those still to be applied. Variants "
        "whose REF does not match the reference are skipped and counted in the "
        "X-Variants-Skipped header rather than being applied blindly."
    ),
    responses={
        200: {"content": {"text/plain": {}}, "description": "The consensus FASTA."},
        **ERROR_RESPONSES,
    },
)
async def vcf_to_fasta(
    max_bytes: UploadLimit,
    reference_fasta: Annotated[UploadFile, File(description="Reference FASTA.")],
    vcf_file: Annotated[UploadFile, File(description="VCF with the variants to apply.")],
) -> Response:
    with temporary_paths(".fasta", ".vcf", ".consensus.fasta") as (
        fasta_path,
        vcf_path,
        output_path,
    ):
        await spool_upload(reference_fasta, fasta_path, max_bytes)
        await spool_upload(vcf_file, vcf_path, max_bytes)
        result = ConversionService.derive_consensus(fasta_path, vcf_path, output_path)
        payload = output_path.read_bytes()

    return Response(
        content=payload,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="consensus.fasta"',
            "X-Records-Converted": str(result.records_written),
            "X-Variants-Applied": str(result.variants_applied),
            "X-Variants-Skipped": str(result.variants_skipped),
        },
    )
