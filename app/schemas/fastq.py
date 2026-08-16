"""Request and response models for the FASTQ string utilities."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_EXAMPLE_FASTQ = "@read1 sample\nACGTACGT\n+\nIIIIIIII"


class FastqRequest(BaseModel):
    """Base request carrying an inline FASTQ document."""

    model_config = ConfigDict(json_schema_extra={"example": {"fastq_string": _EXAMPLE_FASTQ}})

    fastq_string: str = Field(
        min_length=4, description="A FASTQ document with four lines per read."
    )
    quality_offset: int = Field(
        default=33,
        ge=0,
        le=93,
        description="Phred ASCII offset. 33 for Sanger and Illumina 1.8+, 64 for older Illumina.",
    )


class QualityFilterRequest(FastqRequest):
    min_quality: float = Field(
        default=20, ge=0, le=93, description="Minimum mean Phred score a read must reach."
    )
    min_length: int = Field(default=0, ge=0, description="Discard reads shorter than this.")


class FastqToFastaRequest(FastqRequest):
    line_width: int | None = Field(default=60, ge=0, le=1000)


class GzDecompressRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"fastq_gz_base64": "H4sIA..."}})

    fastq_gz_base64: str = Field(
        min_length=1,
        description="Base64-encoded gzip stream, as returned by POST /api/v1/fastq/compress-gz.",
    )
    quality_offset: int = Field(default=33, ge=0, le=93)


class FastqResult(BaseModel):
    fastq_string: str
    num_reads: int


class FastaFromFastqResult(BaseModel):
    fasta_string: str
    num_sequences: int


class GzResult(BaseModel):
    """Compression output, base64-encoded so it survives a JSON transport."""

    data_base64: str
    original_size_bytes: int
    compressed_size_bytes: int
    compression_ratio: float = Field(description="original / compressed, rounded to 3 decimals.")


class FastqStatsResult(BaseModel):
    """Aggregate quality and length figures for an inline FASTQ document."""

    num_reads: int
    total_bases: int
    min_length: int
    max_length: int
    avg_length: float
    gc_percent: float
    mean_quality: float
    min_quality: int
    max_quality: int
    q20_percent: float = Field(description="Percentage of bases with a Phred score of 20 or more.")
    q30_percent: float = Field(description="Percentage of bases with a Phred score of 30 or more.")
