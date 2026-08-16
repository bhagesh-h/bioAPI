"""Analysis of uploaded bioinformatics files.

Everything here takes a path on disk rather than an ``UploadFile``: the router
streams the upload to a temporary file first, which keeps the size limit in one
place and lets pysam hand the path straight to htslib.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from Bio import SeqIO

from app.core.context import add_warning
from app.core.errors import ParseError, UnsupportedFormatError
from app.schemas.file_stats import (
    BamStats,
    FormatDetection,
    GffExtractionSummary,
    GffStats,
    QualityStats,
    SequenceStats,
    VariantExtractionResult,
    VariantRecord,
    VcfStats,
)
from app.utils.detection import SNIFF_BYTES, Detection, FileFormat, detect_format
from app.utils.parsers import FastaRecord, render_fasta

_GC_CHARS = frozenset("GCS")
_AMBIGUITY = frozenset("RYSWKMBDHVN")
_PREVIEW_LIMIT = 5

#: Formats Biopython's SeqIO can read directly.
_SEQIO_FORMATS: dict[FileFormat, str] = {
    FileFormat.fasta: "fasta",
    FileFormat.fastq: "fastq",
    FileFormat.genbank: "genbank",
    FileFormat.embl: "embl",
}

_TEXT_FORMATS = frozenset(
    {
        FileFormat.fasta,
        FileFormat.fastq,
        FileFormat.genbank,
        FileFormat.embl,
        FileFormat.vcf,
        FileFormat.gff,
        FileFormat.gtf,
        FileFormat.sam,
        FileFormat.text,
    }
)

_TRANSITIONS = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}


def _n50(lengths: list[int]) -> int:
    if not lengths:
        return 0
    ordered = sorted(lengths, reverse=True)
    half = sum(ordered) / 2
    running = 0
    for length in ordered:
        running += length
        if running >= half:
            return length
    return ordered[-1]


class FileService:
    """Format detection and per-format statistics for uploaded files."""

    @staticmethod
    def detect(path: Path, filename: str | None) -> FormatDetection:
        """Sniff the file's opening bytes and combine that with its name."""
        with path.open("rb") as handle:
            head = handle.read(SNIFF_BYTES)
        detection: Detection = detect_format(filename, head)
        return FormatDetection(
            detected_format=detection.format,
            confidence=detection.confidence,
            reason=detection.reason,
        )

    @staticmethod
    def count_lines(path: Path) -> int:
        count = 0
        with path.open("rb") as handle:
            for _ in handle:
                count += 1
        return count

    @classmethod
    def analyse(cls, path: Path, detection: FormatDetection) -> dict[str, Any]:
        """Dispatch to the right analyser and return the payload fragments."""
        detected = detection.detected_format

        if detected in _SEQIO_FORMATS:
            return cls._analyse_sequences(path, _SEQIO_FORMATS[detected])
        if detected in (FileFormat.bam, FileFormat.sam):
            return {"bam_stats": cls._analyse_alignments(path, detected)}
        if detected in (FileFormat.gff, FileFormat.gtf):
            return {"gff_stats": cls._analyse_features(path)}
        if detected is FileFormat.vcf:
            return {"vcf_stats": cls._analyse_variants(path)}

        add_warning(
            "The file could not be matched to a known bioinformatics format; "
            "only size and line counts are reported."
        )
        return {}

    # ── per-format analysers ─────────────────────────────────────────────────

    @staticmethod
    def _analyse_sequences(path: Path, seqio_format: str) -> dict[str, Any]:
        """Stream records with SeqIO, accumulating counters rather than sequences."""
        lengths: list[int] = []
        preview: list[str] = []
        gc_count = 0
        ambiguous = 0
        quality_scores: list[int] = []
        q20 = q30 = 0

        try:
            for index, record in enumerate(SeqIO.parse(str(path), seqio_format)):
                sequence = str(record.seq).upper()
                lengths.append(len(sequence))
                gc_count += sum(1 for char in sequence if char in _GC_CHARS)
                ambiguous += sum(1 for char in sequence if char in _AMBIGUITY)

                if index < _PREVIEW_LIMIT:
                    preview.append(record.id)

                scores = record.letter_annotations.get("phred_quality")
                if scores:
                    quality_scores.extend(scores)
                    q20 += sum(1 for score in scores if score >= 20)
                    q30 += sum(1 for score in scores if score >= 30)
        except ValueError as exc:
            raise ParseError(
                f"The file is not valid {seqio_format}: {exc}",
                details={"format": seqio_format},
            ) from exc

        if not lengths:
            raise ParseError(
                f"No {seqio_format} records were found in the file.",
                details={"format": seqio_format},
            )

        total = sum(lengths)
        stats = SequenceStats(
            num_records=len(lengths),
            min_length=min(lengths),
            max_length=max(lengths),
            avg_length=round(total / len(lengths), 2),
            total_bases=total,
            n50=_n50(lengths),
            gc_percent=round(gc_count / total * 100, 4) if total else 0.0,
            ambiguous_chars=ambiguous,
        )

        quality: QualityStats | None = None
        if quality_scores:
            count = len(quality_scores)
            quality = QualityStats(
                mean_quality=round(sum(quality_scores) / count, 3),
                min_quality=min(quality_scores),
                max_quality=max(quality_scores),
                q20_percent=round(q20 / count * 100, 2),
                q30_percent=round(q30 / count * 100, 2),
            )

        return {"sequence_stats": stats, "quality_stats": quality, "preview_ids": preview}

    @staticmethod
    def _analyse_alignments(path: Path, detected: FileFormat) -> BamStats:
        import pysam

        mode = "r" if detected is FileFormat.sam else "rb"
        total = mapped = unmapped = duplicates = 0
        lengths: list[int] = []
        mapping_qualities: list[int] = []
        references = 0

        try:
            with pysam.AlignmentFile(str(path), mode, check_sq=False) as alignments:
                references = alignments.header.nreferences if alignments.header else 0
                for read in alignments:
                    total += 1
                    if read.is_unmapped:
                        unmapped += 1
                    else:
                        mapped += 1
                        mapping_qualities.append(read.mapping_quality)
                    if read.is_duplicate:
                        duplicates += 1
                    if read.query_length:
                        lengths.append(read.query_length)
        except (ValueError, OSError) as exc:
            raise ParseError(
                f"The file could not be read as {detected.value.upper()}: {exc}",
                details={"format": detected.value},
            ) from exc

        return BamStats(
            total_reads=total,
            mapped_reads=mapped,
            unmapped_reads=unmapped,
            duplicate_reads=duplicates,
            avg_read_length=round(sum(lengths) / len(lengths), 2) if lengths else None,
            avg_mapping_quality=(
                round(sum(mapping_qualities) / len(mapping_qualities), 2)
                if mapping_qualities
                else None
            ),
            references=references,
        )

    @staticmethod
    def _analyse_features(path: Path) -> GffStats:
        counts: Counter[str] = Counter()
        sequence_ids: dict[str, None] = {}
        malformed = 0

        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("#") or not line.strip():
                    continue
                columns = line.rstrip("\n").split("\t")
                if len(columns) < 9:
                    malformed += 1
                    continue
                counts[columns[2]] += 1
                if len(sequence_ids) < 50:
                    sequence_ids.setdefault(columns[0], None)

        if malformed:
            add_warning(f"Ignored {malformed} line(s) that did not have nine tab-separated fields.")

        return GffStats(
            total_features=sum(counts.values()),
            feature_counts=dict(counts.most_common()),
            sequence_ids=list(sequence_ids),
        )

    @staticmethod
    def _analyse_variants(path: Path) -> VcfStats:
        import pysam

        snps = indels = other = transitions = transversions = total = 0
        samples: list[str] = []
        contigs: list[str] = []

        try:
            with pysam.VariantFile(str(path)) as variants:
                samples = [str(sample) for sample in variants.header.samples]
                contigs = [str(contig) for contig in variants.header.contigs]
                for record in variants:
                    total += 1
                    kind = _classify_variant(record.ref, record.alts)
                    if kind == "SNP":
                        snps += 1
                        first_alt = (record.alts or ("",))[0].upper()
                        pair = ((record.ref or "").upper(), first_alt)
                        if pair in _TRANSITIONS:
                            transitions += 1
                        else:
                            transversions += 1
                    elif kind == "INDEL":
                        indels += 1
                    else:
                        other += 1
        except (ValueError, OSError) as exc:
            raise ParseError(
                f"The file could not be read as VCF: {exc}", details={"format": "vcf"}
            ) from exc

        return VcfStats(
            total_variants=total,
            snps=snps,
            indels=indels,
            other=other,
            transitions=transitions,
            transversions=transversions,
            ti_tv_ratio=round(transitions / transversions, 3) if transversions else None,
            samples=samples,
            contigs=contigs,
        )

    # ── cross-file operations ────────────────────────────────────────────────

    @staticmethod
    def extract_gff_features(
        fasta_path: Path, gff_path: Path, feature_type: str | None = None
    ) -> tuple[str, GffExtractionSummary]:
        """Slice FASTA sequences using the coordinates in a GFF/GTF file.

        Features on the minus strand are reverse-complemented. Coordinates that
        fall outside the reference are skipped and counted rather than silently
        producing an empty sequence.
        """
        try:
            references = SeqIO.to_dict(SeqIO.parse(str(fasta_path), "fasta"))
        except ValueError as exc:
            raise ParseError(f"The reference FASTA could not be parsed: {exc}") from exc

        if not references:
            raise ParseError("The reference FASTA contains no sequences.")

        extracted: list[FastaRecord] = []
        skipped: defaultdict[str, int] = defaultdict(int)
        seen_ids: dict[str, None] = {}

        with gff_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("#") or not line.strip():
                    continue
                columns = line.rstrip("\n").split("\t")
                if len(columns) < 9:
                    skipped["malformed_line"] += 1
                    continue

                seq_id, _, kind, raw_start, raw_end = columns[:5]
                strand, attributes = columns[6], columns[8]

                if feature_type and kind.lower() != feature_type.lower():
                    continue
                if seq_id not in references:
                    skipped["unknown_reference"] += 1
                    continue

                try:
                    start, end = int(raw_start), int(raw_end)
                except ValueError:
                    skipped["non_numeric_coordinates"] += 1
                    continue

                reference = references[seq_id]
                if start < 1 or end > len(reference.seq) or start > end:
                    skipped["coordinates_out_of_range"] += 1
                    continue

                sequence = reference.seq[start - 1 : end]
                if strand == "-":
                    sequence = sequence.reverse_complement()

                seen_ids.setdefault(seq_id, None)
                extracted.append(
                    FastaRecord(
                        identifier=f"{seq_id}_{start}_{end}_{kind}",
                        description=f"strand={strand or '.'} {attributes}".strip(),
                        sequence=str(sequence),
                    )
                )

        for reason, count in skipped.items():
            add_warning(f"Skipped {count} feature(s): {reason.replace('_', ' ')}.")

        if not extracted:
            raise ParseError(
                "No feature could be extracted. Check that the GFF sequence identifiers "
                "match the FASTA headers and that feature_type is spelled correctly.",
                details={"skipped": dict(skipped), "feature_type": feature_type},
            )

        summary = GffExtractionSummary(
            features_extracted=len(extracted),
            features_skipped=sum(skipped.values()),
            sequence_ids=list(seen_ids),
        )
        return render_fasta(extracted), summary

    @staticmethod
    def extract_variants(vcf_path: Path, variant_type: str = "ALL") -> VariantExtractionResult:
        """List variants of the requested class from a VCF."""
        import pysam

        wanted = variant_type.upper()
        if wanted not in {"ALL", "SNP", "INDEL", "MNP", "OTHER"}:
            raise UnsupportedFormatError(
                f"Unknown variant_type '{variant_type}'. Use ALL, SNP, INDEL, MNP or OTHER.",
                details={"variant_type": variant_type},
            )

        matched: list[VariantRecord] = []
        total = 0

        try:
            with pysam.VariantFile(str(vcf_path)) as variants:
                for record in variants:
                    total += 1
                    kind = _classify_variant(record.ref, record.alts)
                    if wanted != "ALL" and kind != wanted:
                        continue
                    matched.append(
                        VariantRecord(
                            chrom=record.chrom,
                            pos=record.pos,
                            id=record.id,
                            ref=record.ref or "",
                            alts=list(record.alts) if record.alts else [],
                            type=kind,
                            qual=record.qual,
                            filter=list(record.filter.keys()),
                        )
                    )
        except (ValueError, OSError) as exc:
            raise ParseError(f"The VCF could not be read: {exc}") from exc

        if total and not matched:
            add_warning(f"None of the {total} variant(s) in the file are of type {wanted}.")

        return VariantExtractionResult(
            variants=matched, count=len(matched), total_in_file=total, variant_type=wanted
        )


def _classify_variant(ref: str | None, alts: tuple[str, ...] | None) -> str:
    """Classify a VCF record as SNP, INDEL, MNP or OTHER."""
    if not ref or not alts:
        return "OTHER"

    real_alts = [alt for alt in alts if alt not in {"*", ".", "<NON_REF>"}]
    if not real_alts:
        return "OTHER"

    if any(len(alt) != len(ref) for alt in real_alts):
        return "INDEL"
    if len(ref) == 1:
        return "SNP"
    return "MNP"
