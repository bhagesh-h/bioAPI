# syntax=docker/dockerfile:1
#
# Docker is the only supported toolchain for bioAPI.
#
#   builder  compiles the dependency set into a virtualenv. pysam links against
#            htslib, so this stage carries a compiler and the -dev headers in
#            case no wheel exists for the target platform.
#   runtime  the deployable image: the virtualenv, the handful of shared
#            libraries htslib needs, an unprivileged user and a healthcheck.
#   dev      runtime plus pytest, ruff and mypy. Used by compose and CI, never
#            deployed.
#
#   docker build --target runtime -t bioapi:latest .
#   docker build --target dev     -t bioapi:dev .

ARG PYTHON_VERSION=3.12

# ─── builder ──────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        zlib1g-dev \
        libbz2-dev \
        liblzma-dev \
        libcurl4-openssl-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

# ─── runtime ──────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=0.0.1
LABEL org.opencontainers.image.title="bioAPI" \
      org.opencontainers.image.description="REST API for common bioinformatics workflows" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.source="https://github.com/bhagesh-h/bioAPI" \
      org.opencontainers.image.licenses="GPL-3.0-only"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# Shared libraries htslib links against at run time, plus curl for HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcurl4 \
        libbz2-1.0 \
        liblzma5 \
        zlib1g \
        curl \
    && rm -rf /var/lib/apt/lists/*

# The virtualenv stays root-owned: the service reads it but must not modify it.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser && chown appuser:appuser /app

COPY --chown=appuser:appuser ./app /app/app

USER appuser

EXPOSE 8000

# Liveness only — readiness is a heavier probe and belongs to the orchestrator.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health/live" || exit 1

STOPSIGNAL SIGTERM

# exec form via sh so ${PORT} is expanded but uvicorn still becomes PID 1 and
# receives SIGTERM directly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

# ─── dev ──────────────────────────────────────────────────────────────────────
FROM runtime AS dev

USER root

COPY requirements.txt requirements-dev.txt /app/
RUN pip install -r /app/requirements-dev.txt

COPY --chown=appuser:appuser pyproject.toml /app/
COPY --chown=appuser:appuser ./tests /app/tests

USER appuser

CMD ["pytest"]
