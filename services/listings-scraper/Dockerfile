FROM python:3.11-slim

WORKDIR /app

# Firefox runtime libs for camoufox (workers bootstrap a stealth browser).
# The api container doesn't strictly need these but a single image keeps the
# build matrix simple — both services share /app/.venv and the same entrypoint
# selection per docker-compose.yml.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libxtst6 \
    libpci3 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libegl1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

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
CMD ["uv", "run", "python", "-m", "listings_scraper.api.entrypoint"]
