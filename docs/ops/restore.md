# Restore runbook + drill (T-041)

Restoring a nightly encrypted backup ([`backup.md`](backup.md)). Backup
correctness is existential, so this procedure must be **drilled at least once**
and the result recorded in [`restore-drills.md`](restore-drills.md).

## Prerequisites

- The **private** age key (kept offline by the operator).
- `age`, `zstd`, and `pg_restore` (postgresql-client) installed locally.
- A scratch database to restore INTO — never restore over production.

## Steps

```bash
# 1. Download the artifact from the GitHub Actions run (Actions → backup run →
#    Artifacts), then decrypt and decompress it.
age -d -i afa-backup-key.txt afa-backup-YYYYMMDDTHHMMSSZ.dump.zst.age \
  | zstd -d > afa-backup.dump

# 2. Create a scratch database (local or a fresh Neon branch).
createdb afa_restore_check       # or create a Neon branch

# 3. Restore into it.
pg_restore --clean --if-exists --no-owner \
  --dbname "postgresql://…/afa_restore_check" afa-backup.dump

# 4. Verify (see queries below), then drop the scratch database.
dropdb afa_restore_check
```

## Verification queries

Row counts should be non-zero and consistent with production expectations:

```sql
SELECT 'households' AS t, count(*) FROM households
UNION ALL SELECT 'users',        count(*) FROM users
UNION ALL SELECT 'accounts',     count(*) FROM accounts
UNION ALL SELECT 'transactions', count(*) FROM transactions
UNION ALL SELECT 'budgets',      count(*) FROM budgets;

-- Spot-check integrity: every transaction resolves to a real household+account.
SELECT count(*) AS orphans
FROM transactions t
LEFT JOIN households h ON h.id = t.household_id
LEFT JOIN accounts   a ON a.id = t.account_id
WHERE h.id IS NULL OR a.id IS NULL;   -- expect 0
```

## Drill

Run the full download → decrypt → restore → verify cycle once against a scratch
database, then append a dated entry to [`restore-drills.md`](restore-drills.md)
with the row counts observed and the orphan-check result.

> **Status:** the drill requires a real backup artifact, which requires the
> backup workflow to have run against a provisioned Neon database — i.e. it
> follows the T-040 provisioning. It is the last remaining item for the R0 exit
> gate and is an operator action.
