FROM python:3.14-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg git && \
    rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS builder
WORKDIR /app
COPY pyproject.toml .
RUN uv pip install --system -e ".[all]"

FROM base AS runtime
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY src/ ./src/
COPY VERSION .
ENTRYPOINT ["python", "-m", "rover_swarm"]

FROM runtime AS dev
RUN uv pip install --system -e ".[dev,security,robot]"
COPY . .
RUN pre-commit install

FROM runtime AS sim
RUN apt-get install -y --no-install-recommends xvfb && \
    uv pip install --system -e ".[simulation]"
COPY scripts/ ./scripts/
COPY tests/ ./tests/
