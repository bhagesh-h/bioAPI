"""FASTA string utilities. Every endpoint takes and returns inline documents."""

from fastapi import APIRouter

from app.schemas.common import ERROR_RESPONSES, EnvelopeResponse
from app.schemas.fasta import (
    ConvertCaseRequest,
    ExtractSubsequenceRequest,
    FastaRequest,
    FastaResult,
    FastaStatsResult,
    FilterByLengthRequest,
    GetNSequencesRequest,
    MergeFastaRequest,
    ModifyDescriptionsRequest,
    RemoveUnknownCharsRequest,
    RenameSequencesRequest,
    SampleSequencesRequest,
    SequenceIdsResult,
    ShortenHeadersRequest,
    SplitFastaRequest,
    SplitFastaResult,
)
from app.services.fasta_service import FastaService

router = APIRouter(prefix="/fasta", tags=["FASTA Utilities"], responses=ERROR_RESPONSES)


@router.post(
    "/stats",
    response_model=EnvelopeResponse[FastaStatsResult],
    summary="Summarise a FASTA document",
    description="Length distribution, N50, GC content and per-sequence figures.",
)
async def stats(request: FastaRequest) -> EnvelopeResponse[FastaStatsResult]:
    return EnvelopeResponse.ok(FastaService.stats(request))


@router.post(
    "/shorten-headers",
    response_model=EnvelopeResponse[FastaResult],
    summary="Shorten FASTA headers",
    description=(
        "Truncate every header to at most `n` characters. If truncation makes two "
        "identifiers collide, that is reported in `warnings`."
    ),
)
async def shorten_headers(request: ShortenHeadersRequest) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.shorten_headers(request))


@router.post(
    "/get-n-sequences",
    response_model=EnvelopeResponse[FastaResult],
    summary="Take the first N sequences",
    description="Return the leading `n` records. Asking for more than exist returns them all.",
)
async def get_n_sequences(request: GetNSequencesRequest) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.get_n_sequences(request))


@router.post(
    "/filter-by-length",
    response_model=EnvelopeResponse[FastaResult],
    summary="Filter sequences by length",
    description="Keep sequences whose length lies within [min_length, max_length].",
)
async def filter_by_length(request: FilterByLengthRequest) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.filter_by_length(request))


@router.post(
    "/extract-subsequence",
    response_model=EnvelopeResponse[FastaResult],
    summary="Slice a coordinate range from every sequence",
    description=(
        "Extract positions `start` to `end` (1-based, inclusive). Sequences shorter than "
        "`end` fail the request unless `skip_short` is set."
    ),
)
async def extract_subsequence(
    request: ExtractSubsequenceRequest,
) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.extract_subsequence(request))


@router.post(
    "/sample-sequences",
    response_model=EnvelopeResponse[FastaResult],
    summary="Randomly sample N sequences",
    description="Draw `n` sequences without replacement. Pass `seed` for a reproducible draw.",
)
async def sample_sequences(request: SampleSequencesRequest) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.sample_sequences(request))


@router.post(
    "/split",
    response_model=EnvelopeResponse[SplitFastaResult],
    summary="Split a FASTA into chunks",
    description="Supply either `n` (number of chunks) or `size` (sequences per chunk).",
)
async def split(request: SplitFastaRequest) -> EnvelopeResponse[SplitFastaResult]:
    return EnvelopeResponse.ok(FastaService.split(request))


@router.post(
    "/merge",
    response_model=EnvelopeResponse[FastaResult],
    summary="Merge FASTA documents",
    description=(
        "Concatenate two or more documents. Set `deduplicate_ids` to suffix repeated "
        "identifiers instead of leaving collisions in the output."
    ),
)
async def merge(request: MergeFastaRequest) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.merge(request))


@router.post(
    "/convert-case",
    response_model=EnvelopeResponse[FastaResult],
    summary="Convert sequence case",
    description="Uppercase or lowercase every sequence. Headers are left untouched.",
)
async def convert_case(request: ConvertCaseRequest) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.convert_case(request))


@router.post(
    "/remove-unknown-chars",
    response_model=EnvelopeResponse[FastaResult],
    summary="Strip characters outside the nucleotide alphabet",
    description=(
        "Remove anything that is not A, C, G or T. Set `keep_ambiguity_codes` to preserve "
        "IUPAC codes such as N and R."
    ),
)
async def remove_unknown_chars(
    request: RemoveUnknownCharsRequest,
) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.remove_unknown_chars(request))


@router.post(
    "/rename-sequences",
    response_model=EnvelopeResponse[FastaResult],
    summary="Rename sequence identifiers",
    description="Apply a {old_id: new_id} mapping. Descriptions are preserved.",
)
async def rename_sequences(request: RenameSequencesRequest) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.rename_sequences(request))


@router.post(
    "/modify-descriptions",
    response_model=EnvelopeResponse[FastaResult],
    summary="Replace sequence descriptions",
    description="Apply a {sequence_id: new_description} mapping to the header lines.",
)
async def modify_descriptions(
    request: ModifyDescriptionsRequest,
) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.modify_descriptions(request))


@router.post(
    "/find-unique",
    response_model=EnvelopeResponse[FastaResult],
    summary="Deduplicate by sequence content",
    description="Keep the first record of each distinct sequence, comparing case-insensitively.",
)
async def find_unique(request: FastaRequest) -> EnvelopeResponse[FastaResult]:
    return EnvelopeResponse.ok(FastaService.find_unique(request))


@router.post(
    "/extract-ids",
    response_model=EnvelopeResponse[SequenceIdsResult],
    summary="List sequence identifiers",
    description="Return every identifier in the order it appears.",
)
async def extract_ids(request: FastaRequest) -> EnvelopeResponse[SequenceIdsResult]:
    return EnvelopeResponse.ok(FastaService.extract_ids(request))
