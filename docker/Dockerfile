FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY negotium ./negotium
COPY templates ./templates
COPY config ./config

RUN pip install --upgrade pip \
 && pip install ".[dev]" \
 && pip install -e .

RUN adduser --disabled-password --gecos "" negotium \
 && mkdir -p /var/ng/workspaces /app/archive \
 && chown -R negotium:negotium /var/ng /app

USER negotium
EXPOSE 8080

CMD ["negotium", "serve"]
