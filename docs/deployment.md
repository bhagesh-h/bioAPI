# Deployment

The image built here is the one CI tests and the one you deploy. There is no
separate production build path.

## Build

```bash
docker build --target runtime -t bioapi:0.0.1 .
```

The Dockerfile has three stages:

- **builder** — installs compilers and htslib headers, builds a virtualenv at
  `/opt/venv`. None of it reaches the final image.
- **runtime** — the virtualenv plus the small shared libraries htslib links
  against, running as uid 10001 with a `HEALTHCHECK` on `/health/live`.
- **dev** — runtime plus pytest, ruff and mypy. Used by CI and local testing,
  never deployed.

The result is roughly 500 MB, most of it numpy, Biopython and pysam.

## Run

```bash
docker run -d --name bioapi -p 8000:8000 --env-file .env bioapi:0.0.1
```

Or with compose:

```bash
docker compose up -d api
```

`PORT` is honoured, so platforms that assign one (Render, Cloud Run, Heroku)
work without changes.

## Before going live

Defaults are chosen for a first run on a laptop, not for the public internet.

| Setting | Change it to | Why |
|---|---|---|
| `ENVIRONMENT` | `production` | Suppresses internal error detail regardless of `DEBUG` |
| `API_KEY` | a long random value | Otherwise every `/api/v1` route is open |
| `BACKEND_CORS_ORIGINS` | your own origins | `*` also disables credentialed CORS |
| `DOCS_ENABLED` | `false` for a private API | Hides `/docs`, `/redoc` and the schema |
| `RATE_LIMIT_DEFAULT` | suit your traffic | The default 120/minute is a starting point |
| `MAX_UPLOAD_SIZE_MB` | suit your inputs | Genomic files outgrow 50 MB quickly |

Generate a key with `openssl rand -hex 32`. Inject it through your platform's
secret store; never bake it into the image or commit a `.env`.

## Probes

| Path | Use | Behaviour |
|---|---|---|
| `/health/live` | liveness | 200 while the process serves; restart the container if it fails |
| `/health/ready` | readiness | Parses a record with Biopython and loads pysam; 503 if either fails |

Point liveness at `/health/live` and readiness at `/health/ready`. Using the
readiness probe for liveness will restart containers over transient dependency
problems rather than routing around them.

Kubernetes:

```yaml
livenessProbe:
  httpGet: { path: /health/live, port: 8000 }
  initialDelaySeconds: 10
  periodSeconds: 30
readinessProbe:
  httpGet: { path: /health/ready, port: 8000 }
  initialDelaySeconds: 5
  periodSeconds: 10
```

Both paths, and `/metrics`, bypass the API key and the rate limiter.

## Scale

The application is stateless — nothing is written outside per-request temporary
files — so replicas scale horizontally with no coordination.

One caveat: the rate limiter counts in process memory. Each replica enforces its
own budget, so N replicas allow N times the configured limit in aggregate. If
you need a true global limit, enforce it at the ingress or API gateway and set
`RATE_LIMIT_ENABLED=false` here.

Sizing: uvicorn runs a single worker per container by design; scale by adding
containers rather than workers, so the orchestrator's own health checks and
restarts operate at the right granularity. Allow roughly 512 MB per container
plus headroom for the largest upload you accept.

## Observability

Logs are one JSON object per line on stdout, each carrying `request_id`,
`service`, `version`, `environment` and a timestamp. Any aggregator that reads
container stdout will index them without a parser. Set `LOG_FORMAT=console` only
for local work.

`/metrics` exposes Prometheus metrics — request counts, latency histograms and
process statistics — with health paths excluded so probe traffic does not skew
them. Turn it off with `METRICS_ENABLED=false`.

An inbound `X-Request-ID` is honoured and echoed, so a correlation id set at
your edge flows through the logs and the response envelope.

## Reverse proxy

Behind nginx, Traefik or a cloud load balancer:

- Forward `X-Forwarded-For`; the limiter reads it to identify callers.
- Cap the request body at the proxy too — rejecting at the edge is cheaper.
- Terminate TLS at the proxy; the container speaks plain HTTP.

## Render

[`render.yaml`](../render.yaml) is a Docker blueprint with `API_KEY` generated
on the platform and the health check pointed at `/health/ready`. Narrow
`BACKEND_CORS_ORIGINS` before you use it for anything real.

## Upgrading

```bash
docker compose build --no-cache
docker compose run --rm test
docker compose run --rm lint
```

Deploy only after both pass. The CI workflow runs the same commands plus a live
smoke test of the runtime image.
