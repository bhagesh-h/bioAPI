# Architecture

## Layout

```text
bioAPI/
├── app/
│   ├── main.py                 # application factory and wiring
│   ├── core/                   # cross-cutting concerns
│   │   ├── config.py           # environment-driven settings
│   │   ├── context.py          # per-request id and warning buffer
│   │   ├── errors.py           # exception types and handlers
│   │   ├── logging.py          # structlog / stdlib bridge
│   │   ├── middleware.py       # request context, body limits, security headers
│   │   ├── rate_limit.py       # fixed-window limiter
│   │   └── security.py         # API key dependency
│   ├── api/
│   │   ├── deps.py             # shared route dependencies
│   │   ├── health.py           # root-level probes, outside /api/v1
│   │   └── v1/
│   │       ├── router.py       # aggregates the v1 endpoints
│   │       └── endpoints/      # sequences, fasta, fastq, files, conversions, formats
│   ├── schemas/                # Pydantic request and response models
│   ├── services/               # business logic, one module per domain
│   └── utils/                  # pure helpers: alphabets, parsers, detection, tempfiles
├── tests/
├── docs/
├── Dockerfile                  # builder → runtime → dev
├── docker-compose.yml          # api, test, lint, format
└── pyproject.toml              # ruff, mypy, pytest, coverage
```

## The layers

**Endpoints** parse and validate the request, call one service method, and wrap
the result. They contain no branching on data and no file handling beyond
streaming an upload to a temporary path.

**Services** hold the logic. They accept schema objects or paths, raise
`BioAPIError` subclasses, and know nothing about HTTP — no status codes, no
`Request`, no `Response`. That is what makes them straightforward to unit test.

**Utils** are pure functions: alphabet checks, FASTA and FASTQ parsing, format
sniffing, temporary-file handling. No application state.

**Schemas** are the contract. Every field carries a description and most models
carry an example, so the OpenAPI document is useful without extra prose.

Dependencies point one way: endpoints → services → utils. Nothing in `services`
or `utils` imports from `api`.

## Decisions worth knowing

### The response envelope is filled from context variables

`warnings` and `request_id` do not travel through function signatures. The
request middleware opens a `RequestContext`, and any code running inside it can
call `add_warning(...)`. `EnvelopeResponse.ok()` collects them when the response
is built.

The alternative — returning `(result, warnings)` tuples from every service
method — pushes an HTTP concern into every signature in the codebase. The
earlier version of this API took a third path: it built warning lists and then
dropped them on the floor, so callers never saw them.

### Errors are typed, with stable codes

`BioAPIError` subclasses carry both an HTTP status and an `ErrorCode`. Handlers
render them into the same envelope a success uses. A client branches on
`error.code`, never on message text.

The unhandled-exception handler logs a full traceback and returns a generic
message; internals are exposed only when `DEBUG` is on outside production.

### Format detection reads the file

`utils/detection.py` sniffs the first 64 KB and combines that with the filename
extension, returning a `Confidence` and a human-readable reason. Extension-only
detection reported a FASTA file named `sample.txt` as plain text and analysed
nothing. GFF and GTF are told apart by their attribute-column syntax, and FASTQ
from headerless SAM by the `+` on the third line.

### The conversion matrix is explicit

`schemas/conversion.py` declares which source-to-target pairs work and why the
others do not. The pair is validated before the upload is read, so an impossible
request costs no I/O and produces an explanation rather than a Biopython
traceback. `GET /api/v1/formats` publishes the same table.

Two conversions needed real work rather than a pass-through to `SeqIO`:

- **JSON** has no `SeqIO` writer at all, so it is written natively, including
  quality scores and features when the source has them.
- **GenBank and EMBL** require a `molecule_type` annotation that FASTA does not
  carry. It is inferred from sequence composition, and the inference is reported
  as a warning.

### Rate limiting is implemented here, not delegated

slowapi resolves a request's limit by walking `app.routes` and reading each
route's `endpoint`. FastAPI 0.141 wraps included routers in an internal
container that exposes no `endpoint`, so the lookup returns `None` and the
limiter silently allows everything. Rather than pin an old FastAPI, the limiter
is a fixed-window counter in `core/rate_limit.py`, keyed on the API key when one
is present and the client address otherwise.

### Logging renders exactly once

structlog's processor chain ends at `wrap_for_formatter`, which passes the event
dictionary to a `ProcessorFormatter` on the stdlib handler. That formatter owns
the only renderer. Putting a renderer at the end of structlog's own chain as
well serialises each record twice and nests the whole document inside the next
one's `event` field — `tests/test_logging.py` pins this down.

### Temporary files are context-managed

`utils/tempfiles.py` streams uploads in 1 MB chunks, checking the running total
against the limit, and removes the file on the way out even if the handler
raised. File-producing endpoints read the result into memory before the context
closes and return it as a `Response`; returning a `FileResponse` pointed at a
path that the context manager is about to delete is a race.

This is bounded by `MAX_UPLOAD_SIZE_MB`. Outputs much larger than that would
want streaming with a longer-lived temporary file.

### Health checks do work

`/health/ready` parses a FASTA record with Biopython and loads pysam's compiled
extension. A container whose htslib bindings are broken fails readiness and is
pulled from the load balancer instead of 500-ing on the first real request.
`/health/live` stays trivial — liveness should not fail because a dependency is
briefly unhappy.

## Request path

```text
   client
     │
     ▼
RequestContextMiddleware   assigns the request id, opens the warning scope, logs
     │
     ▼
CORSMiddleware             origin checks
     │
     ▼
BodySizeLimitMiddleware    rejects oversized Content-Length
     │
     ▼
GZipMiddleware             compresses responses over 1 KB
     │
     ▼
SecurityHeadersMiddleware  adds the hardening headers
     │
     ▼
RateLimitMiddleware        fixed window; health and metrics exempt
     │
     ▼
route → require_api_key → endpoint → service → utils
```

Starlette runs middleware in reverse registration order, so the last registered
is outermost. The request context is registered last on purpose: it wraps
everything, and every log line — including one from a rejected request — carries
a request id.
