"""FASTQ string utility endpoints."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import SIMPLE_FASTQ

BASE = "/api/v1/fastq"


async def test_stats(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/stats", json={"fastq_string": SIMPLE_FASTQ})
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["num_reads"] == 3
    assert data["total_bases"] == 24
    assert data["min_length"] == 8
    assert data["max_length"] == 8
    assert 0 <= data["q30_percent"] <= 100


async def test_quality_filter_drops_low_quality_reads(client: AsyncClient) -> None:
    """read1 averages Q40, read3 averages Q30, read2 averages Q0."""
    response = await client.post(
        f"{BASE}/quality-filter", json={"fastq_string": SIMPLE_FASTQ, "min_quality": 35}
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["num_reads"] == 1
    assert "read1" in data["fastq_string"]
    assert any("Filtered out 2" in w for w in response.json()["warnings"])


async def test_quality_filter_threshold_is_inclusive(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/quality-filter", json={"fastq_string": SIMPLE_FASTQ, "min_quality": 30}
    )
    assert response.json()["data"]["num_reads"] == 2


async def test_quality_filter_keeps_everything_at_a_low_threshold(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/quality-filter", json={"fastq_string": SIMPLE_FASTQ, "min_quality": 0}
    )
    assert response.json()["data"]["num_reads"] == 3


async def test_quality_filter_can_also_filter_by_length(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/quality-filter",
        json={"fastq_string": SIMPLE_FASTQ, "min_quality": 0, "min_length": 100},
    )
    assert response.json()["data"]["num_reads"] == 0
    assert any("result is empty" in w for w in response.json()["warnings"])


async def test_quality_offset_64_is_supported(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/stats", json={"fastq_string": SIMPLE_FASTQ, "quality_offset": 64}
    )
    assert response.status_code == 200
    assert any("below zero" in w for w in response.json()["warnings"])


async def test_to_fasta(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/to-fasta", json={"fastq_string": SIMPLE_FASTQ})
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["num_sequences"] == 3
    assert data["fasta_string"].startswith(">read1 first")
    assert any("discarded" in w for w in response.json()["warnings"])


async def test_gzip_round_trip(client: AsyncClient) -> None:
    compressed = await client.post(f"{BASE}/compress-gz", json={"fastq_string": SIMPLE_FASTQ})
    assert compressed.status_code == 200

    payload = compressed.json()["data"]
    assert payload["original_size_bytes"] == len(SIMPLE_FASTQ)
    assert payload["compressed_size_bytes"] > 0

    restored = await client.post(
        f"{BASE}/decompress-gz", json={"fastq_gz_base64": payload["data_base64"]}
    )
    assert restored.status_code == 200
    assert restored.json()["data"]["fastq_string"] == SIMPLE_FASTQ
    assert restored.json()["data"]["num_reads"] == 3


async def test_decompress_rejects_bad_base64(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/decompress-gz", json={"fastq_gz_base64": "not base64!!"})
    assert response.status_code == 400
    assert "base64" in response.json()["message"]


async def test_decompress_rejects_a_non_gzip_payload(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/decompress-gz", json={"fastq_gz_base64": "aGVsbG8gd29ybGQ="}
    )
    assert response.status_code == 400
    assert "gzip" in response.json()["message"]


async def test_read_count_not_divisible_by_four_is_rejected(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/stats", json={"fastq_string": "@r1\nACGT\n+"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_FASTQ"


async def test_mismatched_sequence_and_quality_lengths_are_rejected(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/stats", json={"fastq_string": "@r1\nACGT\n+\nIIIIII"})
    assert response.status_code == 422
    assert "quality string is 6" in response.json()["message"]


async def test_header_must_start_with_at(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/stats", json={"fastq_string": "r1\nACGT\n+\nIIII"})
    assert response.status_code == 422
    assert "must start with '@'" in response.json()["message"]


async def test_third_line_must_start_with_plus(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/stats", json={"fastq_string": "@r1\nACGT\nx\nIIII"})
    assert response.status_code == 422
    assert "must start with '+'" in response.json()["message"]


async def test_empty_read_is_rejected_rather_than_dividing_by_zero(client: AsyncClient) -> None:
    """The previous quality filter raised ZeroDivisionError on this input."""
    response = await client.post(
        f"{BASE}/quality-filter", json={"fastq_string": "@r1\n\n+\n", "min_quality": 20}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_FASTQ"
