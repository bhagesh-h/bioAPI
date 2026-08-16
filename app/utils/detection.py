"""File format detection.

The previous implementation trusted the filename extension alone, which meant a
FASTA file named ``reads.txt`` was reported as plain text. Detection now reads
the first few kilobytes and combines the content signature with the extension,
returning a real confidence level and the reason behind the verdict.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

SNIFF_BYTES = 64 * 1024


class FileFormat(StrEnum):
    """Formats the file endpoints understand."""

    fasta = "fasta"
    fastq = "fastq"
    genbank = "genbank"
    embl = "embl"
    bam = "bam"
    sam = "sam"
    vcf = "vcf"
    gff = "gff"
    gtf = "gtf"
    text = "text"
    unknown = "unknown"


class Confidence(StrEnum):
    """How much the detector trusts its own answer."""

    high = "high"
    medium = "medium"
    low = "low"


class Detection(NamedTuple):
    """A format verdict with its justification."""

    format: FileFormat
    confidence: Confidence
    reason: str


_EXTENSION_MAP: dict[str, FileFormat] = {
    "fasta": FileFormat.fasta,
    "fa": FileFormat.fasta,
    "fna": FileFormat.fasta,
    "faa": FileFormat.fasta,
    "ffn": FileFormat.fasta,
    "frn": FileFormat.fasta,
    "mpfa": FileFormat.fasta,
    "fastq": FileFormat.fastq,
    "fq": FileFormat.fastq,
    "gb": FileFormat.genbank,
    "gbk": FileFormat.genbank,
    "genbank": FileFormat.genbank,
    "embl": FileFormat.embl,
    "bam": FileFormat.bam,
    "sam": FileFormat.sam,
    "vcf": FileFormat.vcf,
    "gff": FileFormat.gff,
    "gff3": FileFormat.gff,
    "gtf": FileFormat.gtf,
    "txt": FileFormat.text,
    "text": FileFormat.text,
    "seq": FileFormat.text,
}

# BAM is BGZF-compressed; the payload starts with the magic bytes "BAM\1".
_BAM_GZIP_MAGIC = b"\x1f\x8b"
_TEXT_MAGIC: tuple[tuple[bytes, FileFormat], ...] = (
    (b"##fileformat=VCF", FileFormat.vcf),
    (b"##gff-version", FileFormat.gff),
    (b"LOCUS ", FileFormat.genbank),
    (b"ID   ", FileFormat.embl),
    (b"@HD\t", FileFormat.sam),
    (b"@SQ\t", FileFormat.sam),
)


def format_from_extension(filename: str | None) -> FileFormat:
    """Map a filename's extension to a format, ignoring a ``.gz`` suffix."""
    if not filename:
        return FileFormat.unknown
    suffixes = [suffix.lstrip(".").lower() for suffix in Path(filename).suffixes]
    if suffixes and suffixes[-1] in {"gz", "bgz", "bz2"}:
        suffixes.pop()
    if not suffixes:
        return FileFormat.unknown
    return _EXTENSION_MAP.get(suffixes[-1], FileFormat.unknown)


def _sniff_tabular(lines: list[str]) -> FileFormat | None:
    """Tell GFF and GTF apart by their attribute-column syntax."""
    data_lines = [line for line in lines if line and not line.startswith("#")]
    if not data_lines:
        return None

    tabular = [line.split("\t") for line in data_lines[:20]]
    nine_column = [row for row in tabular if len(row) == 9]
    if len(nine_column) < max(1, len(tabular) // 2):
        return None

    # Coordinates must be integers for the row to be a real feature line.
    for row in nine_column:
        if not (row[3].isdigit() and row[4].isdigit()):
            return None

    # GTF attributes look like `gene_id "X";`, GFF3 like `ID=X;`.
    attributes = " ".join(row[8] for row in nine_column)
    if "gene_id " in attributes or "transcript_id " in attributes:
        return FileFormat.gtf
    return FileFormat.gff


def sniff_content(head: bytes) -> FileFormat | None:
    """Identify a format from the first bytes of a file, or return ``None``."""
    if not head:
        return None

    if head.startswith(_BAM_GZIP_MAGIC):
        # BGZF blocks carry "BAM\1" once inflated; the raw header is enough of a
        # signal here since the parser will confirm or fail loudly.
        return FileFormat.bam

    for magic, detected in _TEXT_MAGIC:
        if head.startswith(magic):
            return detected

    try:
        text = head.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None

    lines = [line.rstrip("\r") for line in text.splitlines()]
    meaningful = [line for line in lines if line.strip()]
    if not meaningful:
        return None

    first = meaningful[0]

    if first.startswith(">"):
        return FileFormat.fasta

    if first.startswith("@"):
        # Distinguish FASTQ from a headerless SAM: FASTQ has a '+' on line 3.
        if len(meaningful) >= 3 and meaningful[2].startswith("+"):
            return FileFormat.fastq
        if "\t" in first:
            return FileFormat.sam
        return FileFormat.fastq

    tabular = _sniff_tabular(lines)
    if tabular is not None:
        return tabular

    return None


def detect_format(filename: str | None, head: bytes) -> Detection:
    """Combine content and filename evidence into a single verdict."""
    by_extension = format_from_extension(filename)
    by_content = sniff_content(head)

    if by_content is not None and by_content == by_extension:
        return Detection(by_content, Confidence.high, "content and file extension agree")

    if by_content is not None and by_extension in (FileFormat.unknown, FileFormat.text):
        return Detection(by_content, Confidence.high, "identified from file content")

    if by_content is not None:
        return Detection(
            by_content,
            Confidence.medium,
            f"content looks like {by_content}, but the extension suggests {by_extension}",
        )

    if by_extension is not FileFormat.unknown:
        return Detection(by_extension, Confidence.low, "inferred from the file extension only")

    return Detection(FileFormat.text, Confidence.low, "no format signature found; treated as text")
