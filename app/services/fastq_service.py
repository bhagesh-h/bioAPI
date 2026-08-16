"""FASTQ document utilities that operate entirely in memory."""

from __future__ import annotations

import base64
import binascii
import gzip
import io

from app.core.context import add_warning
from app.core.errors import BioAPIError, FastqParseError
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
from app.utils.parsers import FastaRecord, parse_fastq, render_fasta, render_fastq

_GC_CHARS = frozenset("GCS")

# A gzip member always starts with these two bytes.
_GZIP_MAGIC = b"\x1f\x8b"


class FastqService:
    """Stateless transformations of a FASTQ document."""

    @staticmethod
    def quality_filter(request: QualityFilterRequest) -> FastqResult:
        """Keep reads whose mean Phred score and length clear the thresholds."""
        reads = parse_fastq(request.fastq_string)
        kept = [
            read
            for read in reads
            if read.mean_quality(request.quality_offset) >= request.min_quality
            and len(read.sequence) >= request.min_length
        ]

        dropped = len(reads) - len(kept)
        if dropped:
            add_warning(f"Filtered out {dropped} of {len(reads)} read(s).")
        if not kept:
            add_warning("No read met the filter criteria; the result is empty.")

        return FastqResult(
            fastq_string=render_fastq(kept) if kept else "",
            num_reads=len(kept),
        )

    @staticmethod
    def to_fasta(request: FastqToFastaRequest) -> FastaResult:
        """Drop the quality track and emit FASTA."""
        reads = parse_fastq(request.fastq_string)
        records = [FastaRecord(read.identifier, read.description, read.sequence) for read in reads]
        add_warning("Quality scores are not representable in FASTA and were discarded.")
        return FastaResult(
            fasta_string=render_fasta(records, request.line_width),
            num_sequences=len(records),
        )

    @staticmethod
    def compress_gz(request: FastqRequest) -> GzResult:
        """Gzip the document and return it base64-encoded so JSON can carry it."""
        parse_fastq(request.fastq_string)  # reject malformed input before compressing

        raw = request.fastq_string.encode("utf-8")
        buffer = io.BytesIO()
        # mtime=0 keeps the output byte-identical for identical input.
        with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as archive:
            archive.write(raw)
        compressed = buffer.getvalue()

        return GzResult(
            data_base64=base64.b64encode(compressed).decode("ascii"),
            original_size_bytes=len(raw),
            compressed_size_bytes=len(compressed),
            compression_ratio=round(len(raw) / len(compressed), 3) if compressed else 0.0,
        )

    @staticmethod
    def decompress_gz(request: GzDecompressRequest) -> FastqResult:
        """Reverse :meth:`compress_gz`, validating the result is real FASTQ."""
        try:
            compressed = base64.b64decode(request.fastq_gz_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise BioAPIError(
                "fastq_gz_base64 is not valid base64.",
                details={"reason": str(exc)},
            ) from exc

        if not compressed.startswith(_GZIP_MAGIC):
            raise BioAPIError(
                "The decoded payload is not a gzip stream (missing the 1f 8b magic bytes)."
            )

        try:
            document = gzip.decompress(compressed).decode("utf-8")
        except (OSError, EOFError, UnicodeDecodeError) as exc:
            raise BioAPIError(
                f"Could not decompress the payload: {exc}",
                details={"reason": type(exc).__name__},
            ) from exc

        reads = parse_fastq(document)
        return FastqResult(fastq_string=render_fastq(reads), num_reads=len(reads))

    @staticmethod
    def stats(request: FastqRequest) -> FastqStatsResult:
        """Length, composition and quality summary for an inline FASTQ document."""
        reads = parse_fastq(request.fastq_string)
        if not reads:
            raise FastqParseError("The document contains no reads.")

        lengths = [len(read.sequence) for read in reads]
        scores: list[int] = []
        gc_count = 0
        for read in reads:
            scores.extend(read.phred_scores(request.quality_offset))
            gc_count += sum(1 for char in read.sequence.upper() if char in _GC_CHARS)

        total_bases = sum(lengths)
        q20 = sum(1 for score in scores if score >= 20)
        q30 = sum(1 for score in scores if score >= 30)

        if any(score < 0 for score in scores):
            add_warning(
                f"Some quality characters decode below zero at offset {request.quality_offset}; "
                "the file may use a different Phred encoding."
            )

        return FastqStatsResult(
            num_reads=len(reads),
            total_bases=total_bases,
            min_length=min(lengths),
            max_length=max(lengths),
            avg_length=round(total_bases / len(reads), 2),
            gc_percent=round(gc_count / total_bases * 100, 4) if total_bases else 0.0,
            mean_quality=round(sum(scores) / len(scores), 3) if scores else 0.0,
            min_quality=min(scores) if scores else 0,
            max_quality=max(scores) if scores else 0,
            q20_percent=round(q20 / len(scores) * 100, 2) if scores else 0.0,
            q30_percent=round(q30 / len(scores) * 100, 2) if scores else 0.0,
        )
