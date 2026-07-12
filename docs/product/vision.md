# Product Vision

Status: Approved for planning (interview completed 2026-07-11)
Decisions referenced: D1–D14 (see `docs/product/roadmap.md` § Decisions)

## Product statement

A personal financial intelligence web application for US individuals that consolidates a person's real transaction history into one **correct, evidence-backed ledger**, and layers on budgets, recurring-payment tracking, cash-flow visibility, net worth, alerts, and an AI analyst whose every numeric claim is computed by deterministic code and traceable to the underlying transactions.

## The user problem

People who want to understand their own money face three failures in existing tools:

1. **Fragmentation** — transactions live across several banks and credit cards; no single place holds a trustworthy consolidated history.
2. **Silent incorrectness** — tools that do consolidate routinely double-count transfers, miscategorize, mishandle refunds and pending charges, and present numbers the user cannot verify.
3. **Opaque "insights"** — AI-flavored features assert things about the user's money without showing the evidence, so the user cannot tell a real anomaly from a hallucination.

## Value proposition

- **One correct ledger.** Imported history is staged, validated, deduplicated, and reviewable before it becomes truth. Money is stored in integer minor units; every row carries provenance (which import, which file, which row).
- **Answers with receipts.** The AI analyst answers questions about *your* finances using deterministic, tenant-scoped tools; every number it states was computed by code and is cited back to specific transactions or aggregates you can click.
- **You stay in control.** The agent proposes changes (recategorize, adjust a budget); nothing mutates without your explicit confirmation. Your data is exportable and hard-deletable at any time.
- **Free to run.** The entire stack operates on genuinely free tiers (a project-wide non-negotiable), which also forces disciplined data minimization toward the LLM provider.

## Target users

- **Primary:** US individuals (the founder + an invited beta of <100 people) with 1–5 bank/credit accounts, who can export CSV statements and want consolidated, trustworthy visibility over 2–3 years of history (~10k transactions/user).
- **Not yet:** households with shared visibility, active investors wanting portfolio analytics, non-US users, mobile-app-first users. The schema is household-ready and currency-tagged so these are additive later.

## Differentiation

| Versus | Difference |
|---|---|
| Mint-style aggregators | Evidence-first: every displayed number reconstructs from visible rows; user reviews imports before commit; no ad-driven data use. |
| Spreadsheets | Same trust level, but with dedup, normalization, recurring detection, alerts, forecasting, and a conversational analyst. |
| "AI finance chat" products | The model never does the math and never acts alone: deterministic tools compute, citations prove, mutations require confirmation. |

## Product principles

1. **Correctness before features.** No feature ships on top of data the system cannot defend (release 0 exists solely for this).
2. **The model narrates; code calculates.** An LLM output is never the authoritative source of a financial number.
3. **Show the evidence.** Every alert, insight, and answer links to the rows that justify it.
4. **Nothing changes without consent.** Agent mutations are proposals; imports commit only after review; deletion is real.
5. **Tenant isolation is structural, not conventional.** Identity comes from the session, never from the client or the model.
6. **Zero-budget is a design constraint.** Every dependency must have a genuinely free tier; if it doesn't, we design around it.
7. **Name things truthfully.** No "net worth" labels on cash-flow numbers; no claimed capabilities (pgvector) that don't exist.

## Success metrics

- **Trust:** 100% of agent numeric claims carry resolvable citations; 0 confirmed cross-tenant data exposures; import dedup false-negative rate <1% on fixture corpus.
- **Utility:** a beta user can import 2 years of history from 2+ institutions and get correct monthly cash flow within 30 minutes; weekly active use by ≥half the beta.
- **Correctness:** all financial-calculation golden tests pass (sums, month boundaries, transfers, refunds); reconciled balances match user-entered statement balances within $0.01.
- **AI quality:** ≥95% pass rate on the deterministic-answer eval set; 100% pass on the prompt-injection suite (no unauthorized tool use, no unconfirmed mutation, no cross-tenant read).
- **Cost:** $0.00 total monthly spend, verified monthly.

## Non-goals

- Personalized investment, tax, or legal advice (explicit refusal policy; not a licensed advisor).
- Money movement of any kind (payments, transfers, bill pay) — the product is read/analyze/plan only.
- Becoming a data aggregation platform for third parties; no data sharing or resale, ever.
- Bank-grade compliance certification (SOC2 etc.) during the beta phase.
- ML-based forecasting; forecasts are deterministic and explainable (recurring-based projection + simple statistics).
