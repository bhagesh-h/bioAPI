"""Format conversion and VCF-driven consensus generation."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from app.core.context import add_warning
from app.core.errors import ParseError, UnsupportedConversionError
from app.schemas.conversion import (
    CONVERSION_MATRIX,
    TARGET_EXTENSIONS,
    UNSUPPORTED_REASONS,
    ConsensusResult,
    ConversionPair,
    ConversionResult,
    ConversionWarning,
    FormatCapabilities,
    SourceFormat,
    TargetFormat,
)

#: Formats whose writers demand a ``molecule_type`` annotation on every record.
_ANNOTATION_HUNGRY = {TargetFormat.genbank, TargetFormat.embl}

#: Map our format names onto Biopython's SeqIO identifiers.
_SEQIO_NAMES: dict[str, str] = {
    "fasta": "fasta",
    "fastq": "fastq",
    "genbank": "genbank",
    "embl": "embl",
    "tab": "tab",
}


class ConversionService:
    """Convert between sequence formats and derive consensus sequences."""

    @staticmethod
    def capabilities() -> FormatCapabilities:
        """Describe what this deployment can convert, for ``GET /api/v1/formats``."""
        return FormatCapabilities(
            analysable_formats=[
                "fasta",
                "fastq",
                "genbank",
                "embl",
                "bam",
                "sam",
                "vcf",
                "gff",
                "gtf",
                "text",
            ],
            conversion_sources=list(SourceFormat),
            conversion_targets=list(TargetFormat),
            conversion_matrix=[
                ConversionPair(source=source, targets=sorted(targets))
                for source, targets in CONVERSION_MATRIX.items()
            ],
            unsupported_pairs={
                f"{source}->{target}": reason
                for (source, target), reason in UNSUPPORTED_REASONS.items()
            },
        )

    @staticmethod
    def validate_pair(source: SourceFormat, target: TargetFormat) -> None:
        """Reject an unsupported pair before any file is read."""
        if source.value == target.value:
            raise UnsupportedConversionError(
                f"Source and target are both {source.value}; there is nothing to convert.",
                details={"source": source.value, "target": target.value},
            )

        if target in CONVERSION_MATRIX.get(source, frozenset()):
            return

        reason = UNSUPPORTED_REASONS.get(
            (source, target),
            f"Converting {source.value} to {target.value} is not supported.",
        )
        raise UnsupportedConversionError(
            reason,
            details={
                "source": source.value,
                "target": target.value,
                "supported_targets": sorted(
                    target.value for target in CONVERSION_MATRIX.get(source, frozenset())
                ),
            },
        )

    @classmethod
    def convert(
        cls, source_path: Path, output_path: Path, source: SourceFormat, target: TargetFormat
    ) -> ConversionResult:
        """Convert ``source_path`` into ``output_path``.

        The pair is validated first, so a caller never gets a Biopython
        traceback dressed up as a 400.
        """
        cls.validate_pair(source, target)

        warnings: list[ConversionWarning] = []
        if source is SourceFormat.fastq and target is not TargetFormat.fastq:
            warnings.append(
                ConversionWarning(
                    code="QUALITY_SCORES_DROPPED",
                    message=f"{target.value} cannot store per-base quality; scores were discarded.",
                )
            )

        if source is SourceFormat.text:
            records = cls._read_plain_text(source_path)
            warnings.append(
                ConversionWarning(
                    code="SYNTHETIC_IDENTIFIERS",
                    message="Plain text has no identifiers, so records were named seq_1, seq_2, …",
                )
            )
        else:
            records = cls._read_with_seqio(source_path, source)

        if not records:
            raise ParseError(
                f"No {source.value} records were found in the uploaded file.",
                details={"source": source.value},
            )

        if target in _ANNOTATION_HUNGRY:
            cls._ensure_molecule_type(records, warnings)

        written = cls._write(records, output_path, target)

        for warning in warnings:
            add_warning(warning.message)

        return ConversionResult(
            filename=f"converted.{TARGET_EXTENSIONS[target]}",
            source_format=source,
            target_format=target,
            records_converted=written,
            warnings=warnings,
        )

    # ── readers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _read_with_seqio(path: Path, source: SourceFormat) -> list[SeqRecord]:
        seqio_name = _SEQIO_NAMES[source.value]
        try:
            return list(SeqIO.parse(str(path), seqio_name))
        except ValueError as exc:
            raise ParseError(
                f"The file is not valid {source.value}: {exc}",
                details={"source": source.value},
            ) from exc

    @staticmethod
    def _read_plain_text(path: Path) -> list[SeqRecord]:
        """Treat each non-empty line as one sequence."""
        records: list[SeqRecord] = []
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, start=1):
                sequence = line.strip()
                if not sequence:
                    continue
                records.append(
                    SeqRecord(
                        Seq(sequence),
                        id=f"seq_{len(records) + 1}",
                        description=f"line {number}",
                    )
                )
        return records

    # ── writers ──────────────────────────────────────────────────────────────

    @classmethod
    def _write(cls, records: list[SeqRecord], output_path: Path, target: TargetFormat) -> int:
        if target is TargetFormat.json:
            return cls._write_json(records, output_path)

        try:
            return int(SeqIO.write(records, str(output_path), _SEQIO_NAMES[target.value]))
        except ValueError as exc:
            raise UnsupportedConversionError(
                f"The records could not be written as {target.value}: {exc}",
                details={"target": target.value},
            ) from exc

    @staticmethod
    def _write_json(records: list[SeqRecord], output_path: Path) -> int:
        """Emit JSON natively — SeqIO has no JSON writer."""
        payload: list[dict[str, Any]] = []
        for record in records:
            sequence = str(record.seq)
            entry: dict[str, Any] = {
                "id": record.id,
                "name": record.name,
                "description": record.description,
                "sequence": sequence,
                "length": len(sequence),
            }
            annotations = {
                key: value
                for key, value in record.annotations.items()
                if isinstance(value, str | int | float | bool)
            }
            if annotations:
                entry["annotations"] = annotations
            quality = record.letter_annotations.get("phred_quality")
            if quality:
                entry["phred_quality"] = list(quality)
            if record.features:
                entry["features"] = [
                    {
                        "type": feature.type,
                        "start": int(feature.location.start),
                        "end": int(feature.location.end),
                        "strand": feature.location.strand,
                    }
                    for feature in record.features
                    if feature.location is not None
                ]
            payload.append(entry)

        output_path.write_text(
            json.dumps({"records": payload, "count": len(payload)}, indent=2),
            encoding="utf-8",
        )
        return len(payload)

    @staticmethod
    def _ensure_molecule_type(records: list[SeqRecord], warnings: list[ConversionWarning]) -> None:
        """Add the annotation GenBank and EMBL writers insist on.

        Without this, ``fasta -> genbank`` fails outright, which is the single
        most common conversion people try.
        """
        patched = 0
        for record in records:
            if record.annotations.get("molecule_type"):
                continue
            alphabet = set(str(record.seq).upper())
            if alphabet and alphabet <= set("ACGUNRYSWKMBDHV-."):
                record.annotations["molecule_type"] = "RNA" if "U" in alphabet else "DNA"
            elif alphabet <= set("ACGTNRYSWKMBDHV-."):
                record.annotations["molecule_type"] = "DNA"
            else:
                record.annotations["molecule_type"] = "protein"
            patched += 1

        if patched:
            warnings.append(
                ConversionWarning(
                    code="MOLECULE_TYPE_INFERRED",
                    message=(
                        f"{patched} record(s) had no molecule_type annotation; it was inferred "
                        "from sequence composition because GenBank and EMBL require it."
                    ),
                )
            )

    # ── consensus ────────────────────────────────────────────────────────────

    @staticmethod
    def derive_consensus(fasta_path: Path, vcf_path: Path, output_path: Path) -> ConsensusResult:
        """Apply a VCF's ALT alleles to a reference FASTA.

        Variants are applied from the end of each sequence backwards so an
        insertion or deletion cannot shift the coordinates of the ones still to
        be applied. Every variant that is not applied is counted and the reason
        reported, rather than being dropped in silence.
        """
        import pysam

        try:
            references = SeqIO.to_dict(SeqIO.parse(str(fasta_path), "fasta"))
        except ValueError as exc:
            raise ParseError(f"The reference FASTA could not be parsed: {exc}") from exc

        if not references:
            raise ParseError("The reference FASTA contains no sequences.")

        by_chromosome: defaultdict[str, list[Any]] = defaultdict(list)
        skipped: defaultdict[str, int] = defaultdict(int)

        try:
            with pysam.VariantFile(str(vcf_path)) as variants:
                for record in variants:
                    if not record.alts:
                        skipped["no_alternate_allele"] += 1
                        continue
                    if record.chrom not in references:
                        skipped["chromosome_not_in_reference"] += 1
                        continue
                    by_chromosome[record.chrom].append(record)
        except (ValueError, OSError) as exc:
            raise ParseError(f"The VCF could not be parsed: {exc}") from exc

        applied = 0
        written = 0

        with output_path.open("w", encoding="utf-8") as sink:
            for seq_id, reference in references.items():
                bases = list(str(reference.seq))
                # Descending position order keeps earlier indices valid.
                for record in sorted(
                    by_chromosome.get(seq_id, ()), key=lambda r: r.pos, reverse=True
                ):
                    index = record.pos - 1
                    ref_allele = record.ref or ""
                    alt_allele = record.alts[0]

                    if index < 0 or index + len(ref_allele) > len(bases):
                        skipped["position_outside_reference"] += 1
                        continue

                    observed = "".join(bases[index : index + len(ref_allele)])
                    if observed.upper() != ref_allele.upper():
                        skipped["reference_allele_mismatch"] += 1
                        continue

                    bases[index : index + len(ref_allele)] = list(alt_allele)
                    applied += 1

                consensus = SeqRecord(
                    Seq("".join(bases)),
                    id=f"{seq_id}_consensus",
                    description=(
                        f"consensus of {seq_id} with "
                        f"{len(by_chromosome.get(seq_id, ()))} variant(s)"
                    ),
                )
                sink.write(consensus.format("fasta"))
                written += 1

        for reason, count in skipped.items():
            add_warning(f"Skipped {count} variant(s): {reason.replace('_', ' ')}.")

        return ConsensusResult(
            records_written=written,
            variants_applied=applied,
            variants_skipped=sum(skipped.values()),
            skipped_reasons=dict(skipped),
        )
