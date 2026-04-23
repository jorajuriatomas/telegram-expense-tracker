# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime dependencies first to leverage Docker layer caching.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Application source.
COPY app ./app
COPY pyproject.toml ./

EXPOSE 8000

# Uvicorn handles concurrency via the asyncio event loop. The worker count
# can be raised via UVICORN_WORKERS for CPU-bound deployments.
ENV BOT_SERVICE_HOST=0.0.0.0 \
    BOT_SERVICE_PORT=8000

CMD ["sh", "-c", "uvicorn app.asgi:app --host ${BOT_SERVICE_HOST} --port ${BOT_SERVICE_PORT}"]
