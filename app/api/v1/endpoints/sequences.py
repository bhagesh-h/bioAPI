"""Single-sequence operations."""

from fastapi import APIRouter

from app.schemas.common import ERROR_RESPONSES, EnvelopeResponse
from app.schemas.sequence import (
    BaseCountResult,
    GCContentResult,
    KmerRequest,
    KmerResult,
    MotifRequest,
    MotifResult,
    SequenceRequest,
    SequenceResult,
    TranslationRequest,
    ValidationResult,
)
from app.services.sequence_service import SequenceService

router = APIRouter(prefix="/sequences", tags=["Sequences"], responses=ERROR_RESPONSES)


@router.post(
    "/reverse",
    response_model=EnvelopeResponse[SequenceResult],
    summary="Reverse a sequence",
    description="Return the sequence read back to front. This is not the reverse complement.",
)
async def reverse(request: SequenceRequest) -> EnvelopeResponse[SequenceResult]:
    return EnvelopeResponse.ok(SequenceService.reverse(request))


@router.post(
    "/complement",
    response_model=EnvelopeResponse[SequenceResult],
    summary="Complement a nucleotide sequence",
    description="Swap each base for its pair. RNA input is complemented as RNA.",
)
async def complement(request: SequenceRequest) -> EnvelopeResponse[SequenceResult]:
    return EnvelopeResponse.ok(SequenceService.complement(request))


@router.post(
    "/reverse-complement",
    response_model=EnvelopeResponse[SequenceResult],
    summary="Reverse-complement a nucleotide sequence",
    description="Complement the sequence and reverse it, giving the opposite strand 5'→3'.",
)
async def reverse_complement(request: SequenceRequest) -> EnvelopeResponse[SequenceResult]:
    return EnvelopeResponse.ok(SequenceService.reverse_complement(request))


@router.post(
    "/transcribe",
    response_model=EnvelopeResponse[SequenceResult],
    summary="Transcribe DNA to RNA",
    description="Replace every T with U.",
)
async def transcribe(request: SequenceRequest) -> EnvelopeResponse[SequenceResult]:
    return EnvelopeResponse.ok(SequenceService.transcribe(request))


@router.post(
    "/back-transcribe",
    response_model=EnvelopeResponse[SequenceResult],
    summary="Back-transcribe RNA to DNA",
    description="Replace every U with T.",
)
async def back_transcribe(request: SequenceRequest) -> EnvelopeResponse[SequenceResult]:
    return EnvelopeResponse.ok(SequenceService.back_transcribe(request))


@router.post(
    "/translate",
    response_model=EnvelopeResponse[SequenceResult],
    summary="Translate a nucleotide sequence to protein",
    description=(
        "Translate using any NCBI genetic code. A sequence whose length is not a multiple "
        "of three is truncated to the last whole codon and a warning is returned."
    ),
)
async def translate(request: TranslationRequest) -> EnvelopeResponse[SequenceResult]:
    return EnvelopeResponse.ok(SequenceService.translate(request))


@router.post(
    "/gc-content",
    response_model=EnvelopeResponse[GCContentResult],
    summary="Calculate GC content",
    description="Percentage of G and C bases. The IUPAC code S (G or C) counts towards GC.",
)
async def gc_content(request: SequenceRequest) -> EnvelopeResponse[GCContentResult]:
    return EnvelopeResponse.ok(SequenceService.gc_content(request))


@router.post(
    "/count-bases",
    response_model=EnvelopeResponse[BaseCountResult],
    summary="Count residue frequencies",
    description="Character frequency table, ordered from most to least common.",
)
async def count_bases(request: SequenceRequest) -> EnvelopeResponse[BaseCountResult]:
    return EnvelopeResponse.ok(SequenceService.count_bases(request))


@router.post(
    "/kmer",
    response_model=EnvelopeResponse[KmerResult],
    summary="Count k-mers",
    description="Count every substring of length k. Use `top` to return only the most frequent.",
)
async def kmer(request: KmerRequest) -> EnvelopeResponse[KmerResult]:
    return EnvelopeResponse.ok(SequenceService.kmer(request))


@router.post(
    "/find-motif",
    response_model=EnvelopeResponse[MotifResult],
    summary="Locate a motif",
    description=(
        "Find every occurrence of a substring. Overlapping hits are counted by default; "
        "set `allow_overlaps` to false to advance past each match."
    ),
)
async def find_motif(request: MotifRequest) -> EnvelopeResponse[MotifResult]:
    return EnvelopeResponse.ok(SequenceService.find_motif(request))


@router.post(
    "/validate",
    response_model=EnvelopeResponse[ValidationResult],
    summary="Validate a sequence against an alphabet",
    description=(
        "Report whether the sequence fits an alphabet, which characters are invalid and "
        "which IUPAC ambiguity codes it uses. This endpoint reports rather than rejects, "
        "so an invalid sequence still returns HTTP 200."
    ),
)
async def validate(request: SequenceRequest) -> EnvelopeResponse[ValidationResult]:
    return EnvelopeResponse.ok(SequenceService.validate(request))
