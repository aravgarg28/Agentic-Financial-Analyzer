# Data Model (Physical)

Status: Proposed. Target: PostgreSQL (Neon/Supabase free tier). Managed via Alembic migrations (INF-01). Money = `BIGINT` **minor units** + `currency CHAR(3)` (ISO 4217); **no float for authoritative amounts** (FIN-01/02). Conversion to major units happens only at the API serialization boundary.

## Conventions

- **PK:** `id BIGINT GENERATED ALWAYS AS IDENTITY` unless noted; external-facing ids use a separate `public_id UUID` (default `gen_random_uuid()`) so integer PKs never leak/enumerate.
- **Tenant:** every financial table has `household_id BIGINT NOT NULL REFERENCES households(id) ON DELETE CASCADE`, indexed, and included in composite indexes. Application always filters by the session-derived `household_id`.
- **Timestamps:** `created_at timestamptz NOT NULL DEFAULT now()`, `updated_at timestamptz` (trigger or app-maintained). Business dates that must be timezone-aware use `timestamptz`; pure calendar dates use `date`.
- **Soft delete:** `deleted_at timestamptz NULL` on user-editable financial records (transactions, accounts, categories, budgets); partial indexes exclude soft-deleted rows. Hard delete reserved for account-deletion cascade and staging cleanup.
- **Provenance:** transactions carry `source`, `import_batch_id`, `connection_id`, `imported_record_id`.
- **Money helper:** columns named `*_minor` (e.g., `amount_minor BIGINT`). Signed: income positive, expense negative — but income/expense semantics come from the **category type**, not the sign (FIN-06).

---

## households
- **Purpose:** tenant root. **Fields:** `id`, `public_id`, `name`, `base_currency CHAR(3) NOT NULL DEFAULT 'USD'`, `timezone TEXT NOT NULL DEFAULT 'America/New_York'`, `created_at`, `deleted_at`. **Retention:** deleted on account deletion (cascade root). **Tenant:** is the tenant.

## users
- **Purpose:** login identity. **Fields:** `id`, `public_id`, `email CITEXT UNIQUE NOT NULL`, `password_hash TEXT NOT NULL` (argon2id encoded), `password_algo TEXT`, `status TEXT` (active/disabled), `failed_login_count INT DEFAULT 0`, `locked_until timestamptz`, `created_at`, `deleted_at`. **Unique:** `email`. **Indexes:** `email`. **Retention:** hard-deleted (with membership) on account deletion. **Isolation:** users reach data only via membership→household.

## memberships
- **Purpose:** user↔household with role. **Fields:** `id`, `user_id FK users`, `household_id FK households`, `role TEXT CHECK (role IN ('owner','member','viewer'))`, `created_at`. **Unique:** `(user_id, household_id)`. **Indexes:** `household_id`, `user_id`. Beta: exactly one `owner` row per household.

## sessions
- **Purpose:** server-side session. **Fields:** `id`, `token_hash TEXT UNIQUE NOT NULL` (store a hash of the opaque token, never the token), `user_id FK`, `household_id FK` (denormalized for fast Principal), `created_at`, `last_seen_at timestamptz`, `idle_expires_at timestamptz`, `absolute_expires_at timestamptz`, `revoked_at timestamptz`, `ip_hash TEXT`, `user_agent TEXT`. **Unique:** `token_hash`. **Indexes:** `token_hash`, `user_id`, partial `WHERE revoked_at IS NULL`. **Retention:** purge expired/revoked after 30d (worker). **Isolation:** the authority for it.

## institutions
- **Purpose:** user-labeled institution. **Fields:** `id`, `household_id FK`, `public_id`, `name TEXT`, `kind TEXT`, `logo_ref TEXT`, `aggregator_institution_id TEXT NULL`, `created_at`, `deleted_at`. **Indexes:** `household_id`.

## financial_connections
- **Purpose:** provider link (manual/CSV or aggregator). **Fields:** `id`, `household_id FK`, `institution_id FK`, `public_id`, `provider TEXT` (manual/teller/simplefin), `access_token_encrypted BYTEA NULL` (app-layer encrypted; key from env, never in DB plaintext), `token_nonce BYTEA`, `cursor TEXT NULL`, `status TEXT` (active/needs_reauth/revoked/error), `consent_id FK consent_records NULL`, `last_synced_at timestamptz`, `created_at`, `deleted_at`. **Indexes:** `household_id`, `institution_id`, partial `status='active'`. **Retention:** tokens deleted immediately on disconnect/revoke (20.3). **Isolation:** household-scoped; tokens never returned to client.

