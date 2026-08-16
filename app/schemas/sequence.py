"""Request and response models for the single-sequence endpoints."""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.utils.alphabets import AlphabetEnum

__all__ = [
    "AlphabetEnum",
    "BaseCountResult",
    "GCContentResult",
    "KmerRequest",
    "KmerResult",
    "MotifHit",
    "MotifRequest",
    "MotifResult",
    "SequenceRequest",
    "SequenceResult",
    "TranslationRequest",
    "TranslationTable",
    "ValidationResult",
]


class TranslationTable(IntEnum):
    """NCBI genetic code identifiers supported by Biopython."""

    standard = 1
    vertebrate_mitochondrial = 2
    yeast_mitochondrial = 3
    mold_protozoan_coelenterate_mitochondrial = 4
    invertebrate_mitochondrial = 5
    ciliate_dasycladacean_hexamita_nuclear = 6
    echinoderm_flatworm_mitochondrial = 9
    euplotid_nuclear = 10
    bacterial_archaeal_plant_plastid = 11
    alternative_yeast_nuclear = 12
    ascidian_mitochondrial = 13
    alternative_flatworm_mitochondrial = 14
    chlorophycean_mitochondrial = 16
    trematode_mitochondrial = 21
    scenedesmus_obliquus_mitochondrial = 22
    thraustochytrium_mitochondrial = 23
    pterobranchia_mitochondrial = 24
    candidate_division_sr1_gracilibacteria = 25
    pachysolen_tannophilus_nuclear = 26
    karyorelict_nuclear = 27
    condylostoma_nuclear = 28
    mesodinium_nuclear = 29
    peritrich_nuclear = 30
    blastocrithidia_nuclear = 31
    cephalodiscidae_mitochondrial = 33


class SequenceRequest(BaseModel):
    """A single sequence plus how it should be normalised and validated."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"sequence": "ATGCGTAA", "alphabet": "dna"}}
    )

    sequence: str = Field(
        min_length=1,
        max_length=settings.MAX_SEQUENCE_LENGTH,
        description="The biological sequence. Whitespace is stripped before processing.",
    )
    alphabet: AlphabetEnum | None = Field(
        default=None,
        description="Alphabet to validate against. Omit to auto-detect.",
    )
    uppercase: bool = Field(default=True, description="Uppercase the sequence before processing.")
    remove_whitespace: bool = Field(
        default=True, description="Strip all whitespace, including newlines."
    )


class TranslationRequest(SequenceRequest):
    """Nucleotide-to-protein translation options."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"sequence": "ATGGCCATTGTAATGGGCCGC", "table": 1, "to_stop": True}
        }
    )

    table: TranslationTable = Field(
        default=TranslationTable.standard, description="NCBI genetic code to translate with."
    )
    to_stop: bool = Field(default=False, description="Stop at the first in-frame stop codon.")


class KmerRequest(SequenceRequest):
    """K-mer counting options."""

    model_config = ConfigDict(json_schema_extra={"example": {"sequence": "ACTGACGACTGA", "k": 3}})

    k: int = Field(default=3, ge=1, le=32, description="K-mer length.")
    top: int | None = Field(
        default=None,
        ge=1,
        description="Return only the N most frequent k-mers. Omit to return all of them.",
    )


class MotifRequest(SequenceRequest):
    """Motif search options."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"sequence": "ATGATGATG", "motif": "ATG"}}
    )

    motif: str = Field(min_length=1, max_length=10_000, description="Substring to search for.")
    allow_overlaps: bool = Field(
        default=True,
        description="Count overlapping occurrences. Disable to advance past each match.",
    )


class SequenceResult(BaseModel):
    """A transformed sequence."""

    result: str = Field(description="The resulting sequence.")
    length: int = Field(description="Length of the resulting sequence.")


class GCContentResult(BaseModel):
    """GC composition of a nucleotide sequence."""

    gc_percent: float = Field(description="Percentage of G and C bases, ambiguity codes included.")
    gc_count: int
    at_count: int
    length: int


class BaseCountResult(BaseModel):
    """Per-character frequency of a sequence."""

    counts: dict[str, int] = Field(description="Character frequencies, most frequent first.")
    length: int


class KmerResult(BaseModel):
    """K-mer frequency table."""

    k: int
    total_kmers: int = Field(description="Number of k-mer positions examined.")
    distinct_kmers: int
    kmers: dict[str, int] = Field(description="Counts, ordered from most to least frequent.")


class MotifHit(BaseModel):
    """One motif occurrence, in 0-based half-open coordinates."""

    start: int
    end: int
    match: str


class MotifResult(BaseModel):
    """All motif occurrences within a sequence."""

    motif: str
    count: int
    hits: list[MotifHit]


class ValidationResult(BaseModel):
    """Outcome of checking a sequence against an alphabet."""

    is_valid: bool
    alphabet_detected: AlphabetEnum | None
    invalid_chars: list[str] = Field(default_factory=list)
    ambiguous_chars: list[str] = Field(
        default_factory=list, description="IUPAC ambiguity codes present in the sequence."
    )
    length: int
