"""Single-sequence operations built on Biopython."""

from __future__ import annotations

from collections import Counter

from Bio.Seq import Seq

from app.core.context import add_warning
from app.core.errors import SequenceValidationError
from app.schemas.sequence import (
    BaseCountResult,
    GCContentResult,
    KmerRequest,
    KmerResult,
    MotifHit,
    MotifRequest,
    MotifResult,
    SequenceRequest,
    SequenceResult,
    TranslationRequest,
    ValidationResult,
)
from app.utils.alphabets import AlphabetEnum, check_alphabet, clean_sequence

# G, C and the ambiguity code S (G or C) all count towards GC content.
_GC_CHARS = frozenset("GCS")
_AT_CHARS = frozenset("ATUW")


class SequenceService:
    """Stateless operations on a single sequence."""

    @staticmethod
    def _prepare(request: SequenceRequest) -> str:
        """Normalise and validate a sequence, or raise with a precise message."""
        sequence = clean_sequence(
            request.sequence,
            uppercase=request.uppercase,
            strip_whitespace=request.remove_whitespace,
        )
        # Validation is always case-insensitive, even when the caller asked to
        # preserve case in the output.
        check = check_alphabet(sequence.upper(), request.alphabet)

        if not check.is_valid:
            expected = request.alphabet.value if request.alphabet else "any known alphabet"
            raise SequenceValidationError(
                f"Sequence contains characters outside {expected}: "
                f"{', '.join(check.invalid_chars)}",
                details={
                    "invalid_characters": check.invalid_chars,
                    "expected_alphabet": expected,
                },
            )

        if check.ambiguous_chars:
            add_warning(
                "Sequence contains IUPAC ambiguity codes "
                f"({', '.join(check.ambiguous_chars)}); results treat them literally."
            )
        return sequence

    @classmethod
    def reverse(cls, request: SequenceRequest) -> SequenceResult:
        sequence = cls._prepare(request)
        return SequenceResult(result=sequence[::-1], length=len(sequence))

    @classmethod
    def complement(cls, request: SequenceRequest) -> SequenceResult:
        sequence = cls._prepare(request)
        cls._reject_protein(request, "complement")
        result = str(
            Seq(sequence).complement_rna() if cls._is_rna(sequence) else Seq(sequence).complement()
        )
        return SequenceResult(result=result, length=len(result))

    @classmethod
    def reverse_complement(cls, request: SequenceRequest) -> SequenceResult:
        sequence = cls._prepare(request)
        cls._reject_protein(request, "reverse-complement")
        seq = Seq(sequence)
        result = str(
            seq.reverse_complement_rna() if cls._is_rna(sequence) else seq.reverse_complement()
        )
        return SequenceResult(result=result, length=len(result))

    @classmethod
    def transcribe(cls, request: SequenceRequest) -> SequenceResult:
        sequence = cls._prepare(request)
        cls._reject_protein(request, "transcribe")
        result = str(Seq(sequence).transcribe())
        return SequenceResult(result=result, length=len(result))

    @classmethod
    def back_transcribe(cls, request: SequenceRequest) -> SequenceResult:
        sequence = cls._prepare(request)
        cls._reject_protein(request, "back-transcribe")
        result = str(Seq(sequence).back_transcribe())
        return SequenceResult(result=result, length=len(result))

    @classmethod
    def translate(cls, request: TranslationRequest) -> SequenceResult:
        sequence = cls._prepare(request)
        cls._reject_protein(request, "translate")

        remainder = len(sequence) % 3
        if remainder:
            add_warning(
                f"Sequence length {len(sequence)} is not a multiple of three; "
                f"the trailing {remainder} base(s) were not translated."
            )
            sequence = sequence[: len(sequence) - remainder]

        if not sequence:
            raise SequenceValidationError(
                "Sequence is shorter than one codon, so there is nothing to translate."
            )

        result = str(Seq(sequence).translate(table=int(request.table), to_stop=request.to_stop))
        return SequenceResult(result=result, length=len(result))

    @classmethod
    def gc_content(cls, request: SequenceRequest) -> GCContentResult:
        sequence = cls._prepare(request)
        cls._reject_protein(request, "GC content")
        upper = sequence.upper()
        gc_count = sum(1 for char in upper if char in _GC_CHARS)
        at_count = sum(1 for char in upper if char in _AT_CHARS)
        length = len(upper)
        percent = round(gc_count / length * 100, 4) if length else 0.0
        return GCContentResult(
            gc_percent=percent, gc_count=gc_count, at_count=at_count, length=length
        )

    @classmethod
    def count_bases(cls, request: SequenceRequest) -> BaseCountResult:
        sequence = cls._prepare(request)
        counts = Counter(sequence)
        ordered = dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
        return BaseCountResult(counts=ordered, length=len(sequence))

    @classmethod
    def kmer(cls, request: KmerRequest) -> KmerResult:
        sequence = cls._prepare(request)
        if request.k > len(sequence):
            raise SequenceValidationError(
                f"k={request.k} exceeds the sequence length of {len(sequence)}.",
                details={"k": request.k, "sequence_length": len(sequence)},
            )

        positions = len(sequence) - request.k + 1
        counts = Counter(sequence[i : i + request.k] for i in range(positions))
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        distinct = len(ordered)

        if request.top is not None and request.top < distinct:
            ordered = ordered[: request.top]
            add_warning(f"Returning the top {request.top} of {distinct} distinct k-mers.")

        return KmerResult(
            k=request.k,
            total_kmers=positions,
            distinct_kmers=distinct,
            kmers=dict(ordered),
        )

    @classmethod
    def find_motif(cls, request: MotifRequest) -> MotifResult:
        sequence = cls._prepare(request)

        motif = request.motif
        if request.remove_whitespace:
            motif = "".join(motif.split())
        if request.uppercase:
            motif = motif.upper()

        if not motif:
            raise SequenceValidationError("The motif is empty once whitespace is removed.")
        if len(motif) > len(sequence):
            return MotifResult(motif=motif, count=0, hits=[])

        hits: list[MotifHit] = []
        step = 1 if request.allow_overlaps else len(motif)
        cursor = 0
        while True:
            found = sequence.find(motif, cursor)
            if found == -1:
                break
            hits.append(MotifHit(start=found, end=found + len(motif), match=motif))
            cursor = found + step

        return MotifResult(motif=motif, count=len(hits), hits=hits)

    @classmethod
    def validate(cls, request: SequenceRequest) -> ValidationResult:
        """Report on a sequence without rejecting it — this endpoint never 400s."""
        sequence = clean_sequence(
            request.sequence,
            uppercase=True,
            strip_whitespace=request.remove_whitespace,
        )
        check = check_alphabet(sequence, request.alphabet)
        return ValidationResult(
            is_valid=check.is_valid,
            alphabet_detected=check.alphabet,
            invalid_chars=check.invalid_chars,
            ambiguous_chars=check.ambiguous_chars,
            length=len(sequence),
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _is_rna(sequence: str) -> bool:
        upper = sequence.upper()
        return "U" in upper and "T" not in upper

    @staticmethod
    def _reject_protein(request: SequenceRequest, operation: str) -> None:
        """Refuse nucleotide-only operations on a declared protein sequence."""
        if request.alphabet is AlphabetEnum.protein:
            raise SequenceValidationError(
                f"{operation} is a nucleotide operation and cannot be applied to a protein "
                "sequence.",
                details={"operation": operation, "alphabet": "protein"},
            )