## accounts
- **Purpose:** account or balance-only container. **Fields:** `id`, `household_id FK`, `institution_id FK NULL`, `connection_id FK NULL`, `public_id`, `name TEXT`, `type TEXT CHECK (type IN ('checking','savings','credit_card','loan','investment','property','cash','other'))`, `tracking_mode TEXT CHECK (tracking_mode IN ('transactions','balance_only'))`, `currency CHAR(3) NOT NULL`, `current_balance_minor BIGINT NULL` (cache), `archived_at timestamptz`, `created_at`, `deleted_at`. **Indexes:** `household_id`, `(household_id, type)`. **Retention:** soft delete/archive; hard delete on account deletion cascade. **Isolation:** household-scoped.

## transactions  *(central table)*
- **Purpose:** canonical transaction. **Fields:**
  - `id`, `household_id FK`, `account_id FK accounts`, `public_id`
  - `amount_minor BIGINT NOT NULL`, `currency CHAR(3) NOT NULL`
  - `booked_date date NOT NULL`, `posted_at timestamptz NULL`, `status TEXT CHECK (status IN ('pending','posted')) DEFAULT 'posted'`
  - `merchant_id FK merchants NULL`, `raw_description TEXT`, `normalized_description TEXT`
  - `category_id FK categories NULL` (NULL = uncategorized, first-class)
  - `transfer_id FK transfers NULL`, `refund_of_transaction_id FK transactions NULL`, `recurring_series_id FK recurring_series NULL`
  - `source TEXT CHECK (source IN ('csv','ofx','pdf','aggregator','manual'))`, `import_batch_id FK NULL`, `imported_record_id FK NULL`, `connection_id FK NULL`
  - `dedup_fingerprint TEXT NOT NULL`, `external_id TEXT NULL` (e.g., OFX FITID / aggregator id)
  - `created_at`, `updated_at`, `deleted_at`
- **Unique / dedup (FIN-05):** partial unique `(household_id, account_id, external_id) WHERE external_id IS NOT NULL`; and application-level dedup on `(household_id, account_id, dedup_fingerprint)` where fingerprint = hash(account, booked_date, amount_minor, normalized_description) — enforced at import review with near-dup surfacing (a soft unique, because legitimate identical repeats exist, e.g. two $3 coffees same day → user confirms).
- **Indexes:** `(household_id, account_id, booked_date DESC)`, `(household_id, category_id, booked_date)`, `(household_id, merchant_id)`, `dedup_fingerprint`, partial `WHERE deleted_at IS NULL`. Sized for ~10k rows/household (D9) — trivial for Postgres.
- **Retention:** soft delete on user edit/remove; hard delete on account/household deletion. **Provenance:** full (source + batch/record/connection). **Isolation:** household-scoped on every query.

## merchants
- **Purpose:** normalized merchant. **Fields:** `id`, `household_id FK`, `canonical_name TEXT`, `raw_pattern TEXT`, `created_at`. **Unique:** `(household_id, canonical_name)`. **Indexes:** `household_id`.

## categories
- **Purpose:** taxonomy. **Fields:** `id`, `household_id FK NULL` (NULL = system default, visible to all; user rows household-scoped), `parent_id FK categories NULL`, `name TEXT`, `type TEXT CHECK (type IN ('income','expense','transfer'))`, `is_system BOOL`, `created_at`, `deleted_at`. **Unique:** `(household_id, parent_id, name)`. **Indexes:** `household_id`.

## categorization_rules
- **Purpose:** deterministic auto-categorization. **Fields:** `id`, `household_id FK`, `priority INT`, `match_merchant TEXT NULL`, `match_amount_min_minor BIGINT NULL`, `match_amount_max_minor BIGINT NULL`, `match_account_id FK NULL`, `set_category_id FK categories`, `enabled BOOL DEFAULT true`, `created_at`. **Indexes:** `(household_id, priority)`. Applied in priority order at import review; deterministic.

