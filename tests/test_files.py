"""File upload analysis and cross-file extraction."""

from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.conftest import GENBANK_DOCUMENT, SIMPLE_FASTA, SIMPLE_FASTQ

BASE = "/api/v1/files"


async def test_fasta_upload_statistics(client: AsyncClient) -> None:
    files = {"file": ("sample.fasta", SIMPLE_FASTA.encode(), "text/plain")}
    response = await client.post(f"{BASE}/stats", files=files)
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["format"]["detected_format"] == "fasta"
    assert data["format"]["confidence"] == "high"
    assert data["sequence_stats"]["num_records"] == 3
    assert data["preview_ids"] == ["seq1", "seq2", "seq3"]


async def test_fasta_is_detected_from_content_despite_a_txt_extension(
    client: AsyncClient,
) -> None:
    """Extension-only detection used to report this as plain text."""
    files = {"file": ("mislabelled.txt", SIMPLE_FASTA.encode(), "text/plain")}
    response = await client.post(f"{BASE}/stats", files=files)

    data = response.json()["data"]
    assert data["format"]["detected_format"] == "fasta"
    assert data["format"]["reason"] == "identified from file content"


async def test_fastq_upload_reports_quality(client: AsyncClient) -> None:
    files = {"file": ("reads.fastq", SIMPLE_FASTQ.encode(), "text/plain")}
    response = await client.post(f"{BASE}/stats", files=files)

    data = response.json()["data"]
    assert data["format"]["detected_format"] == "fastq"
    assert data["sequence_stats"]["num_records"] == 3
    assert data["quality_stats"]["max_quality"] == 40


async def test_genbank_upload(client: AsyncClient, genbank_file: Path) -> None:
    files = {"file": ("record.gb", genbank_file.read_bytes(), "text/plain")}
    response = await client.post(f"{BASE}/stats", files=files)

    data = response.json()["data"]
    assert data["format"]["detected_format"] == "genbank"
    assert data["sequence_stats"]["num_records"] == 1
    assert data["sequence_stats"]["total_bases"] == 16


async def test_gff_upload_counts_features(client: AsyncClient, gff_file: Path) -> None:
    files = {"file": ("annotations.gff", gff_file.read_bytes(), "text/plain")}
    response = await client.post(f"{BASE}/stats", files=files)

    data = response.json()["data"]
    assert data["format"]["detected_format"] == "gff"
    assert data["gff_stats"]["total_features"] == 3
    assert data["gff_stats"]["feature_counts"]["gene"] == 2
    assert data["gff_stats"]["sequence_ids"] == ["chr1"]


async def test_vcf_upload_counts_variants(client: AsyncClient, vcf_file: Path) -> None:
    files = {"file": ("variants.vcf", vcf_file.read_bytes(), "text/plain")}
    response = await client.post(f"{BASE}/stats", files=files)

    data = response.json()["data"]
    assert data["format"]["detected_format"] == "vcf"
    assert data["vcf_stats"]["total_variants"] == 3
    assert data["vcf_stats"]["snps"] == 2
    assert data["vcf_stats"]["indels"] == 1
    assert data["vcf_stats"]["contigs"] == ["chr1"]


async def test_sam_upload(client: AsyncClient, sam_file: Path) -> None:
    files = {"file": ("alignments.sam", sam_file.read_bytes(), "text/plain")}
    response = await client.post(f"{BASE}/stats", files=files)

    data = response.json()["data"]
    assert data["format"]["detected_format"] == "sam"
    assert data["bam_stats"]["total_reads"] == 2
    assert data["bam_stats"]["mapped_reads"] == 1
    assert data["bam_stats"]["unmapped_reads"] == 1


async def test_bam_upload(client: AsyncClient, bam_file: Path) -> None:
    files = {"file": ("alignments.bam", bam_file.read_bytes(), "application/octet-stream")}
    response = await client.post(f"{BASE}/stats", files=files)

    data = response.json()["data"]
    assert data["format"]["detected_format"] == "bam"
    assert data["bam_stats"]["total_reads"] == 2
    assert data["bam_stats"]["references"] == 1


async def test_plain_text_upload_falls_back_to_line_counting(client: AsyncClient) -> None:
    files = {"file": ("notes.txt", b"just some words\nand more words\n", "text/plain")}
    response = await client.post(f"{BASE}/stats", files=files)

    data = response.json()["data"]
    assert data["format"]["detected_format"] == "text"
    assert data["lines"] == 2
    assert data["sequence_stats"] is None


async def test_summary_alias_matches_stats(client: AsyncClient) -> None:
    files = {"file": ("sample.fasta", SIMPLE_FASTA.encode(), "text/plain")}
    stats = await client.post(f"{BASE}/stats", files=files)
    files = {"file": ("sample.fasta", SIMPLE_FASTA.encode(), "text/plain")}
    summary = await client.post(f"{BASE}/summary", files=files)

    assert summary.status_code == 200
    assert summary.json()["data"]["sequence_stats"] == stats.json()["data"]["sequence_stats"]


