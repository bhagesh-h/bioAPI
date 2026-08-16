# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this
project uses [semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] — 2026-08-16

First release of bioAPI as its own repository, rebuilt from a prototype that
lived in a monorepo alongside an unrelated starter template. History starts
fresh here.

### Added

- **Self-describing capabilities** — `GET /api/v1/formats` publishes the
  conversion matrix and the reason each unavailable pair is unavailable.
- **Split health probes** — `/health/live` for liveness, `/health/ready` for
  readiness. Readiness parses a record with Biopython and loads pysam's compiled
  extension, returning 503 when either fails, so a broken image is pulled from
  the load balancer instead of failing real requests. `/health` and `/ready` are
  kept as aliases.
- **Prometheus metrics** at `/metrics`, with health paths excluded.
- **Structured JSON logging** with a request id, service name, version and
  environment on every record.
- **Request correlation** — `X-Request-ID` is generated or honoured from the
  inbound header, returned in the header and in every response envelope.
- **Rate limiting** — fixed window keyed on the API key when present, otherwise
  the client address, advertised through `X-RateLimit-*` headers. Health and
  metrics are exempt.
- **Security headers** on every response: `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Cross-Origin-Opener-Policy`,
  `Permissions-Policy`.
- **New endpoints** — `/api/v1/fasta/stats`, `/api/v1/fastq/stats` and
  `/api/v1/fastq/to-fasta`.
- **New options** — `seed` on `/fasta/sample-sequences` for reproducible
  sampling, `skip_short` on `/fasta/extract-subsequence`, `deduplicate_ids` on
  `/fasta/merge`, `keep_ambiguity_codes` on `/fasta/remove-unknown-chars`, `top`
  on `/sequences/kmer`, `allow_overlaps` on `/sequences/find-motif`,
  `min_length` and `quality_offset` on the FASTQ endpoints, `line_width`
  throughout the FASTA endpoints.
- **Docker-only toolchain** — multi-stage Dockerfile (builder, runtime, dev),
  compose services for `api`, `test`, `lint` and `format`, and a Makefile that
  never touches a host interpreter.
- **CI** — GitHub Actions running lint, types and tests in the dev image, then
  building the runtime image, waiting for its healthcheck and probing it live.
- **Test suite** — 196 tests at ~95% coverage behind a 90% gate. The sixteen
  FASTA and FASTQ endpoints previously had none.
- **Documentation** — architecture, API reference, development, deployment and
  testing guides, plus `.env.example`.

### Fixed

- **`json` conversion target never worked.** `SeqIO` has no JSON writer, so
  every request for it failed. JSON is now written natively, including quality
  scores and features when the source carries them.
- **`fasta` → `genbank` always failed.** The GenBank writer requires a
  `molecule_type` annotation FASTA cannot carry. It is now inferred from
  sequence composition and reported as a warning.
- **Conversion offered impossible source formats.** `bam`, `gff`, `gtf` and
  `string` were advertised but cannot be parsed by `SeqIO`. The supported pairs
  are now declared in one place and validated before the upload is read.
- **Warnings were computed and discarded.** `get-n-sequences` and
  `sample-sequences` built warning lists that never reached the response. All
  warnings now flow through a request-scoped buffer into the envelope.
- **`request_id` was always null** despite the middleware generating one.
- **DNA validation rejected IUPAC ambiguity codes.** `N`, `R`, `Y` and the rest
  are valid in real files; they are now accepted, with a warning noting they are
  treated literally.
- **`ZeroDivisionError` on a zero-length FASTQ quality string**, which surfaced
  as a 500. Empty reads are now a parse error naming the read.
- **Format detection trusted the file extension.** A FASTA file named
  `sample.txt` was analysed as plain text. Detection now reads the content and
  reports a real confidence level with the reason for its verdict.
- **GFF extraction produced silent empty sequences** for coordinates outside the
  reference. Such features are skipped, counted and reported.
- **Consensus generation silently dropped mismatched variants.** Skips are now
  counted by reason and surfaced in headers and warnings.
- **`extract-gff` double-wrapped its errors**, so the message read as an
  exception inside an exception.
- **`numpy` was imported but missing from `requirements.txt`**, working only by
  accident as a transitive dependency.
- **Debug detail keyed off `app.debug`**, which was never set, so the switch had
  no effect.
- **A missing API key returned 403.** It is now 401, with 403 reserved for a key
  that was supplied and rejected. Comparison is constant-time, and the scheme is
  declared in OpenAPI so Swagger renders an *Authorize* button.
- **Rate limiting was a no-op.** The dependency's middleware resolves limits by
  reading each route's `endpoint` from `app.routes`; FastAPI 0.141 wraps
  included routers in a container that exposes none, so no limit was ever
  applied. Replaced with a direct implementation.
- **Log records were JSON-encoded twice**, nesting each document inside the next
  one's `event` field and defeating field indexing.

### Changed

- **Restructured** to `core` / `api` / `schemas` / `services` / `utils`, with
  versioned endpoints under `app/api/v1/endpoints/` and health at the root.
- **Application factory** — `create_app()` replaces the module-level singleton,
  so tests can build isolated instances with different settings.
- **Every error carries a stable `error.code`** for client branching, with
  structured `details`.
- **FASTA and FASTQ parsing is strict and precise.** Multi-line sequences are
  joined, blank lines tolerated, and errors name the offending line or read.
- **Uploads stream to disk in bounded chunks** with the size checked as they go,
  so a request without `Content-Length` cannot exhaust the disk.
- **Statistics stream** rather than concatenating whole files into memory, and
  now include N50 and Q20/Q30.
- **Hardened the image** — multi-stage build, unprivileged user, healthcheck,
  `.dockerignore`, and exact version pins throughout.
- **`ruff format` replaces `black`**; `mypy --strict` passes over `app/`.
- **Python 3.12**, up from 3.11.
- **Removed `slowapi` and `orjson`** — the first was replaced, the second made
  redundant by FastAPI's own serialisation.
