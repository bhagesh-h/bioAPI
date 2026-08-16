"""Shared fixtures.

The suite talks to the application through ``httpx.ASGITransport``, so the full
middleware and exception-handling stack is exercised without binding a socket.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import create_app

# ── sample data ───────────────────────────────────────────────────────────────

SIMPLE_FASTA = ">seq1 first\nACGTACGTAC\n>seq2 second\nTTTTGGGGCCCCAAAA\n>seq3 third\nACGT"
WRAPPED_FASTA = ">chr1 reference\nATGCATGCAT\nGCATGCATGC\n"
DUPLICATE_FASTA = ">a\nACGT\n>b\nACGT\n>c\nTTTT"
SIMPLE_FASTQ = (
    "@read1 first\nACGTACGT\n+\nIIIIIIII\n"
    "@read2 second\nGGGGCCCC\n+\n!!!!!!!!\n"
    "@read3 third\nTTTTAAAA\n+\n5555IIII"
)

REFERENCE_FASTA = ">chr1 reference\nATGCATGCATGCATGC\n"
GFF_DOCUMENT = (
    "##gff-version 3\n"
    "chr1\t.\tgene\t1\t4\t.\t+\t.\tID=gene1;Name=alpha\n"
    "chr1\t.\tgene\t5\t8\t.\t-\t.\tID=gene2;Name=beta\n"
    "chr1\t.\texon\t9\t12\t.\t+\t.\tID=exon1\n"
)
VCF_DOCUMENT = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=chr1,length=16>\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
    # Positions are 1-based against ATGCATGCATGCATGC: 1=A, 5=A, 9=A.
    "chr1\t1\t.\tA\tT\t50\tPASS\t.\n"
    "chr1\t5\t.\tA\tAGG\t60\tPASS\t.\n"
    "chr1\t9\t.\tA\tC\t70\tPASS\t.\n"
)
SAM_DOCUMENT = (
    "@HD\tVN:1.6\tSO:coordinate\n"
    "@SQ\tSN:chr1\tLN:100\n"
    "read1\t0\tchr1\t1\t60\t8M\t*\t0\t0\tACGTACGT\tIIIIIIII\n"
    "read2\t4\t*\t0\t0\t*\t*\t0\t0\tTTTTGGGG\tIIIIIIII\n"
)
GENBANK_DOCUMENT = """LOCUS       TESTSEQ                   16 bp    DNA     linear   UNK 01-JAN-2024
DEFINITION  A synthetic record used by the test suite.
ACCESSION   TESTSEQ
VERSION     TESTSEQ.1
KEYWORDS    .
SOURCE      synthetic
  ORGANISM  synthetic
            .
FEATURES             Location/Qualifiers
     source          1..16
                     /organism="synthetic"
ORIGIN
        1 atgcatgcat gcatgc
//
"""


# ── application and client ────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def app() -> FastAPI:
    """One application instance for the whole session."""
    return create_app()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired straight to the ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture
def api_key_required(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Turn on API key enforcement for the duration of one test."""
    key = "test-secret-key"
    monkeypatch.setattr(settings, "API_KEY", key)
    yield key


# ── file fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def fasta_file(tmp_path: Path) -> Path:
    path = tmp_path / "reference.fasta"
    path.write_text(REFERENCE_FASTA, encoding="utf-8")
    return path


@pytest.fixture
def gff_file(tmp_path: Path) -> Path:
    path = tmp_path / "annotations.gff"
    path.write_text(GFF_DOCUMENT, encoding="utf-8")
    return path


@pytest.fixture
def vcf_file(tmp_path: Path) -> Path:
    path = tmp_path / "variants.vcf"
    path.write_text(VCF_DOCUMENT, encoding="utf-8")
    return path


@pytest.fixture
def fastq_file(tmp_path: Path) -> Path:
    path = tmp_path / "reads.fastq"
    path.write_text(SIMPLE_FASTQ + "\n", encoding="utf-8")
    return path


@pytest.fixture
def genbank_file(tmp_path: Path) -> Path:
    path = tmp_path / "record.gb"
    path.write_text(GENBANK_DOCUMENT, encoding="utf-8")
    return path


@pytest.fixture
def sam_file(tmp_path: Path) -> Path:
    path = tmp_path / "alignments.sam"
    path.write_text(SAM_DOCUMENT, encoding="utf-8")
    return path


@pytest.fixture
def bam_file(tmp_path: Path, sam_file: Path) -> Path:
    """A real BAM, built from the SAM fixture with pysam."""
    import pysam

    path = tmp_path / "alignments.bam"
    with (
        pysam.AlignmentFile(str(sam_file), "r") as source,
        pysam.AlignmentFile(str(path), "wb", header=source.header) as sink,
    ):
        for read in source:
            sink.write(read)
    return path