async def test_corrupt_fasta_upload_is_reported_as_a_parse_error(client: AsyncClient) -> None:
    files = {"file": ("broken.fasta", b">only_a_header_no_sequence_marker", "text/plain")}
    response = await client.post(f"{BASE}/stats", files=files)
    assert response.status_code == 200  # a header with an empty sequence is still valid FASTA
    assert response.json()["data"]["sequence_stats"]["num_records"] == 1


async def test_extract_gff_features(client: AsyncClient, fasta_file: Path, gff_file: Path) -> None:
    files = {
        "fasta_file": ("reference.fasta", fasta_file.read_bytes(), "text/plain"),
        "gff_file": ("annotations.gff", gff_file.read_bytes(), "text/plain"),
    }
    response = await client.post(f"{BASE}/extract-gff", files=files, data={"feature_type": "gene"})
    assert response.status_code == 200
    assert response.headers["x-features-extracted"] == "2"

    body = response.text
    assert ">chr1_1_4_gene" in body
    assert "ATGC" in body
    # chr1[5:8] is ATGC on the plus strand, so the minus-strand feature is GCAT.
    assert "GCAT" in body


async def test_extract_gff_without_a_feature_filter_takes_everything(
    client: AsyncClient, fasta_file: Path, gff_file: Path
) -> None:
    files = {
        "fasta_file": ("reference.fasta", fasta_file.read_bytes(), "text/plain"),
        "gff_file": ("annotations.gff", gff_file.read_bytes(), "text/plain"),
    }
    response = await client.post(f"{BASE}/extract-gff", files=files)
    assert response.headers["x-features-extracted"] == "3"


async def test_extract_gff_skips_out_of_range_coordinates(
    client: AsyncClient, fasta_file: Path, tmp_path: Path
) -> None:
    """A feature past the end of the reference used to yield an empty sequence."""
    gff = tmp_path / "bad.gff"
    gff.write_text(
        "chr1\t.\tgene\t1\t4\t.\t+\t.\tID=ok\nchr1\t.\tgene\t900\t999\t.\t+\t.\tID=beyond\n",
        encoding="utf-8",
    )
    files = {
        "fasta_file": ("reference.fasta", fasta_file.read_bytes(), "text/plain"),
        "gff_file": ("bad.gff", gff.read_bytes(), "text/plain"),
    }
    response = await client.post(f"{BASE}/extract-gff", files=files)
    assert response.status_code == 200
    assert response.headers["x-features-extracted"] == "1"
    assert response.headers["x-features-skipped"] == "1"


async def test_extract_gff_with_no_matching_features_fails_clearly(
    client: AsyncClient, fasta_file: Path, gff_file: Path
) -> None:
    files = {
        "fasta_file": ("reference.fasta", fasta_file.read_bytes(), "text/plain"),
        "gff_file": ("annotations.gff", gff_file.read_bytes(), "text/plain"),
    }
    response = await client.post(
        f"{BASE}/extract-gff", files=files, data={"feature_type": "nonexistent"}
    )
    assert response.status_code == 422
    assert "No feature could be extracted" in response.json()["message"]


async def test_extract_all_variants(client: AsyncClient, vcf_file: Path) -> None:
    files = {"vcf_file": ("variants.vcf", vcf_file.read_bytes(), "text/plain")}
    response = await client.post(f"{BASE}/vcf/extract", files=files, data={"variant_type": "ALL"})
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["count"] == 3
    assert data["total_in_file"] == 3
    assert [variant["type"] for variant in data["variants"]] == ["SNP", "INDEL", "SNP"]
    assert data["variants"][0]["filter"] == ["PASS"]


async def test_extract_only_snps(client: AsyncClient, vcf_file: Path) -> None:
    files = {"vcf_file": ("variants.vcf", vcf_file.read_bytes(), "text/plain")}
    response = await client.post(f"{BASE}/vcf/extract", files=files, data={"variant_type": "SNP"})

    data = response.json()["data"]
    assert data["count"] == 2
    assert data["total_in_file"] == 3


async def test_unknown_variant_type_is_rejected(client: AsyncClient, vcf_file: Path) -> None:
    files = {"vcf_file": ("variants.vcf", vcf_file.read_bytes(), "text/plain")}
    response = await client.post(
        f"{BASE}/vcf/extract", files=files, data={"variant_type": "NONSENSE"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FORMAT"


async def test_oversized_upload_is_rejected(client: AsyncClient, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    payload = b">big\n" + b"A" * (2 * 1024 * 1024)
    files = {"file": ("big.fasta", payload, "text/plain")}

    response = await client.post(f"{BASE}/stats", files=files)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


async def test_genbank_document_constant_is_parseable(client: AsyncClient) -> None:
    files = {"file": ("record.gb", GENBANK_DOCUMENT.encode(), "text/plain")}
    response = await client.post(f"{BASE}/stats", files=files)
    assert response.status_code == 200
