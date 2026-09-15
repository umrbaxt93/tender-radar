# Single image for both processes: the web app and the worker. They differ only in the
# command, so one build serves both and they can never drift apart in dependencies.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependency metadata first so the layer is reused when only source changes.
COPY pyproject.toml README.md ./
RUN mkdir -p radar/source radar/classify radar/templates \
    && touch radar/__init__.py radar/source/__init__.py radar/classify/__init__.py \
    && pip install --no-cache-dir -e .

COPY alembic.ini ./
COPY alembic ./alembic
COPY radar ./radar
COPY samples ./samples
COPY scripts ./scripts

# Runs as a non-root user; out/ is the only directory the app writes to.
RUN useradd --system --create-home --uid 10001 radar \
    && mkdir -p /app/out && chown -R radar:radar /app
USER radar

EXPOSE 8000
CMD ["python", "-m", "radar", "web", "--host", "0.0.0.0", "--port", "8000"]
