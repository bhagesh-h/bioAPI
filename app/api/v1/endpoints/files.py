"""File-upload analysis and cross-file extraction."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import PlainTextResponse

from app.api.deps import UploadLimit
from app.schemas.common import ERROR_RESPONSES, EnvelopeResponse
from app.schemas.file_stats import FileStatsResponse, VariantExtractionResult
from app.services.file_service import FileService
from app.utils.detection import FileFormat
from app.utils.tempfiles import spool_upload, temporary_path, temporary_paths

router = APIRouter(prefix="/files", tags=["Files"], responses=ERROR_RESPONSES)

_LINE_COUNTED = frozenset(
    {
        FileFormat.vcf,
        FileFormat.gff,
        FileFormat.gtf,
        FileFormat.sam,
        FileFormat.text,
        FileFormat.unknown,
    }
)


async def _analyse_upload(upload: UploadFile, max_bytes: int) -> FileStatsResponse:
    """Stream the upload to disk, detect its format and gather statistics."""
    filename = upload.filename or "upload"
    with temporary_path(suffix=f"-{filename}") as path:
        size = await spool_upload(upload, path, max_bytes)
        detection = FileService.detect(path, filename)
        fragments = FileService.analyse(path, detection)
        lines = (
            FileService.count_lines(path) if detection.detected_format in _LINE_COUNTED else None
        )

    return FileStatsResponse(
        filename=filename,
        content_type=upload.content_type or "application/octet-stream",
        size_bytes=size,
        lines=lines,
        format=detection,
        sequence_stats=fragments.get("sequence_stats"),
        quality_stats=fragments.get("quality_stats"),
        bam_stats=fragments.get("bam_stats"),
        gff_stats=fragments.get("gff_stats"),
        vcf_stats=fragments.get("vcf_stats"),
        preview_ids=fragments.get("preview_ids", []),
    )


@router.post(
    "/stats",
    response_model=EnvelopeResponse[FileStatsResponse],
    summary="Analyse an uploaded file",
    description=(
        "Detect the format from the file's content — not just its extension — and return "
        "the statistics that apply to it: sequence composition for FASTA/FASTQ/GenBank/EMBL, "
        "alignment counts for SAM/BAM, feature counts for GFF/GTF, variant counts for VCF."
    ),
)
async def stats(
    max_bytes: UploadLimit,
    file: Annotated[UploadFile, File(description="The file to analyse.")],
) -> EnvelopeResponse[FileStatsResponse]:
    return EnvelopeResponse.ok(await _analyse_upload(file, max_bytes))


@router.post(
    "/summary",
    response_model=EnvelopeResponse[FileStatsResponse],
    summary="Analyse an uploaded file (alias of /stats)",
    description="Kept for backwards compatibility; behaves identically to POST /files/stats.",
    deprecated=True,
)
async def summary(
    max_bytes: UploadLimit,
    file: Annotated[UploadFile, File(description="The file to analyse.")],
) -> EnvelopeResponse[FileStatsResponse]:
    return EnvelopeResponse.ok(await _analyse_upload(file, max_bytes))


@router.post(
    "/extract-gff",
    response_class=PlainTextResponse,
    summary="Extract feature sequences using GFF coordinates",
    description=(
        "Overlay a GFF or GTF annotation on a reference FASTA and return the sliced "
        "features as FASTA. Minus-strand features are reverse-complemented. Counts of "
        "extracted and skipped features are returned in the X-Features-* headers."
    ),
    responses={
        200: {"content": {"text/plain": {}}, "description": "FASTA of the extracted features."},
        **ERROR_RESPONSES,
    },
)
async def extract_gff(
    max_bytes: UploadLimit,
    fasta_file: Annotated[UploadFile, File(description="Reference FASTA.")],
    gff_file: Annotated[UploadFile, File(description="GFF or GTF annotation.")],
    feature_type: Annotated[
        str | None, Form(description="Only extract this feature type, e.g. gene or CDS.")
    ] = None,
) -> PlainTextResponse:
    with temporary_paths(".fasta", ".gff") as (fasta_path, gff_path):
        await spool_upload(fasta_file, fasta_path, max_bytes)
        await spool_upload(gff_file, gff_path, max_bytes)
        document, extraction = FileService.extract_gff_features(fasta_path, gff_path, feature_type)

    return PlainTextResponse(
        content=document,
        headers={
            "Content-Disposition": 'attachment; filename="extracted_features.fasta"',
            "X-Features-Extracted": str(extraction.features_extracted),
            "X-Features-Skipped": str(extraction.features_skipped),
        },
    )


@router.post(
    "/vcf/extract",
    response_model=EnvelopeResponse[VariantExtractionResult],
    summary="Extract variants from a VCF",
    description="List the variants of a given class. Use ALL, SNP, INDEL, MNP or OTHER.",
)
async def extract_variants(
    max_bytes: UploadLimit,
    vcf_file: Annotated[UploadFile, File(description="The VCF to read.")],
    variant_type: Annotated[
        str, Form(description="Variant class to return: ALL, SNP, INDEL, MNP or OTHER.")
    ] = "ALL",
) -> EnvelopeResponse[VariantExtractionResult]:
    with temporary_path(".vcf") as vcf_path:
        await spool_upload(vcf_file, vcf_path, max_bytes)
        result = FileService.extract_variants(vcf_path, variant_type)
    return EnvelopeResponse.ok(result)
