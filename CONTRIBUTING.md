# Contributing

Thanks for taking a look. This project is small enough that the process is
short.

## Ground rule: Docker only

Every build, test and lint runs in a container. Please do not add instructions
that require Python, `pip` or a virtualenv on the host — pysam's htslib bindings
are exactly the kind of thing that works on one machine and not the next, and
keeping the toolchain in the image is what stops that from being anyone's
problem.

```bash
docker compose build
docker compose run --rm test
```

## Before you open a pull request

```bash
docker compose run --rm format   # ruff format + safe fixes
docker compose run --rm lint     # ruff check, format check, mypy --strict
docker compose run --rm test     # full suite, 90% coverage gate
```

All three must pass. CI runs the same commands, so a green local run is a green
CI run.

## What a good change looks like

**Keep routes thin.** A route validates, calls one service method and wraps the
result. Logic and branching belong in `app/services/`; anything pure belongs in
`app/utils/`. Services must not import from `app/api/`.

**Raise typed errors.** Use a `BioAPIError` subclass with a stable `ErrorCode`
and structured `details`. Never raise a bare `HTTPException` from a service.

**Say something when you skip something.** If an operation ignores 12 malformed
records, call `add_warning(...)`. Silently returning a shorter result is how
several of the bugs in the 0.0.1 changelog went unnoticed.

**Describe your schema fields.** Every field gets a `description`; request
models get an example. The OpenAPI document is the reference people actually
read.

**Test the error paths.** New endpoints need the happy path, each failure mode,
and any warning they can emit. When you fix a bug, add the test that would have
caught it and say so in a comment — see `tests/test_fastq.py` for the pattern.

## Commit messages

Present tense, imperative, explaining why where it is not obvious:

```
Reject FASTQ reads with an empty quality string

A zero-length quality line divided by zero in the mean-quality
calculation and surfaced as a 500. It is now a parse error naming
the read.
```

## Dependencies

Runtime pins live in `requirements.txt`, tooling in `requirements-dev.txt`. Pin
exact versions — reproducibility is the point. When you bump one, rebuild
without cache and run the suite:

```bash
docker compose build --no-cache
docker compose run --rm test
```

## Reporting a bug

Include the endpoint, the request, the response body, and the `request_id` from
the envelope or the `X-Request-ID` header. That id ties the response to the log
lines for the same request, which usually makes the cause obvious.

## Security

Please do not open a public issue for a security problem. Contact the maintainer
directly.
