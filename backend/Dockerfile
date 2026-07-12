FROM python:3.11-slim

WORKDIR /app

# asyncpg needs no libpq, but keep gcc for any wheels that build from source
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==2.4.1"

# Copy dependency manifests first for layer caching; install from the lockfile
COPY pyproject.toml poetry.lock ./

# Install into the system environment (no venv layer) — runtime deps only
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

COPY . .
