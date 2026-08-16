"""FASTA string utility endpoints — the group that had no coverage at all."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import DUPLICATE_FASTA, SIMPLE_FASTA, WRAPPED_FASTA

BASE = "/api/v1/fasta"


async def test_stats(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/stats", json={"fasta_string": SIMPLE_FASTA})
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["num_sequences"] == 3
    assert data["total_bases"] == 30
    assert data["min_length"] == 4
    assert data["max_length"] == 16
    assert len(data["records"]) == 3


async def test_extract_ids(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/extract-ids", json={"fasta_string": SIMPLE_FASTA})
    data = response.json()["data"]
    assert data["ids"] == ["seq1", "seq2", "seq3"]
    assert data["count"] == 3


async def test_shorten_headers(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/shorten-headers", json={"fasta_string": SIMPLE_FASTA, "n": 4}
    )
    assert response.status_code == 200
    assert ">seq1" in response.json()["data"]["fasta_string"]
    assert "first" not in response.json()["data"]["fasta_string"]


async def test_shorten_headers_warns_about_collisions(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/shorten-headers", json={"fasta_string": SIMPLE_FASTA, "n": 3}
    )
    assert any("duplicate identifiers" in w for w in response.json()["warnings"])


async def test_get_n_sequences(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/get-n-sequences", json={"fasta_string": SIMPLE_FASTA, "n": 2}
    )
    assert response.json()["data"]["num_sequences"] == 2


async def test_get_n_sequences_warns_when_asking_for_too_many(client: AsyncClient) -> None:
    """The old implementation built this warning and then threw it away."""
    response = await client.post(
        f"{BASE}/get-n-sequences", json={"fasta_string": SIMPLE_FASTA, "n": 99}
    )
    assert response.json()["data"]["num_sequences"] == 3
    assert any("returning all of them" in w for w in response.json()["warnings"])


async def test_filter_by_length(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/filter-by-length", json={"fasta_string": SIMPLE_FASTA, "min_length": 10}
    )
    assert response.json()["data"]["num_sequences"] == 2


async def test_filter_by_length_with_a_ceiling(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/filter-by-length",
        json={"fasta_string": SIMPLE_FASTA, "min_length": 5, "max_length": 12},
    )
    assert response.json()["data"]["num_sequences"] == 1


async def test_filter_by_length_rejects_an_inverted_range(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/filter-by-length",
        json={"fasta_string": SIMPLE_FASTA, "min_length": 20, "max_length": 5},
    )
    assert response.status_code == 422


async def test_extract_subsequence(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/extract-subsequence",
        json={"fasta_string": WRAPPED_FASTA, "start": 1, "end": 4},
    )
    assert response.status_code == 200
    assert "ATGC" in response.json()["data"]["fasta_string"]


async def test_extract_subsequence_fails_on_a_short_sequence(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/extract-subsequence", json={"fasta_string": SIMPLE_FASTA, "start": 1, "end": 12}
    )
    assert response.status_code == 400
    # seq1 is 10 bases long, so it is the first to fall short of end=12.
    assert response.json()["error"]["details"]["sequence_id"] == "seq1"


async def test_extract_subsequence_can_skip_short_sequences(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/extract-subsequence",
        json={"fasta_string": SIMPLE_FASTA, "start": 1, "end": 12, "skip_short": True},
    )
    assert response.status_code == 200
    assert response.json()["data"]["num_sequences"] == 1
    assert any("Skipped" in w for w in response.json()["warnings"])


async def test_extract_subsequence_rejects_start_after_end(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/extract-subsequence", json={"fasta_string": SIMPLE_FASTA, "start": 9, "end": 2}
    )
    assert response.status_code == 422


async def test_sample_sequences_is_reproducible_with_a_seed(client: AsyncClient) -> None:
    payload = {"fasta_string": SIMPLE_FASTA, "n": 2, "seed": 42}
    first = await client.post(f"{BASE}/sample-sequences", json=payload)
    second = await client.post(f"{BASE}/sample-sequences", json=payload)
    assert first.json()["data"]["fasta_string"] == second.json()["data"]["fasta_string"]
    assert first.json()["data"]["num_sequences"] == 2


async def test_split_by_chunk_count(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/split", json={"fasta_string": SIMPLE_FASTA, "n": 3})
    data = response.json()["data"]
    assert data["num_chunks"] == 3
    assert data["sequences_per_chunk"] == [1, 1, 1]


async def test_split_by_chunk_size(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/split", json={"fasta_string": SIMPLE_FASTA, "size": 2})
    data = response.json()["data"]
    assert data["num_chunks"] == 2
    assert data["sequences_per_chunk"] == [2, 1]


async def test_split_rejects_both_strategies(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/split", json={"fasta_string": SIMPLE_FASTA, "n": 2, "size": 2}
    )
    assert response.status_code == 422


async def test_split_rejects_neither_strategy(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/split", json={"fasta_string": SIMPLE_FASTA})
    assert response.status_code == 422


async def test_split_into_more_chunks_than_sequences_is_rejected(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/split", json={"fasta_string": SIMPLE_FASTA, "n": 10})
    assert response.status_code == 400


async def test_merge(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/merge", json={"fasta_strings": [">a\nACGT", ">b\nTTGG"]})
    data = response.json()["data"]
    assert data["num_sequences"] == 2
    assert ">a" in data["fasta_string"] and ">b" in data["fasta_string"]


async def test_merge_warns_about_duplicate_ids(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/merge", json={"fasta_strings": [">a\nACGT", ">a\nTTGG"]})
    assert any("more than one input" in w for w in response.json()["warnings"])


async def test_merge_can_deduplicate_ids(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/merge",
        json={"fasta_strings": [">a\nACGT", ">a\nTTGG"], "deduplicate_ids": True},
    )
    assert ">a_2" in response.json()["data"]["fasta_string"]


async def test_merge_names_the_offending_input(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/merge", json={"fasta_strings": [">a\nACGT", "not fasta at all"]}
    )
    assert response.status_code == 422
    assert "fasta_strings[1]" in response.json()["message"]


async def test_convert_case(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/convert-case", json={"fasta_string": ">a\nacgt", "case": "upper"}
    )
    assert "ACGT" in response.json()["data"]["fasta_string"]


async def test_remove_unknown_chars(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/remove-unknown-chars", json={"fasta_string": ">a\nACGTNNXX"}
    )
    assert response.json()["data"]["fasta_string"].endswith("ACGT")
    assert any("Removed 4" in w for w in response.json()["warnings"])


async def test_remove_unknown_chars_can_keep_ambiguity_codes(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/remove-unknown-chars",
        json={"fasta_string": ">a\nACGTNNXX", "keep_ambiguity_codes": True},
    )
    assert response.json()["data"]["fasta_string"].endswith("ACGTNN")


async def test_rename_sequences_preserves_descriptions(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/rename-sequences",
        json={"fasta_string": ">old keep me\nACGT", "rename_map": {"old": "new"}},
    )
    assert ">new keep me" in response.json()["data"]["fasta_string"]


async def test_rename_sequences_warns_about_unused_mappings(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/rename-sequences",
        json={"fasta_string": ">a\nACGT", "rename_map": {"missing": "new"}},
    )
    assert any("were not found" in w for w in response.json()["warnings"])


async def test_modify_descriptions(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/modify-descriptions",
        json={"fasta_string": ">a old text\nACGT", "description_map": {"a": "new text"}},
    )
    assert ">a new text" in response.json()["data"]["fasta_string"]


async def test_find_unique(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/find-unique", json={"fasta_string": DUPLICATE_FASTA})
    assert response.json()["data"]["num_sequences"] == 2
    assert any("Dropped 1 duplicate" in w for w in response.json()["warnings"])


async def test_multiline_sequences_are_joined(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/stats", json={"fasta_string": WRAPPED_FASTA})
    assert response.json()["data"]["total_bases"] == 20


async def test_line_width_controls_wrapping(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/convert-case",
        json={"fasta_string": WRAPPED_FASTA, "case": "upper", "line_width": 5},
    )
    body = response.json()["data"]["fasta_string"]
    assert body.splitlines()[1] == "ATGCA"


async def test_malformed_fasta_is_rejected(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/extract-ids", json={"fasta_string": "ACGT no header"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_FASTA"


async def test_header_without_an_identifier_is_rejected(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/extract-ids", json={"fasta_string": ">\nACGT"})
    assert response.status_code == 422
    assert "no identifier" in response.json()["message"]
