"""Request and response models for the FASTA string utilities."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_EXAMPLE_FASTA = ">seq1 first record\nACGTACGTAC\n>seq2 second record\nTTTTGGGGCC"


class FastaRequest(BaseModel):
    """Base request carrying an inline FASTA document."""

    model_config = ConfigDict(json_schema_extra={"example": {"fasta_string": _EXAMPLE_FASTA}})

    fasta_string: str = Field(
        min_length=2,
        description="A FASTA document. Multi-line sequences and blank lines are accepted.",
    )
    line_width: int | None = Field(
        default=60,
        ge=0,
        le=1000,
        description="Wrap output sequences at this width. Use 0 for one line per sequence.",
    )


class ShortenHeadersRequest(FastaRequest):
    n: int = Field(ge=1, le=10_000, description="Maximum characters to keep in each header.")


class GetNSequencesRequest(FastaRequest):
    n: int = Field(ge=1, description="Number of sequences to take from the top.")


class FilterByLengthRequest(FastaRequest):
    min_length: int = Field(default=0, ge=0, description="Minimum sequence length, inclusive.")
    max_length: int | None = Field(
        default=None, ge=0, description="Maximum sequence length, inclusive. Omit for no ceiling."
    )

    @model_validator(mode="after")
    def _min_below_max(self) -> FilterByLengthRequest:
        if self.max_length is not None and self.min_length > self.max_length:
            raise ValueError("min_length must not exceed max_length")
        return self


class ExtractSubsequenceRequest(FastaRequest):
    start: int = Field(ge=1, description="1-based start position, inclusive.")
    end: int = Field(ge=1, description="1-based end position, inclusive.")
    skip_short: bool = Field(
        default=False,
        description=(
            "Skip sequences shorter than `end` instead of failing the whole request. "
            "Skipped identifiers are reported in `warnings`."
        ),
    )

    @model_validator(mode="after")
    def _start_before_end(self) -> ExtractSubsequenceRequest:
        if self.start > self.end:
            raise ValueError("start must be less than or equal to end")
        return self


class SampleSequencesRequest(FastaRequest):
    n: int = Field(ge=1, description="Number of sequences to sample without replacement.")
    seed: int | None = Field(
        default=None,
        description="Seed the sampler to make the selection reproducible.",
    )


class SplitFastaRequest(FastaRequest):
    n: int | None = Field(default=None, ge=1, description="Number of chunks to produce.")
    size: int | None = Field(default=None, ge=1, description="Sequences per chunk.")

    @model_validator(mode="after")
    def _exactly_one_strategy(self) -> SplitFastaRequest:
        if (self.n is None) == (self.size is None):
            raise ValueError("supply exactly one of 'n' or 'size'")
        return self


class MergeFastaRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"fasta_strings": [">a\nACGT", ">b\nTTGG"]}}
    )

    fasta_strings: list[str] = Field(
        min_length=2, description="Two or more FASTA documents to concatenate."
    )
    line_width: int | None = Field(default=60, ge=0, le=1000)
    deduplicate_ids: bool = Field(
        default=False,
        description="Suffix repeated identifiers with _2, _3, … instead of leaving duplicates.",
    )


class ConvertCaseRequest(FastaRequest):
    case: Literal["upper", "lower"] = Field(default="upper", description="Target case.")


class RemoveUnknownCharsRequest(FastaRequest):
    keep_ambiguity_codes: bool = Field(
        default=False,
        description="Keep IUPAC ambiguity codes (RYSWKMBDHVN) instead of stripping them too.",
    )


class RenameSequencesRequest(FastaRequest):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"fasta_string": ">old_id\nACGT", "rename_map": {"old_id": "new_id"}}
        }
    )

    rename_map: dict[str, str] = Field(
        min_length=1, description="Mapping of {existing_id: replacement_id}."
    )


class ModifyDescriptionsRequest(FastaRequest):
    description_map: dict[str, str] = Field(
        min_length=1, description="Mapping of {sequence_id: new_description}."
    )


class FastaResult(BaseModel):
    """A FASTA document produced by one of the utilities."""

    fasta_string: str
    num_sequences: int


class SplitFastaResult(BaseModel):
    chunks: list[str]
    num_chunks: int
    sequences_per_chunk: list[int]


class SequenceIdsResult(BaseModel):
    ids: list[str]
    count: int


class FastaRecordSummary(BaseModel):
    """Per-sequence figures returned by the FASTA stats endpoint."""

    id: str
    length: int
    gc_percent: float
    ambiguous_chars: int


class FastaStatsResult(BaseModel):
    """Aggregate composition of an inline FASTA document."""

    num_sequences: int
    total_bases: int
    min_length: int
    max_length: int
    avg_length: float
    n50: int = Field(description="Length at which half the assembled bases sit in longer contigs.")
    gc_percent: float
    ambiguous_chars: int
    records: list[FastaRecordSummary]
