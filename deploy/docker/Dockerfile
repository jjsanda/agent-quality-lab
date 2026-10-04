# Python agent image (used by CI's build job and for running `aql` in a container).
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

# Install dependencies first (cached layer), then the source.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra anthropic --extra otel

COPY data ./data
COPY evaluation ./evaluation

# Run as a non-root user.
RUN useradd --create-home --uid 10001 aql && chown -R aql:aql /app
USER aql

ENTRYPOINT ["aql"]
CMD ["info"]
