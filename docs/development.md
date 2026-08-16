# Development

Everything runs in Docker. You need Docker Engine 24+ with Compose v2, and
nothing else — no Python on the host, no virtualenv, no `pip`.

pysam links against htslib. Building it on a developer machine means installing
zlib, bzip2, lzma and curl headers and hoping the versions line up; on Windows
it does not build at all. The container settles that once.

## Getting going

```bash
git clone https://github.com/bhagesh-h/bioAPI.git
cd bioAPI
docker compose build
docker compose run --rm test
```

Then serve it:

```bash
docker compose up api          # http://127.0.0.1:8000/docs
```

## The compose services

| Service | Purpose |
|---|---|
| `api` | The production image, port 8000, healthchecked |
| `test` | Dev image, runs `pytest` with the coverage gate |
| `lint` | `ruff check`, `ruff format --check`, `mypy --strict` |
| `format` | Rewrites source with `ruff format` and applies safe fixes |

`test`, `lint` and `format` bind-mount `app/` and `tests/`, so a code change
takes effect without a rebuild. `test` and `lint` mount read-only; `format`
needs write access and runs as root so it can write through the mount.

Rebuild only when dependencies or the Dockerfile change:

```bash
docker compose build
```

## The loop

```bash
# One file
docker compose run --rm test pytest tests/test_fasta.py

# One test, verbose, no coverage gate
docker compose run --rm test pytest tests/test_fasta.py::test_merge -v --no-cov

# Anything matching a name
docker compose run --rm test pytest -k "consensus or variant" --no-cov

# Stop at the first failure and drop into the debugger
docker compose run --rm test pytest -x --pdb --no-cov
```

Before opening a PR:

```bash
docker compose run --rm format
docker compose run --rm lint
docker compose run --rm test
```

## Code style

`ruff` handles both linting and formatting; there is no separate `black` step.
`mypy --strict` runs over `app/`. Configuration for all three lives in
`pyproject.toml`.

Two deliberate exemptions:

- `untyped_calls_exclude = ["Bio", "pysam"]` — both ship `py.typed` but leave
  most functions unannotated. Strict call checking stays on for our own code.
- `tests/*` may use `pathlib` inside async tests. Blocking the loop for
  microseconds to read a fixture keeps the tests readable.

## Adding an endpoint

1. **Schema** in `app/schemas/` — describe every field, add an example to the
   request model.
2. **Service method** in `app/services/` — pure logic, raising a `BioAPIError`
   subclass on bad input. Call `add_warning(...)` for anything the caller should
   know but that does not make the result wrong.
3. **Route** in `app/api/v1/endpoints/` — validate, call the service, wrap in
   `EnvelopeResponse.ok(...)`. Give it a `summary` and a `description`; they are
   what people read in Swagger.
4. **Register** it if the module is new: add the router to
   `app/api/v1/router.py` and a tag to `TAGS_METADATA` in `app/main.py`.
5. **Tests** — the happy path, each error path, and any warning the endpoint can
   emit.

A route body that is longer than a few lines, or that branches on the shape of
the data, belongs in a service.

## Debugging

Structured logs are hard to skim locally. Switch renderers:

```bash
docker compose run --rm -e LOG_FORMAT=console -e LOG_LEVEL=DEBUG api
```

To see internal exception detail in error responses:

```bash
docker compose run --rm -e DEBUG=true -e ENVIRONMENT=development api
```

`DEBUG` is ignored when `ENVIRONMENT=production`, so this cannot be switched on
by accident in a live deployment.

A shell in the dev image:

```bash
docker compose run --rm --entrypoint sh test
```

## Dependencies

Runtime pins live in `requirements.txt`, tooling in `requirements-dev.txt`
(which includes the runtime set). Both are exact pins so an image built today
matches one built last month.

To move a version: edit the pin, rebuild, run the suite.

```bash
docker compose build --no-cache
docker compose run --rm test
```

To see what current would resolve to without committing to it:

```bash
docker run --rm python:3.12-slim sh -c \
  "pip install -q --dry-run --report /tmp/r.json fastapi pydantic biopython pysam \
   && python -c \"import json;[print(i['metadata']['name'],i['metadata']['version']) for i in json.load(open('/tmp/r.json'))['install']]\""
```
