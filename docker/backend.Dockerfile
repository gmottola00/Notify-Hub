# syntax=docker/dockerfile:1
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first, from the lockfile, so a code-only change reuses this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra postgres --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --extra postgres

EXPOSE 8000

# Migrations and the VAPID key load inside the lifespan, before /health answers.
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "notify_hub.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
