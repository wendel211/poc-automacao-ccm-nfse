FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install -e ".[dev]" 2>/dev/null || pip install \
    pandas openpyxl pydantic httpx tenacity loguru typer playwright rich

RUN python -m playwright install chromium --with-deps

COPY src/ ./src/
COPY input/ ./input/

RUN mkdir -p output/evidencias

VOLUME ["/app/output"]

ENTRYPOINT ["python", "-c", \
    "from src.pipeline import run; from pathlib import Path; run(Path('input/janabril2026_amostra_5x5.xlsx'))"]
