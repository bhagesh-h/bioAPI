"""Format conversion, the capability matrix, and consensus generation."""

from __future__ import annotations

import json
from pathlib import Path

from httpx import AsyncClient

from tests.conftest import SIMPLE_FASTA, SIMPLE_FASTQ

BASE = "/api/v1/conversions"


async def test_formats_endpoint_publishes_the_matrix(client: AsyncClient) -> None:
    response = await client.get("/api/v1/formats")
    assert response.status_code == 200

    data = response.json()["data"]
    assert "fasta" in data["conversion_sources"]
    assert "json" in data["conversion_targets"]
    assert data["unsupported_pairs"]["fasta->fastq"]


async def test_text_to_fasta(client: AsyncClient) -> None:
    files = {"file": ("lines.txt", b"ATGC\nCGTA\n", "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=text&target_format=fasta", files=files
    )
    assert response.status_code == 200
    assert response.headers["x-records-converted"] == "2"

    body = response.text
    assert ">seq_1" in body
    assert "ATGC" in body


async def test_fastq_to_fasta_warns_about_dropped_quality(client: AsyncClient) -> None:
    files = {"file": ("reads.fastq", SIMPLE_FASTQ.encode(), "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=fastq&target_format=fasta", files=files
    )
    assert response.status_code == 200
    assert response.headers["x-records-converted"] == "3"
    assert response.headers["x-conversion-warnings"] == "1"


async def test_fasta_to_genbank_infers_molecule_type(client: AsyncClient) -> None:
    """SeqIO refuses to write GenBank without molecule_type; this used to fail."""
    files = {"file": ("sample.fasta", SIMPLE_FASTA.encode(), "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=fasta&target_format=genbank", files=files
    )
    assert response.status_code == 200
    assert response.headers["x-records-converted"] == "3"
    assert "LOCUS" in response.text
    assert "DNA" in response.text


async def test_fasta_to_json_is_produced_natively(client: AsyncClient) -> None:
    """SeqIO has no JSON writer, so the previous implementation always failed."""
    files = {"file": ("sample.fasta", SIMPLE_FASTA.encode(), "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=fasta&target_format=json", files=files
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")

    document = json.loads(response.text)
    assert document["count"] == 3
    assert document["records"][0]["id"] == "seq1"
    assert document["records"][0]["sequence"] == "ACGTACGTAC"


async def test_fastq_to_json_includes_quality(client: AsyncClient) -> None:
    files = {"file": ("reads.fastq", SIMPLE_FASTQ.encode(), "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=fastq&target_format=json", files=files
    )
    document = json.loads(response.text)
    assert document["records"][0]["phred_quality"][0] == 40


async def test_genbank_to_fasta(client: AsyncClient, genbank_file: Path) -> None:
    files = {"file": ("record.gb", genbank_file.read_bytes(), "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=genbank&target_format=fasta", files=files
    )
    assert response.status_code == 200
    assert response.text.startswith(">TESTSEQ")


async def test_fasta_to_tab(client: AsyncClient) -> None:
    files = {"file": ("sample.fasta", SIMPLE_FASTA.encode(), "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=fasta&target_format=tab", files=files
    )
    assert response.status_code == 200
    assert response.text.startswith("seq1\tACGTACGTAC")


async def test_fasta_to_fastq_is_rejected_with_a_reason(client: AsyncClient) -> None:
    files = {"file": ("sample.fasta", SIMPLE_FASTA.encode(), "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=fasta&target_format=fastq", files=files
    )
    assert response.status_code == 400

    body = response.json()
    assert body["error"]["code"] == "UNSUPPORTED_CONVERSION"
    assert "quality" in body["message"]
    assert "genbank" in body["error"]["details"]["supported_targets"]


async def test_identical_source_and_target_is_rejected(client: AsyncClient) -> None:
    files = {"file": ("sample.fasta", SIMPLE_FASTA.encode(), "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=fasta&target_format=fasta", files=files
    )
    assert response.status_code == 400
    assert "nothing to convert" in response.json()["message"]


async def test_unknown_format_fails_schema_validation(client: AsyncClient) -> None:
    files = {"file": ("sample.fasta", SIMPLE_FASTA.encode(), "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=bam&target_format=fasta", files=files
    )
    assert response.status_code == 422


async def test_conversion_of_an_unparseable_file(client: AsyncClient) -> None:
    files = {"file": ("broken.fastq", b"this is not fastq at all\n", "text/plain")}
    response = await client.post(
        f"{BASE}/convert?source_format=fastq&target_format=fasta", files=files
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] in {"PARSE_ERROR", "INVALID_FASTQ"}


async def test_consensus_applies_snps_and_indels(
    client: AsyncClient, fasta_file: Path, vcf_file: Path
) -> None:
    files = {
        "reference_fasta": ("reference.fasta", fasta_file.read_bytes(), "text/plain"),
        "vcf_file": ("variants.vcf", vcf_file.read_bytes(), "text/plain"),
    }
    response = await client.post(f"{BASE}/vcf-to-fasta", files=files)
    assert response.status_code == 200
    assert response.headers["x-records-converted"] == "1"
    assert response.headers["x-variants-applied"] == "3"
    assert response.headers["x-variants-skipped"] == "0"

    body = response.text
    assert ">chr1_consensus" in body
    sequence = "".join(body.splitlines()[1:])
    # ATGCATGCATGCATGC with T at 1, A->AGG at 5, T->C at 9.
    assert sequence == "TTGCAGGTGCCTGCATGC"


async def test_consensus_reports_mismatched_reference_alleles(
    client: AsyncClient, fasta_file: Path, tmp_path: Path
) -> None:
    """A REF that does not match must be counted, not silently skipped."""
    vcf = tmp_path / "wrong.vcf"
    vcf.write_text(
        "##fileformat=VCFv4.2\n"
        "##contig=<ID=chr1,length=16>\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t1\t.\tG\tT\t50\tPASS\t.\n",
        encoding="utf-8",
    )
    files = {
        "reference_fasta": ("reference.fasta", fasta_file.read_bytes(), "text/plain"),
        "vcf_file": ("wrong.vcf", vcf.read_bytes(), "text/plain"),
    }
    response = await client.post(f"{BASE}/vcf-to-fasta", files=files)
    assert response.status_code == 200
    assert response.headers["x-variants-applied"] == "0"
    assert response.headers["x-variants-skipped"] == "1"


async def test_consensus_rejects_an_empty_reference(
    client: AsyncClient, vcf_file: Path, tmp_path: Path
) -> None:
    empty = tmp_path / "empty.fasta"
    empty.write_text("", encoding="utf-8")
    files = {
        "reference_fasta": ("empty.fasta", b"", "text/plain"),
        "vcf_file": ("variants.vcf", vcf_file.read_bytes(), "text/plain"),
    }
    response = await client.post(f"{BASE}/vcf-to-fasta", files=files)
    assert response.status_code == 422
    assert "no sequences" in response.json()["message"]