## transfers
- **Purpose:** confirmed transfer pairing. **Fields:** `id`, `household_id FK`, `out_transaction_id FK transactions`, `in_transaction_id FK transactions`, `status TEXT CHECK (status IN ('candidate','confirmed','rejected'))`, `created_at`, `confirmed_at`. **Unique:** `(out_transaction_id, in_transaction_id)`. **Indexes:** `household_id`. Confirmed transfers excluded from cash-flow aggregates.

## balance_snapshots
- **Purpose:** dated anchor / balance-only value. **Fields:** `id`, `household_id FK`, `account_id FK`, `as_of date NOT NULL`, `balance_minor BIGINT NOT NULL`, `currency CHAR(3)`, `source TEXT` (statement/manual/aggregator), `created_at`. **Unique:** `(account_id, as_of, source)`. **Indexes:** `(household_id, account_id, as_of DESC)`. Drives balance reconstruction + discrepancy alerts.

## import_batches
- **Purpose:** one import run. **Fields:** `id`, `household_id FK`, `account_id FK NULL`, `public_id`, `source TEXT`, `filename TEXT NULL`, `file_document_id FK documents NULL`, `file_checksum TEXT`, `column_mapping_id FK NULL`, `status TEXT CHECK (status IN ('staged','committing','committed','rolled_back','failed'))`, `row_count INT`, `new_count INT`, `dup_count INT`, `created_at`, `committed_at`. **Indexes:** `household_id`, `status`. **Rollback:** deletes exactly the transactions with this `import_batch_id`.

## imported_records
- **Purpose:** staged raw row pre-commit. **Fields:** `id`, `household_id FK`, `import_batch_id FK`, `row_number INT`, `raw JSONB`, `parsed_amount_minor BIGINT NULL`, `parsed_date date NULL`, `parsed_currency CHAR(3) NULL`, `validation JSONB` (errors/warnings), `dedup_verdict TEXT CHECK (dedup_verdict IN ('new','duplicate','near_dup'))`, `user_decision TEXT CHECK (user_decision IN ('pending','accept','skip','merge'))`, `committed_transaction_id FK NULL`, `created_at`. **Indexes:** `(import_batch_id, row_number)`. **Retention:** kept for provenance; purge policy after batch age (configurable, default retain).

## column_mappings
- **Purpose:** saved per-institution CSV mapping. **Fields:** `id`, `household_id FK`, `institution_id FK NULL`, `name TEXT`, `mapping JSONB` (source-col → canonical field, sign convention, date format), `created_at`. **Unique:** `(household_id, name)`.

## budgets
- **Purpose:** monthly category budget. **Fields:** `id`, `household_id FK`, `category_id FK`, `period_month date` (first-of-month in household tz), `amount_minor BIGINT`, `rollover BOOL DEFAULT false`, `created_at`, `updated_at`, `deleted_at`. **Unique:** `(household_id, category_id, period_month)` — fixes silent-noop/duplicate budget (FIN-08). **Indexes:** `(household_id, period_month)`.

## recurring_series
- **Purpose:** detected recurring stream. **Fields:** `id`, `household_id FK`, `merchant_id FK NULL`, `label TEXT`, `cadence TEXT` (monthly/weekly/…), `expected_amount_minor BIGINT`, `amount_tolerance_minor BIGINT`, `next_expected_date date`, `status TEXT CHECK (status IN ('candidate','confirmed','ended'))`, `created_at`. **Indexes:** `household_id`. Member transactions link via `transactions.recurring_series_id`.

## goals
- **Fields:** `id`, `household_id FK`, `name`, `target_amount_minor BIGINT`, `target_date date`, `linked_account_ids BIGINT[]` (or a join table `goal_accounts`), `created_at`, `deleted_at`. **Indexes:** `household_id`. Progress computed from balances (deterministic).

## liabilities
- **Fields:** `id`, `household_id FK`, `account_id FK NULL`, `name`, `principal_minor BIGINT`, `apr_bps INT` (basis points, integer), `min_payment_minor BIGINT`, `currency CHAR(3)`, `created_at`, `deleted_at`. Feeds net worth (negative) and R4 payoff planning.

## holdings
- **Purpose:** balance-only investment (D10/D14). **Fields:** `id`, `household_id FK`, `account_id FK`, `label`, `value_minor BIGINT`, `as_of date`, `created_at`. Full positions/pricing postponed.

