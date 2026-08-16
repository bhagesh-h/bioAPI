"""Unit tests for the helper layer, exercised without going through HTTP."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.context import RequestContext, add_warning, get_request_id, get_warnings
from app.core.errors import FastaParseError, FastqParseError
from app.utils.alphabets import (
    AlphabetEnum,
    check_alphabet,
    clean_sequence,
    detect_alphabet,
)
from app.utils.detection import (
    Confidence,
    FileFormat,
    detect_format,
    format_from_extension,
    sniff_content,
)
from app.utils.parsers import parse_fasta, parse_fastq, render_fasta, render_fastq

# ── alphabets ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        ("ACGT", AlphabetEnum.dna),
        ("ACGU", AlphabetEnum.rna),
        ("ACGTN", AlphabetEnum.dna),
        ("MKWVLF", AlphabetEnum.protein),
        ("ACGT!!", None),
    ],
)
def test_detect_alphabet(sequence: str, expected: AlphabetEnum | None) -> None:
    assert detect_alphabet(sequence) is expected


def test_ambiguity_codes_are_valid_dna() -> None:
    check = check_alphabet("ACGTRYN", AlphabetEnum.dna)
    assert check.is_valid
    assert check.ambiguous_chars == ["N", "R", "Y"]


def test_invalid_characters_are_listed() -> None:
    check = check_alphabet("ACGTZ", AlphabetEnum.dna)
    assert not check.is_valid
    assert check.invalid_chars == ["Z"]


def test_empty_sequence_is_not_valid() -> None:
    assert check_alphabet("") == (False, None, [], [])


def test_clean_sequence() -> None:
    assert clean_sequence(" ac gt\n") == "ACGT"
    assert clean_sequence(" ac gt\n", uppercase=False) == "acgt"
    assert clean_sequence("ac gt", strip_whitespace=False) == "AC GT"


# ── FASTA parsing ─────────────────────────────────────────────────────────────


def test_parse_fasta_joins_wrapped_lines() -> None:
    records = parse_fasta(">a desc\nACGT\nTTTT\n")
    assert len(records) == 1
    assert records[0].identifier == "a"
    assert records[0].description == "desc"
    assert records[0].sequence == "ACGTTTTT"


def test_parse_fasta_tolerates_blank_lines() -> None:
    assert len(parse_fasta(">a\nACGT\n\n>b\nTTTT\n")) == 2


def test_parse_fasta_rejects_data_before_a_header() -> None:
    with pytest.raises(FastaParseError, match="before any"):
        parse_fasta("ACGT\n>a\nACGT")


def test_parse_fasta_rejects_an_empty_document() -> None:
    with pytest.raises(FastaParseError, match="empty"):
        parse_fasta("   \n  ")


def test_render_fasta_wraps_at_the_requested_width() -> None:
    records = parse_fasta(">a\n" + "A" * 10)
    assert render_fasta(records, 4) == ">a\nAAAA\nAAAA\nAA"


def test_render_fasta_can_emit_one_line_per_sequence() -> None:
    records = parse_fasta(">a\n" + "A" * 10)
    assert render_fasta(records, 0) == ">a\n" + "A" * 10


# ── FASTQ parsing ─────────────────────────────────────────────────────────────


def test_parse_fastq_round_trip() -> None:
    document = "@r1 note\nACGT\n+\nIIII"
    records = parse_fastq(document)
    assert records[0].identifier == "r1"
    assert records[0].description == "note"
    assert render_fastq(records) == document


def test_mean_quality() -> None:
    read = parse_fastq("@r1\nACGT\n+\nIIII")[0]
    assert read.mean_quality() == 40.0
    assert read.phred_scores() == [40, 40, 40, 40]


def test_parse_fastq_rejects_a_bad_line_count() -> None:
    with pytest.raises(FastqParseError, match="multiple of four"):
        parse_fastq("@r1\nACGT\n+")


def test_parse_fastq_rejects_an_empty_sequence() -> None:
    with pytest.raises(FastqParseError, match="sequence is empty"):
        parse_fastq("@r1\n\n+\n\n@r2\nACGT\n+\nIIII")


def test_parse_fastq_tolerates_trailing_blank_lines() -> None:
    assert len(parse_fastq("@r1\nACGT\n+\nIIII\n\n\n")) == 1


# ── format detection ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("x.fasta", FileFormat.fasta),
        ("x.fa", FileFormat.fasta),
        ("x.fq", FileFormat.fastq),
        ("x.gb", FileFormat.genbank),
        ("x.vcf.gz", FileFormat.vcf),
        ("x.gff3", FileFormat.gff),
        ("x.unknownext", FileFormat.unknown),
        (None, FileFormat.unknown),
    ],
)
def test_format_from_extension(filename: str | None, expected: FileFormat) -> None:
    assert format_from_extension(filename) is expected


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (b">seq1\nACGT\n", FileFormat.fasta),
        (b"@r1\nACGT\n+\nIIII\n", FileFormat.fastq),
        (b"##fileformat=VCFv4.2\n", FileFormat.vcf),
        (b"##gff-version 3\n", FileFormat.gff),
        (b"LOCUS       X   16 bp\n", FileFormat.genbank),
        (b"\x1f\x8b\x08\x04", FileFormat.bam),
        (b"@HD\tVN:1.6\n", FileFormat.sam),
        (b"just words\n", None),
        (b"", None),
    ],
)
def test_sniff_content(head: bytes, expected: FileFormat | None) -> None:
    assert sniff_content(head) is expected


def test_gtf_is_told_apart_from_gff_by_its_attributes() -> None:
    gtf = b'chr1\tsrc\texon\t1\t100\t.\t+\t.\tgene_id "G1"; transcript_id "T1";\n'
    assert sniff_content(gtf) is FileFormat.gtf

    gff = b"chr1\tsrc\texon\t1\t100\t.\t+\t.\tID=exon1;Parent=G1\n"
    assert sniff_content(gff) is FileFormat.gff


def test_detection_confidence_levels() -> None:
    agree = detect_format("x.fasta", b">a\nACGT")
    assert agree.confidence is Confidence.high

    content_only = detect_format("x.txt", b">a\nACGT")
    assert content_only.format is FileFormat.fasta
    assert content_only.confidence is Confidence.high

    conflict = detect_format("x.vcf", b">a\nACGT")
    assert conflict.format is FileFormat.fasta
    assert conflict.confidence is Confidence.medium

    extension_only = detect_format("x.vcf", b"nothing recognisable here")
    assert extension_only.format is FileFormat.vcf
    assert extension_only.confidence is Confidence.low

    nothing = detect_format("x.mystery", b"nothing recognisable here")
    assert nothing.format is FileFormat.text
    assert nothing.confidence is Confidence.low


# ── request context ───────────────────────────────────────────────────────────


def test_request_context_scopes_warnings() -> None:
    assert get_request_id() is None

    with RequestContext("abc-123"):
        assert get_request_id() == "abc-123"
        add_warning("first")
        add_warning("first")  # duplicates collapse
        add_warning("second")
        assert get_warnings() == ["first", "second"]

    assert get_request_id() is None
    assert get_warnings() == []


# ── settings ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("*", ["*"]),
        ("http://a.test,http://b.test", ["http://a.test", "http://b.test"]),
        ('["http://a.test"]', ["http://a.test"]),
    ],
)
def test_cors_origins_accept_several_notations(raw: str, expected: list[str]) -> None:
    """A bare '*' used to crash pydantic-settings' JSON decoding."""
    settings = Settings(BACKEND_CORS_ORIGINS=raw, _env_file=None)
    assert expected == settings.BACKEND_CORS_ORIGINS


def test_upload_limit_is_exposed_in_bytes() -> None:
    settings = Settings(MAX_UPLOAD_SIZE_MB=2, _env_file=None)
    assert settings.max_upload_size_bytes == 2 * 1024 * 1024


def test_error_details_are_hidden_in_production() -> None:
    assert not Settings(DEBUG=True, ENVIRONMENT="production", _env_file=None).expose_error_details
    assert Settings(DEBUG=True, ENVIRONMENT="development", _env_file=None).expose_error_details
