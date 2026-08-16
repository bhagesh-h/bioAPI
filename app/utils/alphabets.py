"""Sequence alphabets and validation.

Real-world FASTA files routinely carry IUPAC ambiguity codes (``R`` for A/G,
``N`` for any base, and so on). Restricting DNA to ``ACGT`` rejects perfectly
valid data, so the ambiguity codes are part of the accepted alphabet and the
caller is told, through a warning, when a sequence relies on them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

# Unambiguous bases.
DNA_BASES = frozenset("ACGT")
RNA_BASES = frozenset("ACGU")

# IUPAC nucleotide ambiguity codes, plus the gap characters used in alignments.
NUCLEOTIDE_AMBIGUITY = frozenset("RYSWKMBDHVN")
GAP_CHARACTERS = frozenset("-.")

DNA_ALPHABET = DNA_BASES | NUCLEOTIDE_AMBIGUITY | GAP_CHARACTERS
RNA_ALPHABET = RNA_BASES | NUCLEOTIDE_AMBIGUITY | GAP_CHARACTERS

# The 20 standard amino acids.
PROTEIN_RESIDUES = frozenset("ACDEFGHIKLMNPQRSTVWY")
# B=D/N, Z=E/Q, J=I/L, X=any, U=selenocysteine, O=pyrrolysine, *=stop.
PROTEIN_AMBIGUITY = frozenset("BZJXUO*")
PROTEIN_ALPHABET = PROTEIN_RESIDUES | PROTEIN_AMBIGUITY | GAP_CHARACTERS


class AlphabetEnum(StrEnum):
    """Alphabet a sequence is expected to conform to."""

    dna = "dna"
    rna = "rna"
    protein = "protein"


_ALPHABETS: dict[AlphabetEnum, frozenset[str]] = {
    AlphabetEnum.dna: DNA_ALPHABET,
    AlphabetEnum.rna: RNA_ALPHABET,
    AlphabetEnum.protein: PROTEIN_ALPHABET,
}

_AMBIGUOUS: dict[AlphabetEnum, frozenset[str]] = {
    AlphabetEnum.dna: NUCLEOTIDE_AMBIGUITY,
    AlphabetEnum.rna: NUCLEOTIDE_AMBIGUITY,
    AlphabetEnum.protein: PROTEIN_AMBIGUITY,
}


class AlphabetCheck(NamedTuple):
    """Outcome of validating a sequence against an alphabet."""

    is_valid: bool
    alphabet: AlphabetEnum | None
    invalid_chars: list[str]
    ambiguous_chars: list[str]


def detect_alphabet(sequence: str) -> AlphabetEnum | None:
    """Guess the alphabet of an already-uppercased sequence.

    DNA is tried first, then RNA, then protein. A sequence of only ``ACG``
    characters is ambiguous between DNA and RNA by definition; DNA wins because
    it is overwhelmingly the more common input.
    """
    if not sequence:
        return None
    used = set(sequence)
    for candidate in (AlphabetEnum.dna, AlphabetEnum.rna, AlphabetEnum.protein):
        if used <= _ALPHABETS[candidate]:
            return candidate
    return None


def check_alphabet(sequence: str, expected: AlphabetEnum | None = None) -> AlphabetCheck:
    """Validate ``sequence`` against ``expected``, or auto-detect when omitted.

    ``sequence`` is expected to be uppercased and whitespace-free already; use
    :func:`clean_sequence` first.
    """
    if not sequence:
        return AlphabetCheck(False, None, [], [])

    used = set(sequence)

    if expected is not None:
        allowed = _ALPHABETS[expected]
        invalid = sorted(used - allowed)
        ambiguous = sorted(used & _AMBIGUOUS[expected])
        return AlphabetCheck(not invalid, expected, invalid, ambiguous)

    detected = detect_alphabet(sequence)
    if detected is None:
        # Report against the widest alphabet so the message is actionable.
        return AlphabetCheck(False, None, sorted(used - PROTEIN_ALPHABET), [])
    return AlphabetCheck(True, detected, [], sorted(used & _AMBIGUOUS[detected]))


def clean_sequence(sequence: str, *, uppercase: bool = True, strip_whitespace: bool = True) -> str:
    """Normalise a raw sequence string before validation or computation."""
    result = sequence
    if strip_whitespace:
        result = "".join(result.split())
    if uppercase:
        result = result.upper()
    return result
