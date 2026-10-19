# DocTune backend image (API, Celery workers and beat share it). Builds for amd64 and arm64.
# Build from the REPO ROOT:  docker build -f backend/Dockerfile .   (the Kaggle backend embeds notebook/)
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libmagic1 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra ml
COPY backend/src ./src
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
# the training package that the Kaggle backend ships inside each kernel (ADR-0002)
COPY notebook/pyproject.toml notebook/README.md /app/notebook_pkg/
COPY notebook/doctune_nb /app/notebook_pkg/doctune_nb
RUN uv sync --frozen --no-dev --extra ml

RUN useradd --create-home --uid 10001 doctune && mkdir -p /app/.data/storage /app/.data/models && chown -R doctune /app/.data
ENV HF_HOME=/app/.data/models/hf NOTEBOOK_SRC_DIR=/app/notebook_pkg
USER doctune
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "doctune.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
