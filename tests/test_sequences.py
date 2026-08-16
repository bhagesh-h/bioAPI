"""Single-sequence endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

BASE = "/api/v1/sequences"


async def test_reverse(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/reverse", json={"sequence": "ATGC"})
    assert response.status_code == 200
    assert response.json()["data"]["result"] == "CGTA"


async def test_complement(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/complement", json={"sequence": "ATGC", "alphabet": "dna"})
    assert response.json()["data"]["result"] == "TACG"


async def test_reverse_complement(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/reverse-complement", json={"sequence": "ATGC", "alphabet": "dna"}
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["result"] == "GCAT"
    assert body["length"] == 4


async def test_reverse_complement_of_rna_stays_rna(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/reverse-complement", json={"sequence": "AUGC", "alphabet": "rna"}
    )
    assert response.json()["data"]["result"] == "GCAU"


async def test_invalid_characters_are_rejected_with_a_code(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/reverse-complement", json={"sequence": "ATGCZZ", "alphabet": "dna"}
    )
    assert response.status_code == 400

    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_SEQUENCE"
    assert body["error"]["details"]["invalid_characters"] == ["Z"]


async def test_iupac_ambiguity_codes_are_accepted_with_a_warning(client: AsyncClient) -> None:
    """A sequence with N and R is valid DNA; the old alphabet rejected it."""
    response = await client.post(
        f"{BASE}/reverse-complement", json={"sequence": "ATGCNRY", "alphabet": "dna"}
    )
    assert response.status_code == 200
    assert any("ambiguity" in warning for warning in response.json()["warnings"])


async def test_protein_sequence_cannot_be_reverse_complemented(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/reverse-complement", json={"sequence": "MKWV", "alphabet": "protein"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SEQUENCE"


async def test_transcribe_and_back_transcribe_round_trip(client: AsyncClient) -> None:
    forward = await client.post(f"{BASE}/transcribe", json={"sequence": "ATGC"})
    rna = forward.json()["data"]["result"]
    assert rna == "AUGC"

    backward = await client.post(f"{BASE}/back-transcribe", json={"sequence": rna})
    assert backward.json()["data"]["result"] == "ATGC"


async def test_translate_standard_table(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/translate", json={"sequence": "ATGGCCATTGTA", "table": 1})
    assert response.status_code == 200
    assert response.json()["data"]["result"] == "MAIV"


async def test_translate_to_stop(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/translate", json={"sequence": "ATGGCCTAAGGG", "to_stop": True}
    )
    assert response.json()["data"]["result"] == "MA"


async def test_translate_warns_about_a_partial_codon(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/translate", json={"sequence": "ATGGCCA"})
    assert response.status_code == 200
    assert response.json()["data"]["result"] == "MA"
    assert any("multiple of three" in warning for warning in response.json()["warnings"])


async def test_translate_rejects_a_sequence_shorter_than_a_codon(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/translate", json={"sequence": "AT"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SEQUENCE"


async def test_gc_content(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/gc-content", json={"sequence": "ATGCGC"})
    data = response.json()["data"]
    assert data["gc_percent"] == pytest.approx(66.6667)
    assert data["gc_count"] == 4
    assert data["at_count"] == 2


async def test_gc_content_counts_the_s_ambiguity_code(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/gc-content", json={"sequence": "ATSS"})
    assert response.json()["data"]["gc_count"] == 2


async def test_count_bases_orders_by_frequency(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/count-bases", json={"sequence": "AAATTC"})
    data = response.json()["data"]
    assert list(data["counts"]) == ["A", "T", "C"]
    assert data["length"] == 6


async def test_kmer_counting(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/kmer", json={"sequence": "ACGTACGT", "k": 4})
    data = response.json()["data"]
    assert data["k"] == 4
    assert data["total_kmers"] == 5
    assert data["kmers"]["ACGT"] == 2


async def test_kmer_top_n_truncates_and_warns(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/kmer", json={"sequence": "ACGTACGTTTGCA", "k": 3, "top": 2}
    )
    assert len(response.json()["data"]["kmers"]) == 2
    assert any("top 2" in warning for warning in response.json()["warnings"])


async def test_kmer_longer_than_sequence_is_rejected(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/kmer", json={"sequence": "ACGT", "k": 10})
    assert response.status_code == 400
    assert response.json()["error"]["details"]["k"] == 10


async def test_find_motif_counts_overlaps_by_default(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/find-motif", json={"sequence": "AAAA", "motif": "AA"})
    data = response.json()["data"]
    assert data["count"] == 3
    assert data["hits"][0] == {"start": 0, "end": 2, "match": "AA"}


async def test_find_motif_without_overlaps(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/find-motif", json={"sequence": "AAAA", "motif": "AA", "allow_overlaps": False}
    )
    assert response.json()["data"]["count"] == 2


async def test_find_motif_longer_than_sequence_returns_no_hits(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/find-motif", json={"sequence": "ACGT", "motif": "ACGTACGT"}
    )
    assert response.json()["data"]["count"] == 0


async def test_validate_reports_without_rejecting(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/validate", json={"sequence": "ATGCZZ", "alphabet": "dna"})
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["is_valid"] is False
    assert data["invalid_chars"] == ["Z"]


async def test_validate_detects_the_alphabet(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/validate", json={"sequence": "AUGCUU"})
    data = response.json()["data"]
    assert data["is_valid"] is True
    assert data["alphabet_detected"] == "rna"


async def test_whitespace_is_stripped_before_processing(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/reverse", json={"sequence": "AT GC\nAT"})
    assert response.json()["data"]["result"] == "TACGTA"


async def test_empty_sequence_fails_schema_validation(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/reverse", json={"sequence": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"]["issues"]
