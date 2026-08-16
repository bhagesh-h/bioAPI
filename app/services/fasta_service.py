"""FASTA document utilities that operate entirely in memory."""

from __future__ import annotations

import random
from collections import Counter

from app.core.context import add_warning
from app.core.errors import BioAPIError, FastaParseError
from app.schemas.fasta import (
    ConvertCaseRequest,
    ExtractSubsequenceRequest,
    FastaRecordSummary,
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
from app.utils.alphabets import DNA_BASES, NUCLEOTIDE_AMBIGUITY
from app.utils.parsers import FastaRecord, parse_fasta, render_fasta

_GC_CHARS = frozenset("GCS")


def _n50(lengths: list[int]) -> int:
    """Length at which half of all bases lie in sequences of that size or longer."""
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


def _gc_percent(sequence: str) -> float:
    if not sequence:
        return 0.0
    upper = sequence.upper()
    return round(sum(1 for char in upper if char in _GC_CHARS) / len(upper) * 100, 4)


class FastaService:
    """Stateless transformations of a FASTA document."""

    @staticmethod
    def shorten_headers(request: ShortenHeadersRequest) -> FastaResult:
        """Truncate each header to ``n`` characters, warning about collisions."""
        records = parse_fasta(request.fasta_string)
        shortened: list[FastaRecord] = []
        for record in records:
            truncated = record.header[: request.n]
            identifier, _, description = truncated.partition(" ")
            shortened.append(FastaRecord(identifier, description.strip(), record.sequence))

        duplicates = [
            identifier
            for identifier, count in Counter(r.identifier for r in shortened).items()
            if count > 1
        ]
        if duplicates:
            add_warning(
                f"Truncation produced duplicate identifiers: {', '.join(sorted(duplicates)[:10])}."
            )

        return FastaResult(
            fasta_string=render_fasta(shortened, request.line_width),
            num_sequences=len(shortened),
        )

    @staticmethod
    def get_n_sequences(request: GetNSequencesRequest) -> FastaResult:
        records = parse_fasta(request.fasta_string)
        if request.n > len(records):
            add_warning(
                f"Requested {request.n} sequences but the document holds {len(records)}; "
                "returning all of them."
            )
        selected = records[: request.n]
        return FastaResult(
            fasta_string=render_fasta(selected, request.line_width),
            num_sequences=len(selected),
        )

    @staticmethod
    def filter_by_length(request: FilterByLengthRequest) -> FastaResult:
        records = parse_fasta(request.fasta_string)
        ceiling = request.max_length if request.max_length is not None else None
        kept = [
            record
            for record in records
            if len(record.sequence) >= request.min_length
            and (ceiling is None or len(record.sequence) <= ceiling)
        ]
        if not kept:
            add_warning("No sequence satisfied the length filter; the result is empty.")
        return FastaResult(
            fasta_string=render_fasta(kept, request.line_width) if kept else "",
            num_sequences=len(kept),
        )

    @staticmethod
    def extract_subsequence(request: ExtractSubsequenceRequest) -> FastaResult:
        """Slice ``[start, end]`` (1-based, inclusive) from every sequence."""
        records = parse_fasta(request.fasta_string)
        sliced: list[FastaRecord] = []
        skipped: list[str] = []

        for record in records:
            if request.end > len(record.sequence):
                if request.skip_short:
                    skipped.append(record.identifier)
                    continue
                raise BioAPIError(
                    f"Sequence '{record.identifier}' is {len(record.sequence)} bases long, "
                    f"shorter than the requested end position {request.end}. "
                    "Set skip_short=true to drop such sequences instead.",
                    details={
                        "sequence_id": record.identifier,
                        "sequence_length": len(record.sequence),
                        "requested_end": request.end,
                    },
                )
            sliced.append(
                FastaRecord(
                    identifier=record.identifier,
                    description=f"{record.description} [{request.start}-{request.end}]".strip(),
                    sequence=record.sequence[request.start - 1 : request.end],
                )
            )

        if skipped:
            add_warning(
                f"Skipped {len(skipped)} sequence(s) shorter than position {request.end}: "
                f"{', '.join(skipped[:10])}."
            )

        return FastaResult(
            fasta_string=render_fasta(sliced, request.line_width) if sliced else "",
            num_sequences=len(sliced),
        )

    @staticmethod
    def sample_sequences(request: SampleSequencesRequest) -> FastaResult:
        """Draw ``n`` sequences at random, optionally with a reproducible seed."""
        records = parse_fasta(request.fasta_string)
        if request.n > len(records):
            add_warning(
                f"Requested {request.n} samples but the document holds {len(records)}; "
                "returning all of them."
            )
        rng = random.Random(request.seed)
        sampled = rng.sample(records, min(request.n, len(records)))
        return FastaResult(
            fasta_string=render_fasta(sampled, request.line_width),
            num_sequences=len(sampled),
        )

    @staticmethod
    def split(request: SplitFastaRequest) -> SplitFastaResult:
        """Split into ``n`` chunks or into chunks of ``size`` sequences."""
        records = parse_fasta(request.fasta_string)
        total = len(records)

        if request.n is not None:
            if request.n > total:
                raise BioAPIError(
                    f"Cannot split {total} sequence(s) into {request.n} chunks.",
                    details={"sequences": total, "requested_chunks": request.n},
                )
            chunk_size = -(-total // request.n)  # ceiling division
        else:
            assert request.size is not None
            chunk_size = request.size

        chunks: list[str] = []
        counts: list[int] = []
        for start in range(0, total, chunk_size):
            group = records[start : start + chunk_size]
            chunks.append(render_fasta(group, request.line_width))
            counts.append(len(group))

        if request.n is not None and len(chunks) != request.n:
            add_warning(
                f"Requested {request.n} chunks; {len(chunks)} were produced because "
                f"{total} sequences do not divide evenly."
            )

        return SplitFastaResult(chunks=chunks, num_chunks=len(chunks), sequences_per_chunk=counts)

    @staticmethod
    def merge(request: MergeFastaRequest) -> FastaResult:
        """Concatenate several FASTA documents into one."""
        merged: list[FastaRecord] = []
        for index, document in enumerate(request.fasta_strings):
            try:
                merged.extend(parse_fasta(document))
            except FastaParseError as exc:
                raise FastaParseError(
                    f"fasta_strings[{index}]: {exc.message}",
                    details={"index": index, **exc.details},
                ) from exc

        if request.deduplicate_ids:
            merged = FastaService._disambiguate_ids(merged)
        else:
            duplicates = [
                identifier
                for identifier, count in Counter(r.identifier for r in merged).items()
                if count > 1
            ]
            if duplicates:
                add_warning(
                    f"{len(duplicates)} identifier(s) appear in more than one input; "
                    "set deduplicate_ids=true to make them unique."
                )

        return FastaResult(
            fasta_string=render_fasta(merged, request.line_width),
            num_sequences=len(merged),
        )

    @staticmethod
    def convert_case(request: ConvertCaseRequest) -> FastaResult:
        records = parse_fasta(request.fasta_string)
        transform = str.upper if request.case == "upper" else str.lower
        converted = [
            FastaRecord(r.identifier, r.description, transform(r.sequence)) for r in records
        ]
        return FastaResult(
            fasta_string=render_fasta(converted, request.line_width),
            num_sequences=len(converted),
        )

    @staticmethod
    def remove_unknown_chars(request: RemoveUnknownCharsRequest) -> FastaResult:
        """Strip characters outside the accepted nucleotide set."""
        records = parse_fasta(request.fasta_string)
        allowed = set(DNA_BASES)
        if request.keep_ambiguity_codes:
            allowed |= set(NUCLEOTIDE_AMBIGUITY)
        allowed |= {char.lower() for char in allowed}

        cleaned: list[FastaRecord] = []
        removed_total = 0
        for record in records:
            kept = "".join(char for char in record.sequence if char in allowed)
            removed_total += len(record.sequence) - len(kept)
            cleaned.append(FastaRecord(record.identifier, record.description, kept))

        if removed_total:
            add_warning(f"Removed {removed_total} character(s) outside the accepted alphabet.")

        return FastaResult(
            fasta_string=render_fasta(cleaned, request.line_width),
            num_sequences=len(cleaned),
        )

    @staticmethod
    def rename_sequences(request: RenameSequencesRequest) -> FastaResult:
        records = parse_fasta(request.fasta_string)
        renamed: list[FastaRecord] = []
        applied = 0
        for record in records:
            new_id = request.rename_map.get(record.identifier)
            if new_id is None:
                renamed.append(record)
                continue
            applied += 1
            renamed.append(FastaRecord(new_id, record.description, record.sequence))

        unused = set(request.rename_map) - {r.identifier for r in records}
        if unused:
            add_warning(
                f"{len(unused)} identifier(s) in rename_map were not found: "
                f"{', '.join(sorted(unused)[:10])}."
            )

        return FastaResult(
            fasta_string=render_fasta(renamed, request.line_width),
            num_sequences=len(renamed),
        )

    @staticmethod
    def modify_descriptions(request: ModifyDescriptionsRequest) -> FastaResult:
        records = parse_fasta(request.fasta_string)
        updated = [
            FastaRecord(
                r.identifier,
                request.description_map.get(r.identifier, r.description),
                r.sequence,
            )
            for r in records
        ]

        unused = set(request.description_map) - {r.identifier for r in records}
        if unused:
            add_warning(
                f"{len(unused)} identifier(s) in description_map were not found: "
                f"{', '.join(sorted(unused)[:10])}."
            )

        return FastaResult(
            fasta_string=render_fasta(updated, request.line_width),
            num_sequences=len(updated),
        )

    @staticmethod
    def find_unique(request: FastaRequest) -> FastaResult:
        """Keep the first record of each distinct sequence."""
        records = parse_fasta(request.fasta_string)
        seen: set[str] = set()
        unique: list[FastaRecord] = []
        for record in records:
            key = record.sequence.upper()
            if key in seen:
                continue
            seen.add(key)
            unique.append(record)

        dropped = len(records) - len(unique)
        if dropped:
            add_warning(f"Dropped {dropped} duplicate sequence(s).")

        return FastaResult(
            fasta_string=render_fasta(unique, request.line_width),
            num_sequences=len(unique),
        )

    @staticmethod
    def extract_ids(request: FastaRequest) -> SequenceIdsResult:
        records = parse_fasta(request.fasta_string)
        ids = [record.identifier for record in records]
        return SequenceIdsResult(ids=ids, count=len(ids))

    @staticmethod
    def stats(request: FastaRequest) -> FastaStatsResult:
        """Summarise composition without writing anything to disk."""
        records = parse_fasta(request.fasta_string)
        lengths = [len(record.sequence) for record in records]
        joined = "".join(record.sequence.upper() for record in records)
        total = len(joined)
        ambiguous = sum(1 for char in joined if char in NUCLEOTIDE_AMBIGUITY)

        return FastaStatsResult(
            num_sequences=len(records),
            total_bases=total,
            min_length=min(lengths),
            max_length=max(lengths),
            avg_length=round(sum(lengths) / len(lengths), 2),
            n50=_n50(lengths),
            gc_percent=_gc_percent(joined),
            ambiguous_chars=ambiguous,
            records=[
                FastaRecordSummary(
                    id=record.identifier,
                    length=len(record.sequence),
                    gc_percent=_gc_percent(record.sequence),
                    ambiguous_chars=sum(
                        1 for char in record.sequence.upper() if char in NUCLEOTIDE_AMBIGUITY
                    ),
                )
                for record in records
            ],
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _disambiguate_ids(records: list[FastaRecord]) -> list[FastaRecord]:
        """Suffix repeated identifiers with _2, _3, … in order of appearance."""
        seen: Counter[str] = Counter()
        result: list[FastaRecord] = []
        for record in records:
            seen[record.identifier] += 1
            occurrence = seen[record.identifier]
            identifier = (
                record.identifier if occurrence == 1 else f"{record.identifier}_{occurrence}"
            )
            result.append(FastaRecord(identifier, record.description, record.sequence))
        return result
