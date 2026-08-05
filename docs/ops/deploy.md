# Deployment runbook (Release 0, free-tier stack)

**Task:** T-040. **Constraint:** zero budget (D6) — every component below is on a
free tier. **Durability rule:** no Render free Postgres (expires after 90 days);
Postgres and Redis are external, persistent free tiers.

## Topology

```
 Browser ──HTTPS──> Render Web (frontend, Next.js)
                         │  (NEXT_PUBLIC_API_URL, build-time)
                         ▼
 Browser ──HTTPS/cookies──> Render Web (backend, FastAPI)
                         ├── Neon (PostgreSQL, TLS)     ← persistent
                         └── Upstash (Redis, rediss://) ← agent chat memory
 GitHub Actions (cron) ── nightly encrypted pg_dump ──> Actions artifact (14d)
```

Everything is defined as code in [`render.yaml`](../../render.yaml). Datastore
URLs are injected as Render secrets (`sync: false`), never committed.

## One-time provisioning (operator)

These steps need real accounts and secrets, so they are performed by a human in
each vendor's dashboard. None cost money.

1. **Neon Postgres** (https://neon.tech, free tier)
   - Create a project + database.
   - Copy the **pooled** connection string; convert the scheme to
     `postgresql+asyncpg://…` for the app's `DATABASE_URL`.
   - Neon has the `citext` extension available; the app's first migration runs
     `CREATE EXTENSION IF NOT EXISTS citext`.
2. **Upstash Redis** (https://upstash.com, free tier)
   - Create a database; copy the `rediss://` URL → `REDIS_URL`.
3. **Render** (https://render.com, free tier)
   - New → Blueprint → point at this repo; Render reads `render.yaml`.
   - When prompted, paste the secrets: `DATABASE_URL`, `REDIS_URL`,
     `GROQ_API_KEY`, `FRONTEND_ORIGIN` (the frontend's Render URL),
     `NEXT_PUBLIC_API_URL` (the backend's Render URL). `SECRET_KEY` is generated.
   - The backend `startCommand` runs `alembic upgrade head` before serving.
4. **Seed (optional, non-prod only):** the demo seed refuses to run when
   `ENVIRONMENT=production`. For a demo environment, run
   `python -m scripts.seed_demo` with `ENVIRONMENT=development`.

## Verification (acceptance)

- Backend `GET /health` returns `{"status":"healthy"}`.
- Register a user in the deployed frontend; confirm the session cookie is
  `Secure; HttpOnly; SameSite=Lax` (DevTools → Application → Cookies).
- Confirm the browser reaches the API at the correct public URL (no
  `http://backend:8000` — that was the INF-08 bug).
- Confirm **no datastore ports are public**: Neon/Upstash are reached only via
  their TLS URLs from the backend; nothing is exposed on host ports.

## Local development

Use Docker Compose for local parity (local Postgres + Redis, published ports are
fine for dev only):

```bash
docker-compose up -d      # applies migrations, serves backend on :8000
cd frontend && npm run dev # frontend on :3000
```

Local Postgres/Redis in `docker-compose.yml` are for development only — do not
expose those ports or reuse the compose credentials in any deployed environment.

## Backups

Nightly encrypted `pg_dump` runs in GitHub Actions — see
[`backup.md`](backup.md) and [`restore.md`](restore.md).

> **Status:** the vendor provisioning above is the remaining operator work for
> the R0 exit gate. All infra-as-code (`render.yaml`), the backup workflow, and
> the restore drill procedure are in the repo and ready to execute.
