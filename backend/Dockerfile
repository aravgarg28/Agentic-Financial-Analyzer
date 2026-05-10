FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for PostgreSQL and others
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

RUN pip install poetry

COPY pyproject.toml ./
RUN touch README.md

# Install dependencies directly into the system environment to avoid virtualenv overhead in Docker
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

COPY . .
