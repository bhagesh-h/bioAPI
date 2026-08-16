"""Response models for the file-upload analysis endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.utils.detection import Confidence, FileFormat

__all__ = [
    "BamStats",
    "Confidence",
    "FileFormat",
    "FileStatsResponse",
    "FormatDetection",
    "GffStats",
    "QualityStats",
    "SequenceStats",
    "VariantRecord",
    "VcfStats",
]


class FormatDetection(BaseModel):
    """How the uploaded file's format was determined."""

    detected_format: FileFormat
    confidence: Confidence
    reason: str = Field(description="Why the detector reached this verdict.")


class SequenceStats(BaseModel):
    """Composition figures for a FASTA, FASTQ, GenBank or EMBL upload."""

    num_records: int
    min_length: int
    max_length: int
    avg_length: float
    total_bases: int
    n50: int
    gc_percent: float
    ambiguous_chars: int


class QualityStats(BaseModel):
    """Phred quality figures, present only for FASTQ uploads."""

    mean_quality: float
    min_quality: int
    max_quality: int
    q20_percent: float
    q30_percent: float


class BamStats(BaseModel):
    """Alignment figures for a SAM or BAM upload."""

    total_reads: int
    mapped_reads: int
    unmapped_reads: int
    duplicate_reads: int
    avg_read_length: float | None
    avg_mapping_quality: float | None
    references: int = Field(description="Number of reference sequences in the header.")


class GffStats(BaseModel):
    """Feature counts for a GFF or GTF upload."""

    total_features: int
    feature_counts: dict[str, int]
    sequence_ids: list[str] = Field(description="Distinct sequence identifiers, first 50.")


class VcfStats(BaseModel):
    """Variant figures for a VCF upload."""

    total_variants: int
    snps: int
    indels: int
    other: int
    transitions: int
    transversions: int
    ti_tv_ratio: float | None = Field(
        default=None, description="Transition/transversion ratio; null when no transversions."
    )
    samples: list[str] = Field(default_factory=list)
    contigs: list[str] = Field(default_factory=list)


class FileStatsResponse(BaseModel):
    """Everything the analyser could work out about an uploaded file."""

    filename: str
    content_type: str
    size_bytes: int
    lines: int | None = Field(default=None, description="Line count, for text-based formats.")
    format: FormatDetection
    sequence_stats: SequenceStats | None = None
    quality_stats: QualityStats | None = None
    bam_stats: BamStats | None = None
    gff_stats: GffStats | None = None
    vcf_stats: VcfStats | None = None
    preview_ids: list[str] = Field(
        default_factory=list, description="Identifiers of the first few records."
    )


class VariantRecord(BaseModel):
    """A single variant extracted from a VCF."""

    chrom: str
    pos: int
    id: str | None
    ref: str
    alts: list[str]
    type: str = Field(description="SNP, INDEL, MNP or OTHER.")
    qual: float | None
    filter: list[str] = Field(default_factory=list)


class VariantExtractionResult(BaseModel):
    """Variants matching the requested type, with the totals they came from."""

    variants: list[VariantRecord]
    count: int
    total_in_file: int
    variant_type: str


class GffExtractionSummary(BaseModel):
    """What a GFF-driven FASTA extraction produced."""

    features_extracted: int
    features_skipped: int
    sequence_ids: list[str]
