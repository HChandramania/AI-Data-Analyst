FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

FROM python:3.13-slim
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DBO_DATA_DIR=/app/data DBO_ENVIRONMENT=production
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir /app/data && chown app:app /app/data
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=4)"]
CMD ["python", "-m", "app.serve"]
