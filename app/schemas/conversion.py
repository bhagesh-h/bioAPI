"""Conversion formats and the matrix of pairs the service actually supports.

The previous version advertised source formats Biopython cannot parse (BAM,
GFF, GTF) and a ``json`` target ``SeqIO.write`` has never supported, so those
requests always failed. The supported pairs are now declared in one place,
validated before any work starts, and published through ``GET /api/v1/formats``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SourceFormat(StrEnum):
    """Formats a file may be converted *from*."""

    fasta = "fasta"
    fastq = "fastq"
    genbank = "genbank"
    embl = "embl"
    tab = "tab"
    text = "text"


class TargetFormat(StrEnum):
    """Formats a file may be converted *to*."""

    fasta = "fasta"
    fastq = "fastq"
    genbank = "genbank"
    embl = "embl"
    tab = "tab"
    json = "json"


#: Which targets each source can reach. Anything absent is rejected up front
#: with an explanation rather than failing deep inside Biopython.
CONVERSION_MATRIX: dict[SourceFormat, frozenset[TargetFormat]] = {
    SourceFormat.fasta: frozenset(
        {TargetFormat.genbank, TargetFormat.embl, TargetFormat.tab, TargetFormat.json}
    ),
    SourceFormat.fastq: frozenset(
        {
            TargetFormat.fasta,
            TargetFormat.genbank,
            TargetFormat.embl,
            TargetFormat.tab,
            TargetFormat.json,
        }
    ),
    SourceFormat.genbank: frozenset(
        {TargetFormat.fasta, TargetFormat.embl, TargetFormat.tab, TargetFormat.json}
    ),
    SourceFormat.embl: frozenset(
        {TargetFormat.fasta, TargetFormat.genbank, TargetFormat.tab, TargetFormat.json}
    ),
    SourceFormat.tab: frozenset(
        {TargetFormat.fasta, TargetFormat.genbank, TargetFormat.embl, TargetFormat.json}
    ),
    SourceFormat.text: frozenset({TargetFormat.fasta, TargetFormat.json}),
}

#: Reasons a pair is unavailable, so the error can say more than "unsupported".
UNSUPPORTED_REASONS: dict[tuple[SourceFormat, TargetFormat], str] = {
    (SourceFormat.fasta, TargetFormat.fastq): (
        "FASTA carries no per-base quality scores, so it cannot produce FASTQ."
    ),
    (SourceFormat.genbank, TargetFormat.fastq): (
        "GenBank carries no per-base quality scores, so it cannot produce FASTQ."
    ),
    (SourceFormat.embl, TargetFormat.fastq): (
        "EMBL carries no per-base quality scores, so it cannot produce FASTQ."
    ),
    (SourceFormat.tab, TargetFormat.fastq): (
        "Tab-delimited input carries no quality scores, so it cannot produce FASTQ."
    ),
    (SourceFormat.text, TargetFormat.fastq): (
        "Plain text carries no quality scores, so it cannot produce FASTQ."
    ),
    (SourceFormat.text, TargetFormat.genbank): (
        "Plain text has no annotations; convert to FASTA first if that is enough."
    ),
    (SourceFormat.text, TargetFormat.embl): (
        "Plain text has no annotations; convert to FASTA first if that is enough."
    ),
    (SourceFormat.text, TargetFormat.tab): (
        "Plain text has no identifiers to place in the first column."
    ),
}

#: Extension used for the downloaded file of each target format.
TARGET_EXTENSIONS: dict[TargetFormat, str] = {
    TargetFormat.fasta: "fasta",
    TargetFormat.fastq: "fastq",
    TargetFormat.genbank: "gb",
    TargetFormat.embl: "embl",
    TargetFormat.tab: "tsv",
    TargetFormat.json: "json",
}


class ConversionWarning(BaseModel):
    """A non-fatal note about information lost or invented during conversion."""

    code: str
    message: str


class ConversionResult(BaseModel):
    """Metadata about a completed conversion, mirrored into response headers."""

    filename: str
    source_format: SourceFormat
    target_format: TargetFormat
    records_converted: int
    warnings: list[ConversionWarning] = Field(default_factory=list)


class ConversionPair(BaseModel):
    """One entry of the published conversion matrix."""

    source: SourceFormat
    targets: list[TargetFormat]


class FormatCapabilities(BaseModel):
    """Everything ``GET /api/v1/formats`` reports."""

    analysable_formats: list[str] = Field(
        description="Formats POST /api/v1/files/stats can analyse."
    )
    conversion_sources: list[SourceFormat]
    conversion_targets: list[TargetFormat]
    conversion_matrix: list[ConversionPair]
    unsupported_pairs: dict[str, str] = Field(
        description="Pairs that are deliberately unavailable, keyed 'source->target'."
    )


class ConsensusResult(BaseModel):
    """Summary of a VCF-driven consensus build, mirrored into response headers."""

    records_written: int
    variants_applied: int
    variants_skipped: int
    skipped_reasons: dict[str, int] = Field(default_factory=dict)
