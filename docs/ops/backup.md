# Encrypted backups (T-041)

**Goal:** a recoverable, encrypted, off-database copy of production data every
night, at zero cost (INF-10, D8).

## How it works

The workflow [`.github/workflows/backup.yml`](../../.github/workflows/backup.yml)
runs on a nightly `cron`:

1. `pg_dump` the Neon database (custom format).
2. Compress with `zstd`.
3. Encrypt with [`age`](https://age-encryption.org) using a public recipient key
   — the private key is **never** in CI.
4. Upload the `.age` file as a GitHub Actions artifact with 14-day retention.

Because encryption uses only the **public** key, a compromised CI environment
cannot decrypt any backup. Decryption requires the private key, which the
operator holds offline.

## Secrets (operator sets these in the repo's Actions secrets)

| Secret | Value |
|--------|-------|
| `BACKUP_DATABASE_URL` | Neon connection string (libpq form, `postgresql://…`) |
| `AGE_PUBLIC_KEY` | `age1…` recipient public key |

Generate the key pair once, locally, and store the private key in a password
manager (never in the repo):

```bash
age-keygen -o afa-backup-key.txt   # prints the public key; keep the file offline
```

## Restoring

See [`restore.md`](restore.md). Perform the drill at least once and record the
result in `restore-drills.md`.

> **Workflow-scope note:** pushing files under `.github/workflows/` requires a
> GitHub token with the `workflow` scope. If your push is rejected, merge the
> workflow via the GitHub UI or a PAT with that scope (the same constraint
> applied to `ci.yml`, parked on `ci-workflow-pending`).
