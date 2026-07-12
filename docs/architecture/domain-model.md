# Domain Model

Status: Proposed. Conceptual model (entities, relationships, lifecycle). Physical types/constraints/indexes are in `data-model.md`. All monetary values are integer minor units + ISO-4217 currency. All domain entities are scoped to a **household** (tenant).

## Entity overview

```
User ──*── Membership ──1── Household ──1──* (everything below)
User ──1──* Session
Household ──1──* Institution ──1──* FinancialConnection ──1──* Account
Household ──1──* Account ──1──* Transaction
Account ──1──* BalanceSnapshot
ImportBatch ──1──* ImportedRecord ──(commit)──►Transaction
Transaction ──*──1 Merchant
Transaction ──*──1 Category
CategorizationRule ──(applies to)──► Transaction
Transfer ──1── (Transaction out, Transaction in)
RecurringSeries ──1──* Transaction
Household ──1──* Budget | Goal | Liability | Holding | Document | Alert | Forecast | Scenario
Household ──1──* AgentConversation ──1──* AgentAction
Household ──1──* ConsentRecord
Household ──1──* AuditEvent
```

## Entities

1. **User** — a login identity (email, password credential, status). May belong to one household during beta (schema allows many via Membership). Lifecycle: registered → active → (disabled/deleted).

2. **Session** — a server-side authenticated session for a user; opaque token, issued at login, revoked at logout/expiry. Carries no financial data; the source of truth for `Principal{user_id, household_id}`.

3. **Household** — the tenant. Every financial row hangs off exactly one household. Created automatically at signup with the registering user as owner. Timezone + base currency live here (drives month boundaries, D1/FIN-03).

4. **Membership** — links User↔Household with a role (owner/member/viewer). Beta creates one owner membership; roles exist for future household collaboration (postponed D14) without a migration.

5. **Institution** — a financial institution reference (name, type, logo/color, optional aggregator id). Scoped to household (a user's chosen labels), groups connections/accounts.

6. **FinancialConnection** — a link to an institution via a provider (CSV-manual, or aggregator such as Teller/SimpleFIN). Holds encrypted provider tokens, sync cursor, health status, consent linkage. For CSV-only accounts, a lightweight "manual" connection or none.

7. **Account** — a checking/savings/credit-card account (full transactions), or a balance-only asset/liability container. Fields: type, currency, display name, institution, current-balance cache, archived flag. Owns transactions and balance snapshots.

8. **BalanceSnapshot** — a dated statement/known balance for an account (an *anchor*). Used to reconstruct running balances and detect discrepancies. Also the representation for balance-only assets/liabilities (D10).

9. **Transaction** — the canonical, provider-independent transaction: account, posted+pending status, minor-unit amount, currency, booked/posted date, merchant, category, description, provenance (import_batch/connection), transfer/refund links, soft-delete, edit audit. The heart of the model.

10. **ImportBatch** — one import attempt (file or sync run): source, status (staged/committed/rolled_back), counts, mapping used, checksum. Enables rollback of exactly its rows.

11. **ImportedRecord** — a raw staged row from an import before it becomes a Transaction: original values, parse/validation results, dedup verdict (new/duplicate/near-dup), user decision. Provenance for every committed transaction points back here.

12. **Merchant** — a normalized merchant entity (raw name → canonical name), grouping transactions for merchant analysis and recurring detection. Household-scoped normalization.

13. **Category** — spending/income category (system defaults + user categories, 2-level hierarchy, typed as income/expense/transfer). First-class "uncategorized".

14. **CategorizationRule** — a deterministic, ordered rule (match on merchant/amount/account → set category) applied at import review; may be promoted from confirmed agent proposals.

15. **Transfer** — a confirmed pairing of two transactions (money leaving one own-account, entering another). Excluded from income/spending aggregates (fixes FIN-06 double counting). Status: candidate → confirmed/rejected.

16. **RecurringSeries** — a detected/confirmed recurring stream (merchant + cadence + expected amount), with member transactions, next-expected occurrence, and drift/missed detection. Feeds alerts and forecasting.

17. **Budget** — a per-category monthly spending target (minor units), calendar-month window in household tz, optional rollover. Unique per (household, category, period).

18. **Goal** — a savings goal (target amount+date, linked accounts); progress computed deterministically from balances.

19. **Liability** — a debt (credit card as account, or balance-only loan) with APR/minimum payment for payoff planning (R4). Feeds net worth as a negative.

20. **Holding** — a balance-only investment position during early releases (value snapshot); full positions/pricing postponed (D14). Feeds net worth as an asset.

21. **Document** — an uploaded artifact (CSV/OFX/PDF statement) retained for provenance/audit; linked to its ImportBatch. Storage strategy per ADR-08.

22. **Alert** — a fired notification (type, severity, fired-at, state read/dismissed, and **evidence references** to the rows/thresholds that justify it). In-app only (D11).

23. **Forecast** — a saved deterministic cash-flow projection over a horizon, with per-line-item provenance (which recurring series/statistic produced each projected amount).

24. **Scenario** — a named, re-runnable parameterized simulation layered on a forecast (e.g., drop subscription, rent change, extra debt payment), storing its parameters and computed deltas.

25. **AgentConversation** — a chat session between a user and the analyst: ordered messages, linked to household, retention policy, minimization metadata.

26. **AgentAction** — a single agent step: tool calls made (read-only), the citations produced, and any **proposal** emitted (typed mutation the user may confirm) with its lifecycle (proposed → confirmed/rejected → executed-via-authorized-API). The audit trail for AI behavior.

27. **ConsentRecord** — a record of user consent (aggregator connection, LLM data-processing acknowledgment, data-retention choices), with grant/revoke timestamps. Basis for connection disconnect and the AI opt-out (20.4).

28. **AuditEvent** — append-only record of security/financial-relevant actions: auth events, imports, mutations, agent proposals/confirmations, exports, deletions. Actor, action, target, request id, timestamp.

## Key lifecycle & invariants

- **Tenant invariant:** every entity 3–28 resolves to exactly one Household; access requires a Session whose Principal matches that Household.
- **Ingestion invariant:** a Transaction exists only via a committed ImportedRecord *or* an explicit authorized manual add; both carry provenance.
- **Money invariant:** amounts never stored as float; currency always present.
- **Mutation invariant:** every change to financial data is either a direct authorized user action or a confirmed AgentAction proposal — never a raw model write.
- **Deletion invariant:** account deletion hard-deletes all household-owned rows and documents and revokes connections/tokens; audit events are retained but actor-anonymized per policy.