## documents
- **Purpose:** uploaded statement/artifact. **Fields:** `id`, `household_id FK`, `public_id`, `kind TEXT` (csv/ofx/pdf), `filename`, `content_type`, `byte_size BIGINT`, `storage_ref TEXT` (see ADR-08 — DB `bytea` for small files on free tier, or free object storage), `checksum TEXT`, `created_at`, `deleted_at`. **Retention:** deleted with its batch/household. **Security:** type/size validated on upload; never executed/served inline.

## alerts
- **Purpose:** in-app alert (D11). **Fields:** `id`, `household_id FK`, `type TEXT`, `severity TEXT`, `title`, `body`, `evidence JSONB` (references: transaction ids, thresholds, series id), `state TEXT CHECK (state IN ('unread','read','dismissed'))`, `fired_at timestamptz`, `created_at`. **Indexes:** `(household_id, state, fired_at DESC)`. Every alert must carry resolvable evidence.

## forecasts
- **Fields:** `id`, `household_id FK`, `horizon_months INT`, `generated_at timestamptz`, `line_items JSONB` (each: month, amount_minor, source_type, source_ref, explanation), `assumptions JSONB`, `created_at`. Deterministic; every line traceable.

## scenarios
- **Fields:** `id`, `household_id FK`, `name`, `base_forecast_id FK NULL`, `parameters JSONB`, `computed_deltas JSONB`, `created_at`, `updated_at`. Re-runnable.

## agent_conversations
- **Fields:** `id`, `household_id FK`, `user_id FK`, `public_id`, `title`, `created_at`, `last_message_at`, `deleted_at`. Chat window cached in Redis (`chat:{household_id}:{conversation_id}`, tenant from session — fixes AGT-05). **Retention:** user-deletable; purged on account deletion.

## agent_actions
- **Purpose:** AI audit trail + proposals. **Fields:** `id`, `household_id FK`, `conversation_id FK`, `step_index INT`, `tools_called JSONB` (name + args as executed server-side), `citations JSONB` (row/aggregate refs), `proposal JSONB NULL` (typed mutation), `proposal_status TEXT CHECK (proposal_status IN ('none','proposed','confirmed','rejected','executed'))`, `executed_via TEXT NULL` (which authorized endpoint), `created_at`. **Indexes:** `(household_id, conversation_id, step_index)`.

## consent_records
- **Fields:** `id`, `household_id FK`, `user_id FK`, `type TEXT` (aggregator/llm_processing/retention), `scope JSONB`, `granted_at timestamptz`, `revoked_at timestamptz NULL`, `created_at`. Basis for disconnect (20.3) and AI opt-out (20.4).

## audit_events  *(append-only)*
- **Fields:** `id`, `household_id FK NULL`, `actor_user_id FK NULL`, `action TEXT`, `target_type TEXT`, `target_public_id TEXT`, `request_id TEXT`, `metadata JSONB` (no secrets/PII), `created_at`. **Indexes:** `(household_id, created_at DESC)`, `action`. **Retention:** retained through account deletion but actor-anonymized per deletion policy; never updated or deleted individually (append-only).

## jobs  *(ops / worker queue)*
- **Fields:** `id`, `type TEXT`, `payload JSONB`, `status TEXT CHECK (status IN ('queued','running','done','failed'))`, `attempts INT DEFAULT 0`, `run_after timestamptz`, `locked_by TEXT`, `locked_at timestamptz`, `last_error TEXT`, `created_at`, `updated_at`. **Indexes:** partial `(status, run_after) WHERE status='queued'`. Consumed via `FOR UPDATE SKIP LOCKED`. Not tenant data but payloads reference household ids.

---

## Integrity & isolation summary

- **Every** financial FK cascades from `households` so account deletion is a clean hard delete.
- **Every** read path filters by `household_id` from the Session Principal; there is no code path that accepts a client- or model-supplied tenant (SEC-01/AGT-01/AGT-05).
- **Money** is minor-units + currency everywhere; the only float in the system is transient display formatting at the API edge.
- **Uniqueness** prevents the current silent-noop and duplicate defects (budgets, transfers, external ids).
- **Provenance** on every transaction supports import rollback and evidence citations.
