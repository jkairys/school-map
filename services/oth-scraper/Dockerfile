FROM python:3.11-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml README.md ./
RUN uv sync --no-dev

COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

ENV PYTHONPATH=/app/src
# Put uv's project venv on PATH so console scripts like `oth` are runnable
# directly: `docker compose exec api oth list ls` works without `uv run`.
ENV PATH=/app/.venv/bin:$PATH

# Entrypoint is overridden per service in docker-compose.yml
CMD ["uv", "run", "python", "-m", "oth_scraper.api.entrypoint"]
