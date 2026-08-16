# Testing

```bash
docker compose run --rm test
```

196 tests, ~95% line coverage, roughly four seconds. The suite runs in the `dev`
image and nowhere else.

## Layout

| File | Covers |
|---|---|
| `conftest.py` | Fixtures and the sample FASTA/FASTQ/GFF/VCF/SAM/GenBank documents |
| `test_units.py` | Alphabets, parsers, format detection, settings, request context |
| `test_health.py` | Root, liveness, readiness, version, request ids, 404 shape |
| `test_sequences.py` | The eleven sequence endpoints and their error paths |
| `test_fasta.py` | The fourteen FASTA utilities |
| `test_fastq.py` | The five FASTQ utilities |
| `test_files.py` | Upload analysis for every recognised format, plus extraction |
| `test_conversions.py` | The conversion matrix, each supported pair, consensus |
| `test_security.py` | API key handling and rate limiting |
| `test_logging.py` | Log record shape |

## How it runs

Integration tests reach the app through `httpx.ASGITransport`, which exercises
the full middleware and exception-handling stack without binding a socket. That
is what makes assertions on `X-Request-ID`, rate-limit headers and error
envelopes meaningful rather than a test of the handler function alone.

`asyncio_mode = "auto"` in `pyproject.toml` means async tests need no marker.

The application is built once per session by the `app` fixture. Tests that need
different settings — a required API key, a tiny rate limit — build their own
instance with `create_app()` so nothing leaks between tests.

Fixtures write real files to `tmp_path` and the `bam_file` fixture builds a
genuine BAM with pysam from the SAM fixture, so the BAM path is tested against a
real binary file rather than a mock.

## What is deliberately covered

Several tests exist because the behaviour was previously wrong, and a comment
says so where that is the point:

- `test_iupac_ambiguity_codes_are_accepted_with_a_warning` — the old alphabet
  rejected `N` and `R`, so ordinary DNA files failed validation.
- `test_get_n_sequences_warns_when_asking_for_too_many` — warnings used to be
  built and then discarded before the response was assembled.
- `test_fasta_is_detected_from_content_despite_a_txt_extension` — detection used
  to read only the extension.
- `test_fasta_to_json_is_produced_natively` — `SeqIO` has no JSON writer, so
  this conversion always failed despite being advertised.
- `test_fasta_to_genbank_infers_molecule_type` — `SeqIO` refuses to write
  GenBank without that annotation.
- `test_empty_read_is_rejected_rather_than_dividing_by_zero` — a zero-length
  quality string used to raise `ZeroDivisionError` and return a 500.
- `test_extract_gff_skips_out_of_range_coordinates` — out-of-range features used
  to yield silent empty sequences.
- `test_consensus_reports_mismatched_reference_alleles` — mismatched variants
  were skipped with no indication to the caller.
- `test_event_is_not_double_encoded` — a misconfigured structlog bridge nested
  each JSON record inside the next one's `event` field.

## Coverage

The gate is 90%, enforced by `--cov-fail-under=90` in `pyproject.toml`; a drop
below it fails the run and the CI job. `app/main.py` is omitted — it is wiring,
executed on every import and asserted by the smoke job in CI.

An HTML report:

```bash
docker compose run --rm test pytest --cov-report=html:/app/htmlcov
```

The uncovered remainder is mostly defensive: parse-error branches for corrupt
binary files, and probe failure paths that need a broken pysam to reach.

## Useful invocations

```bash
# One file, one test, no gate
docker compose run --rm test pytest tests/test_fasta.py::test_merge -v --no-cov

# By keyword
docker compose run --rm test pytest -k "consensus" --no-cov

# First failure, with the debugger
docker compose run --rm test pytest -x --pdb --no-cov

# Slowest ten
docker compose run --rm test pytest --durations=10 --no-cov
```

## Beyond the suite

`docker compose run --rm lint` runs `ruff check`, `ruff format --check` and
`mypy --strict`. CI runs the same command, so a green local lint means a green
CI lint.

CI additionally builds the runtime image, starts it, waits for the Docker
healthcheck to report healthy, and probes `/health/ready`, the OpenAPI document
and a real endpoint. That covers what the ASGI-transport tests cannot: that the
image boots, that uvicorn binds, and that the healthcheck itself works.
