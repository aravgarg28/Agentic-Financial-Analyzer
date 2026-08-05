# Restore drill log (T-041)

Each entry records one full download → decrypt → restore → verify cycle of a
nightly encrypted backup, per [`restore.md`](restore.md). A completed drill is
required for the R0 exit gate.

| Date (UTC) | Backup artifact | Restored into | Row counts (households/users/accounts/transactions/budgets) | Orphan check | Operator | Notes |
|------------|-----------------|---------------|-------------------------------------------------------------|--------------|----------|-------|
| _pending_  | _pending_       | _pending_     | _pending_                                                   | _pending_    | _pending_ | First drill not yet performed — requires a provisioned Neon DB + a completed backup run (follows T-040). |

## How to add an entry

After running the drill in `restore.md`, append a row above with the observed
row counts and the orphan-check result (expected `0`). Keep every historical
entry — the log is the evidence that backups are actually restorable.
