# API reference

The live OpenAPI document is the authority: `/docs`, `/redoc`, or
`/api/v1/openapi.json`. This page covers the parts that are easier to explain in
prose than in a schema.

## Conventions

Base path for everything versioned: `/api/v1`. Health and metadata sit at the
root so probes never move between versions.

Every JSON endpoint returns:

```json
{
  "success": true,
  "message": null,
  "data": {},
  "error": null,
  "warnings": [],
  "request_id": "0f7c0a6e-2c5b-4a8e-9d0f-6f7a1b2c3d4e"
}
```

On failure `data` is `null` and `error` is populated:

```json
{
  "success": false,
  "message": "Sequence contains characters outside dna: Z",
  "data": null,
  "error": {
    "code": "INVALID_SEQUENCE",
    "message": "Sequence contains characters outside dna: Z",
    "details": { "invalid_characters": ["Z"], "expected_alphabet": "dna" }
  },
  "warnings": [],
  "request_id": "0f7c0a6e-2c5b-4a8e-9d0f-6f7a1b2c3d4e"
}
```

### Status codes

| Code | Meaning |
|---|---|
| 200 | Success |
| 400 | The request was understood but rejected — bad sequence, impossible conversion |
| 401 | `X-API-Key` missing while a key is configured |
| 403 | `X-API-Key` present but wrong |
| 413 | Payload above `MAX_UPLOAD_SIZE_MB` |
| 422 | Schema validation failed, or a document could not be parsed |
| 429 | Rate limit exceeded |
| 500 | Unhandled error; details are logged, not returned |
| 503 | `/health/ready` only — a dependency is unusable |

### Response headers

| Header | On |
|---|---|
| `X-Request-ID` | Everything; echoes an inbound value if you send one |
| `X-Process-Time` | Everything; milliseconds |
| `X-RateLimit-Limit`, `-Remaining`, `-Reset` | Everything except exempt paths |
| `Retry-After` | 429 |
| `X-Records-Converted` | `/conversions/convert`, `/conversions/vcf-to-fasta` |
| `X-Conversion-Source`, `-Target`, `-Warnings` | `/conversions/convert` |
| `X-Variants-Applied`, `X-Variants-Skipped` | `/conversions/vcf-to-fasta` |
| `X-Features-Extracted`, `X-Features-Skipped` | `/files/extract-gff` |

## Sequences

All eleven endpoints share a request base:

```json
{
  "sequence": "ATGCGTAA",
  "alphabet": "dna",
  "uppercase": true,
  "remove_whitespace": true
}
```

`alphabet` is `dna`, `rna`, `protein`, or omitted to auto-detect. Whitespace and
newlines are stripped before processing, so pasting a wrapped sequence works.

IUPAC ambiguity codes are valid: `RYSWKMBDHVN` for nucleotides, `BZJXUO*` for
proteins, plus `-` and `.` for alignment gaps. Using one is not an error, but it
does produce a warning, because most calculations treat the code literally
rather than expanding it.

Nucleotide-only operations — complement, reverse-complement, transcribe,
back-transcribe, translate, GC content — reject a sequence declared as
`protein`.

### Endpoint-specific fields

| Endpoint | Extra fields |
|---|---|
| `/translate` | `table` (NCBI genetic code id, default 1), `to_stop` (default false) |
| `/kmer` | `k` (1–32, default 3), `top` (return only the N most frequent) |
| `/find-motif` | `motif` (required), `allow_overlaps` (default true) |

`/translate` truncates to the last whole codon when the length is not a multiple
of three, and says so in `warnings`. A sequence shorter than one codon is a 400.

`/validate` never rejects — an invalid sequence still returns 200, with
`is_valid: false` and the offending characters listed. Use it to check input
before committing to an operation.

`/find-motif` returns 0-based half-open coordinates: `{"start": 0, "end": 2}` is
the first two characters.

## FASTA utilities

Every request carries `fasta_string` and an optional `line_width` (default 60;
`0` puts each sequence on one line). Multi-line sequences are joined on parse
and re-wrapped on output. Blank lines between records are tolerated.

| Endpoint | Fields |
|---|---|
| `/stats` | — |
| `/shorten-headers` | `n` — characters to keep |
| `/get-n-sequences` | `n` |
| `/filter-by-length` | `min_length`, `max_length` |
| `/extract-subsequence` | `start`, `end` (1-based inclusive), `skip_short` |
| `/sample-sequences` | `n`, `seed` |
| `/split` | `n` **or** `size`, never both |
| `/merge` | `fasta_strings` (≥2), `deduplicate_ids` |
| `/convert-case` | `case`: `upper` or `lower` |
| `/remove-unknown-chars` | `keep_ambiguity_codes` |
| `/rename-sequences` | `rename_map` |
| `/modify-descriptions` | `description_map` |
| `/find-unique` | — |
| `/extract-ids` | — |

Notes:

- `/extract-subsequence` fails the whole request if any sequence is shorter than
  `end`, naming it in `error.details`. Set `skip_short: true` to drop those
  instead; the skipped identifiers come back in `warnings`.
- `/sample-sequences` without a `seed` is genuinely random and will differ
  between calls. Pass one to make a selection reproducible.
- `/merge` reports duplicate identifiers as a warning; `deduplicate_ids: true`
  suffixes them `_2`, `_3` in order of appearance.
