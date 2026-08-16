"""FASTQ string utilities. Every endpoint takes and returns inline documents."""

from fastapi import APIRouter

from app.schemas.common import ERROR_RESPONSES, EnvelopeResponse
from app.schemas.fasta import FastaResult
from app.schemas.fastq import (
    FastqRequest,
    FastqResult,
    FastqStatsResult,
    FastqToFastaRequest,
    GzDecompressRequest,
    GzResult,
    QualityFilterRequest,
)
from app.services.fastq_service import FastqService

router = APIRouter(prefix="/fastq", tags=["FASTQ Utilities"], responses=ERROR_RESPONSES)


@router.post(
    "/stats",
    response_model=EnvelopeResponse[FastqStatsResult],
    summary="Summarise a FASTQ document",
    description="Read counts, length distribution, GC content and Q20/Q30 quality figures.",
)
async def stats(request: FastqRequest) -> EnvelopeResponse[FastqStatsResult]:
    return EnvelopeResponse.ok(FastqService.stats(request))


@router.post(
    "/quality-filter",
    response_model=EnvelopeResponse[FastqResult],
    summary="Filter reads by quality and length",
    description=(
        "Discard reads whose mean Phred score is below `min_quality` or that are shorter "
        "than `min_length`. Set `quality_offset` to 64 for legacy Illumina encodings."
    ),
)
async def quality_filter(request: QualityFilterRequest) -> EnvelopeResponse[FastqResult]:
    return EnvelopeResponse.ok(FastqService.quality_filter(request))


@router.post(
    "/to-fasta",
    response_model=EnvelopeResponse[FastaResult],
    summary="Convert FASTQ to FASTA",
    description="Drop the quality track and return the reads as a FASTA document.",
)
async def to_fasta(request: FastqToFastaRequest) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastqService.to_fasta(request))


@router.post(
    "/compress-gz",
    response_model=EnvelopeResponse[GzResult],
    summary="Gzip-compress a FASTQ document",
    description=(
        "Compress the document and return it base64-encoded so it survives JSON transport. "
        "Feed `data_base64` straight back into POST /api/v1/fastq/decompress-gz."
    ),
)
async def compress_gz(request: FastqRequest) -> EnvelopeResponse[GzResult]:
    return EnvelopeResponse.ok(FastqService.compress_gz(request))


@router.post(
    "/decompress-gz",
    response_model=EnvelopeResponse[FastqResult],
    summary="Decompress a gzipped FASTQ document",
    description="Decode base64, gunzip, and validate that the result is well-formed FASTQ.",
)
async def decompress_gz(request: GzDecompressRequest) -> EnvelopeResponse[FastqResult]:
    return EnvelopeResponse.ok(FastqService.decompress_gz(request))
