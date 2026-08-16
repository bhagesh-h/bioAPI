# bioAPI

A REST API for everyday bioinformatics work: sequence manipulation, FASTA and
FASTQ utilities, file analysis, format conversion, and VCF-driven consensus
generation. Built on FastAPI, Biopython and pysam.

[![CI](https://github.com/bhagesh-h/bioAPI/actions/workflows/ci.yml/badge.svg)](https://github.com/bhagesh-h/bioAPI/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen)
![License](https://img.shields.io/badge/license-GPL--3.0-green)

Endpoint reference and overview: <https://bhagesh-h.github.io/bioAPI/>

**Docker is the only supported toolchain.** Every command below runs in a
container. There is no host virtualenv to create and no `pip install` to run —
which also means pysam's C extensions build once, in an environment where they
are known to work, rather than on each contributor's laptop.

## Quick start

```bash
git clone https://github.com/bhagesh-h/bioAPI.git
cd bioAPI
docker compose up api
```

The API is then on <http://127.0.0.1:8000>, with interactive docs at
<http://127.0.0.1:8000/docs> and ReDoc at <http://127.0.0.1:8000/redoc>.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/sequences/reverse-complement \
  -H 'Content-Type: application/json' \
  -d '{"sequence":"ATGCGTAA","alphabet":"dna"}'
```

```json
{
  "success": true,
  "message": null,
  "data": { "result": "TTACGCAT", "length": 8 },
  "error": null,
  "warnings": [],
  "request_id": "c20b1ca5-9c54-4297-8040-a944c809bc5b"
}
```

## Everyday commands

| Command | What it does |
|---|---|
| `make up` | Serve the API on port 8000 |
| `make test` | Full test suite behind a 90% coverage gate |
| `make lint` | `ruff check`, `ruff format --check` and `mypy --strict` |
| `make format` | Rewrite the source with `ruff format` and apply safe fixes |
| `make smoke` | Start the container, probe `/health/ready`, tear it down |
| `make shell` | A shell inside the dev image |
| `make clean` | Remove containers, images and caches |

Without `make`, every target is a plain compose command — `docker compose run
--rm test`, `docker compose run --rm lint`, and so on.

## The response envelope

Every JSON endpoint returns the same shape, so a client writes one unwrapping
helper and reuses it everywhere.

| Field | Meaning |
|---|---|
| `success` | Whether the operation completed |
| `message` | Optional human-readable note |
| `data` | The payload; `null` on failure |
| `error` | `{code, message, details}`; `null` on success |
| `warnings` | Non-fatal notes — ambiguity codes found, records skipped, quality dropped |
| `request_id` | Correlation id, also returned in the `X-Request-ID` header |

`error.code` is a stable identifier meant for branching in client code:
`VALIDATION_ERROR`, `INVALID_SEQUENCE`, `INVALID_FASTA`, `INVALID_FASTQ`,
`PARSE_ERROR`, `UNSUPPORTED_FORMAT`, `UNSUPPORTED_CONVERSION`,
`PAYLOAD_TOO_LARGE`, `NOT_FOUND`, `UNAUTHORIZED`, `FORBIDDEN`, `RATE_LIMITED`,
`INTERNAL_ERROR`.

Endpoints that produce a file return it directly, with the metadata in `X-`
response headers rather than a JSON body.

Warnings are worth reading. An operation can succeed and still have something to
tell you — that 12 sequences were skipped, that a VCF variant did not match the
reference, that a translation dropped a partial codon.

## Endpoints

### Health and metadata

| Method | Path | Description |
|---|---|---|
| GET | `/` | Service name, version and documentation links |
| GET | `/health`, `/health/live` | Liveness — 200 while the process is serving |
| GET | `/health/ready` | Readiness — parses a probe record and loads pysam; 503 if either fails |
| GET | `/ready` | Deprecated alias of `/health/ready` |
| GET | `/version` | App, Python, Biopython and pysam versions |
| GET | `/metrics` | Prometheus metrics |

Health and metrics paths never require an API key and are exempt from rate
limiting, so an orchestrator's probes cannot be locked out.

### Sequences — `/api/v1/sequences`

| Path | Description |
|---|---|
| `POST /reverse` | Reverse a sequence |
| `POST /complement` | Complement; RNA input stays RNA |
| `POST /reverse-complement` | Opposite strand, 5'→3' |
| `POST /transcribe` | DNA → RNA |
| `POST /back-transcribe` | RNA → DNA |
| `POST /translate` | Nucleotide → protein, any NCBI genetic code |
| `POST /gc-content` | GC percentage with G/C and A/T counts |
| `POST /count-bases` | Residue frequencies, most common first |
| `POST /kmer` | K-mer counts, optionally the top N |
| `POST /find-motif` | Motif positions, overlapping or not |
| `POST /validate` | Report validity without rejecting — always 200 |

### FASTA utilities — `/api/v1/fasta`

| Path | Description |
|---|---|
| `POST /stats` | Lengths, N50, GC, per-sequence breakdown |
| `POST /shorten-headers` | Truncate headers, warning on collisions |
| `POST /get-n-sequences` | First N records |
| `POST /filter-by-length` | Keep records within a length range |
| `POST /extract-subsequence` | Slice a 1-based inclusive range from each record |
| `POST /sample-sequences` | Random sample, reproducible with `seed` |
| `POST /split` | Into `n` chunks or chunks of `size` |
| `POST /merge` | Concatenate documents, optionally deduplicating ids |
| `POST /convert-case` | Upper or lower case the sequences |
| `POST /remove-unknown-chars` | Strip non-ACGT, optionally keeping IUPAC codes |
| `POST /rename-sequences` | Apply an `{old_id: new_id}` map |
| `POST /modify-descriptions` | Apply an `{id: description}` map |
| `POST /find-unique` | Deduplicate by sequence content |
| `POST /extract-ids` | List every identifier |

### FASTQ utilities — `/api/v1/fastq`

| Path | Description |
|---|---|
| `POST /stats` | Read counts, lengths, GC, mean quality, Q20/Q30 |
| `POST /quality-filter` | Filter by mean Phred score and length |
| `POST /to-fasta` | Drop the quality track |
| `POST /compress-gz` | Gzip, returned base64-encoded |
| `POST /decompress-gz` | Reverse of the above, validated as FASTQ |

### Files — `/api/v1/files`

| Path | Description |
|---|---|
| `POST /stats` | Analyse an upload; format detected from content |
| `POST /summary` | Deprecated alias of `/stats` |
| `POST /extract-gff` | Slice FASTA features using GFF/GTF coordinates |
| `POST /vcf/extract` | List variants of a given class |

Recognised for analysis: FASTA, FASTQ, GenBank, EMBL, SAM, BAM, VCF, GFF, GTF
and plain text.

### Conversions — `/api/v1/conversions`

| Path | Description |
|---|---|
| `POST /convert` | Convert between formats |
| `POST /vcf-to-fasta` | Apply a VCF to a reference to build a consensus |

### Capabilities — `/api/v1/formats`

`GET /api/v1/formats` publishes the conversion matrix and the reason each
unavailable pair is unavailable, so clients need not hard-code it.

| From | To |
|---|---|
| fasta | genbank, embl, tab, json |
| fastq | fasta, genbank, embl, tab, json |
| genbank | fasta, embl, tab, json |
| embl | fasta, genbank, tab, json |
| tab | fasta, genbank, embl, json |
| text | fasta, json |

Anything targeting FASTQ from a source without quality scores is refused up
front with an explanation rather than failing deep inside Biopython.

## Examples

**Analyse a file — detection reads the content, not the extension**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/files/stats -F "file=@reads.fastq"
```

A FASTA file named `sample.txt` is still reported as FASTA, with
`format.confidence` and `format.reason` explaining the verdict.

**Convert FASTA to GenBank**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/conversions/convert?source_format=fasta&target_format=genbank" \
  -F "file=@genome.fasta" -o genome.gb
```

GenBank requires a `molecule_type` annotation that FASTA does not carry; it is
inferred from the sequence composition and reported as a warning.

**Build a consensus from a VCF**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/conversions/vcf-to-fasta \
  -F "reference_fasta=@ref.fasta" -F "vcf_file=@variants.vcf" -o consensus.fasta
```

Variants are applied from the end of each sequence backwards, so an indel cannot
shift the coordinates of the variants still to be applied. Any variant whose REF
does not match the reference is skipped and counted in `X-Variants-Skipped`.

**Extract gene sequences with a GFF**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/files/extract-gff \
  -F "fasta_file=@genome.fasta" -F "gff_file=@annotations.gff" \
  -F "feature_type=gene" -o genes.fasta
```

**Reproducible sampling**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/fasta/sample-sequences \
  -H 'Content-Type: application/json' \
  -d '{"fasta_string":">a\nACGT\n>b\nTTGG\n>c\nCCAA","n":2,"seed":42}'
```

## Configuration

Every setting has a working default, so the container starts with no `.env` at
all. Copy [`.env.example`](.env.example) to `.env` to override. The settings
that matter most in production:

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` suppresses internal error detail |
| `API_KEY` | unset | When set, every `/api/v1` route needs `X-API-Key` |
| `BACKEND_CORS_ORIGINS` | `*` | Comma-separated or a JSON array; narrow this |
| `MAX_UPLOAD_SIZE_MB` | `50` | Enforced by header and again while streaming |
| `RATE_LIMIT_DEFAULT` | `120/minute` | `count/second\|minute\|hour\|day` |
| `LOG_FORMAT` | `json` | `console` for readable local output |
| `DOCS_ENABLED` | `true` | `false` hides `/docs`, `/redoc` and the schema |

## Security

- **Authentication** is off until `API_KEY` is set. Once set, a missing header
  is a 401 and a wrong value a 403, compared in constant time. The scheme is
  declared in OpenAPI, so Swagger UI shows an *Authorize* button.
- **Rate limiting** is a per-key (or per-IP) fixed window, advertised through
  `X-RateLimit-*` headers with `Retry-After` on a 429.
- **Upload limits** are checked against `Content-Length` and again while the
  body streams to disk, so a client that omits the header cannot fill the disk.
- **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Cross-Origin-Opener-Policy`, `Permissions-Policy` — are
  set on every response.
- **The container runs as an unprivileged user** (uid 10001) from a multi-stage
  build that leaves the compilers behind in the builder stage.

## Documentation

- [Project site](https://bhagesh-h.github.io/bioAPI/) — the same endpoint reference as a
  single page, published from [`site/`](site/) by
  [`.github/workflows/pages.yml`](.github/workflows/pages.yml)
- [Architecture](docs/architecture.md) — how the layers fit together and why
- [API reference](docs/api-reference.md) — every endpoint, with request shapes
- [Development](docs/development.md) — working on the code, all through Docker
- [Deployment](docs/deployment.md) — running it somewhere real
- [Testing](docs/testing.md) — how the suite is organised
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## License

[GNU General Public License v3.0](LICENSE).