- `/rename-sequences` and `/modify-descriptions` warn about map keys that match
  no record — usually a typo.
- `/stats` reports N50 alongside min, max, mean and GC, and includes a
  per-sequence breakdown.

## FASTQ utilities

Every request carries `fastq_string` and `quality_offset` (33 for Sanger and
Illumina 1.8+, 64 for older Illumina).

| Endpoint | Fields |
|---|---|
| `/stats` | — |
| `/quality-filter` | `min_quality` (mean Phred, default 20), `min_length` |
| `/to-fasta` | `line_width` |
| `/compress-gz` | — |
| `/decompress-gz` | `fastq_gz_base64` |

Parsing is strict: exactly four lines per read, `@` on the first, `+` on the
third, sequence and quality of equal non-zero length. Errors name the read
number. Line-wrapped FASTQ cannot be parsed unambiguously and is rejected
rather than guessed at.

`/compress-gz` returns base64 so the bytes survive JSON. Feed `data_base64`
straight to `/decompress-gz`, which validates that the result really is FASTQ.
For large files use the upload endpoints instead — base64 adds a third to the
size.

`/stats` reports Q20 and Q30 percentages. A quality string that decodes below
zero at the chosen offset produces a warning suggesting the other encoding.

## Files

### `POST /files/stats`

Multipart, field name `file`. The format is detected from the first 64 KB of
content combined with the filename:

| `confidence` | Meaning |
|---|---|
| `high` | Content signature found; extension agrees or was uninformative |
| `medium` | Content and extension disagree — content wins, and `reason` says so |
| `low` | No signature; the extension alone, or a fallback to text |

Which statistics block is populated depends on the format:

| Format | Block |
|---|---|
| FASTA, GenBank, EMBL | `sequence_stats` |
| FASTQ | `sequence_stats` and `quality_stats` |
| SAM, BAM | `bam_stats` |
| GFF, GTF | `gff_stats` |
| VCF | `vcf_stats` |
| text, unrecognised | `lines` only |

### `POST /files/extract-gff`

Multipart: `fasta_file`, `gff_file`, optional `feature_type` form field.
Returns FASTA as `text/plain`.

Coordinates are 1-based inclusive, as GFF specifies. Minus-strand features are
reverse-complemented. Features naming an unknown sequence, carrying
non-numeric coordinates, or falling outside the reference are skipped, counted
in `X-Features-Skipped` and explained in `warnings`. If nothing at all matches,
the response is a 422 that tells you to check the identifiers and the spelling
of `feature_type`.

### `POST /files/vcf/extract`

Multipart: `vcf_file`, optional `variant_type` form field — `ALL`, `SNP`,
`INDEL`, `MNP` or `OTHER`. Anything else is a 400.

Classification: any ALT of a different length to REF is an INDEL; equal lengths
with a single-base REF is a SNP; equal lengths with a longer REF is an MNP;
records with no usable ALT (`*`, `.`, `<NON_REF>`) are OTHER.

The response carries both `count` (matching) and `total_in_file`.

## Conversions

### `POST /conversions/convert`

Query parameters `source_format` and `target_format`; the file is multipart
`file`. The pair is checked before the upload is read — an unsupported one costs
no I/O and returns an explanation plus the list of targets that would work.

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/conversions/convert?source_format=fasta&target_format=json" \
  -F "file=@genome.fasta"
```

The JSON writer emits `{"records": [...], "count": N}`, each record carrying id,
name, description, sequence, length, and — when the source has them —
annotations, `phred_quality` and features.

Converting to GenBank or EMBL requires a `molecule_type` annotation. When the
source lacks one it is inferred (RNA if the sequence contains U, DNA for other
nucleotide alphabets, protein otherwise) and reported as a warning.

Converting FASTQ to anything else drops the quality scores, also as a warning.

`text` treats each non-empty line as one sequence and names them `seq_1`,
`seq_2`, …

### `POST /conversions/vcf-to-fasta`

Multipart: `reference_fasta`, `vcf_file`. Returns the consensus FASTA.

The first ALT allele of each record is applied. Variants are applied from the
end of each sequence backwards so an indel cannot shift the coordinates of those
still pending. A variant is skipped when its chromosome is absent from the
reference, its position falls outside the sequence, or its REF does not match
what is actually there — that last case usually means the VCF was called against
a different reference build. Skips are counted in `X-Variants-Skipped` and
broken down by reason in `warnings`.

Reference sequences with no variants are copied through unchanged, so the output
always has the same record count as the input.

## Rate limiting

A fixed window keyed on `X-API-Key` when present, otherwise on
`X-Forwarded-For` or the peer address. Every response outside the exempt paths
carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset`
(seconds until the window rolls over). A 429 adds `Retry-After`.

Exempt: `/health`, `/health/live`, `/health/ready`, `/ready`, `/metrics`.

The counter is per process. Behind multiple replicas each enforces its own
share; put a global limit on the ingress if you need one.

## Authentication

Unset `API_KEY` means the API is open. With it set, every `/api/v1` route needs
the `X-API-Key` header — missing is 401, wrong is 403. Health, metadata and
metrics stay open either way.

```bash
curl -H "X-API-Key: $BIOAPI_KEY" http://127.0.0.1:8000/api/v1/formats
```

The scheme is declared in the OpenAPI document, so Swagger UI renders an
*Authorize* button rather than a stray header field on every operation.
