# Ingestion Design

Status: Proposed. Principle: **one canonical transaction model** (`data-model.md` › transactions) independent of any provider. Every source (CSV, OFX/QFX, PDF, aggregator, manual) funnels through the same **stage → validate → dedup → review → commit** pipeline, so correctness and dedup logic are written once.

## 1. Canonical pipeline (all sources)

```
source ──► ImportBatch(staged)
             └─► ImportedRecord[] (raw JSONB + parsed fields + validation + dedup verdict)
                    └─► user review (accept/skip/merge; fix category)
                           └─► commit ──► Transaction[] (with provenance)
                                            └─► post-commit jobs: recurring detect, transfer candidates, alert scan
       rollback(batch) ──► delete exactly this batch's committed transactions
```

- **Idempotency:** a batch is identified by `file_checksum` (CSV/OFX) or provider `cursor` range (aggregator). Re-submitting the same file surfaces "already imported" instead of duplicating.
- **Atomph commit:** commit runs in a transaction; on large batches (>~500 rows) it is handed to the worker (`csv_commit` job) to avoid request timeouts on free tiers.
- **Rollback:** allowed while no downstream edits reference the rows; deletes by `import_batch_id`; audited.

## 2. CSV import (R1 — the guaranteed path, D3)

### 2.1 Upload
- Accept `.csv`/`.txt`, size cap (e.g. 5 MB, ~tens of thousands of rows — comfortably above D9), MIME+extension check, virus-of-the-poor sanity (no executable content; CSV parsed, never executed). Stored as a `documents` row for provenance.

### 2.2 Column mapping (saved presets)
- Parser sniffs delimiter + encoding (utf-8/utf-8-sig/latin-1) and header row.
- Mapping UI maps source columns → canonical fields: `booked_date`, `amount` (+ sign convention: single signed column, or separate debit/credit columns), `description`, optional `category`, optional `balance`, `currency` (default household base, D1).
- **Saved mappings** (`column_mappings`) keyed by institution so repeat imports are one click. A small library of built-in presets for common US banks ships as data (not code).

### 2.3 Row validation
- Per row: parse date (using mapping's date format, tz = household), parse amount → `amount_minor` (reject/flag non-numeric, thousands separators handled, parentheses/`DR`/`CR` conventions), currency, non-empty description. Failures become row-level `validation` warnings/errors; the row is shown but not committable until resolved or skipped.

### 2.4 Duplicate detection
- **Fingerprint:** `hash(account_id, booked_date, amount_minor, normalized_description)`.
- **Exact match** against existing committed transactions → verdict `duplicate` (default skip).
- **Near-dup** (same fingerprint within the batch, or same amount+date+similar desc) → verdict `near_dup`, surfaced for user decision (legitimate repeats exist — two identical coffees — so this is review, not auto-drop).
- **External id:** if the source carries a stable id (OFX FITID, aggregator id), it becomes `external_id` and is the strong dedup key (partial unique).

### 2.5 Review & correction UX
- A staging table view: each row with parsed values, validation flags, dedup verdict, and an editable category. Bulk actions (accept all new, skip all dups, apply a rule). Nothing enters the ledger until the user commits.

### 2.6 Rollback
- One action per batch; disabled if any row was later edited/split/transfer-linked (explain why); otherwise deletes the batch's transactions and marks batch `rolled_back`.

## 3. OFX/QFX import (R4)
- Same pipeline; parser reads OFX SGML/XML. **FITID → `external_id`** gives reliable dedup (better than CSV fingerprints). Account mapping via `<ACCTID>`. Balance elements become `balance_snapshots`. Fixtures per institution in CI.

## 4. PDF statement import (design-only, implement R5+, D12)
- **Extract:** free libraries (pdfplumber/camelot) produce candidate rows; layout varies per bank so extraction confidence is per-row.
- **Mandatory human review of every row** before commit — the LLM is **never** the authoritative source of an amount (upholds the "code calculates" principle, AGT-04). Optional LLM assist only to *suggest* column boundaries, always user-verified.
- Low-confidence rows blocked from commit until corrected. This is deliberately last because reliability is lowest and correctness bar is highest.

## 5. Aggregator integration (design R2 / implement R3, D13 — contingent on verified-free tier)
- **Provider-agnostic module.** Interface: `link()`, `list_accounts()`, `fetch_transactions(since_cursor)`, `verify_webhook(payload)`, `reauth()`, `revoke()`. Concrete adapters: **Teller** (free developer tier candidate, US-only) with **SimpleFIN** fallback. If neither is genuinely free at implementation time, the feature **slips** (zero-budget rule, D6) — CSV remains the guaranteed path.
- **Webhooks:** endpoint verifies provider signature (reject unsigned/invalid); enqueues an `aggregator_sync` job; never trusts webhook body as data without a follow-up authenticated fetch (SSRF/spoof defense).
- **Incremental sync:** worker fetches since `connection.cursor`, funnels rows through the **same staging pipeline** (auto-accept high-confidence new rows, surface conflicts), updates cursor atomically.
- **Reauthentication:** on provider `needs_reauth`, mark connection, alert user, pause sync; resume after reauth.
- **Connection health:** status field + last_synced_at surfaced in UI; stale/error connections alert.
- **Provider-token protection:** tokens stored `access_token_encrypted` (app-layer AEAD, key from env, never plaintext in DB, never returned to client); deleted immediately on disconnect/revoke (20.3); token access audited.

## 6. Pending → posted reconciliation
- CSV/OFX rows are posted-only. Aggregator feeds may include `pending`; a pending transaction is stored with `status='pending'` and later **matched** to its posted counterpart (same account, close amount/date, external id lineage) and updated in place rather than duplicated. Unmatched stale pendings expire per policy.

## 7. Correctness guarantees carried by ingestion
- Money parsed straight to `amount_minor` (never via float) — FIN-01.
- Currency always set (default household base) — FIN-02.
- Dates parsed in household tz; calendar-month attribution correct — FIN-03/04.
- Dedup + idempotency by construction — FIN-05.
- Provenance on every committed row (batch/record/connection) enables rollback and citations.
- Transfers/refunds detected **after** commit as candidate links the user confirms — FIN-06 (never silently netted).

## 8. Failure handling
- Partial parse failures never block the whole batch — bad rows are isolated.
- Commit is transactional; a failed commit leaves the batch `staged` (safe to retry).
- Worker jobs are idempotent and retried with backoff; dead-lettered jobs raise an ops alert.
- All import outcomes (staged/committed/rolled_back/failed, counts) are audited.
