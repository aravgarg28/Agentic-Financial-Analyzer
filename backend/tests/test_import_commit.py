"""Import review + commit (T-074).

Commit is a single transaction: accepted, error-free records become Transactions
with full provenance. Atomic — a failure mid-commit leaves the batch 'staged'
with nothing written. Committed totals match accepted staging totals to the cent.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.modules.ledger.models import Transaction
from main import app
from tests.conftest import CSRF_HEADERS
from tests.helpers import make_household

MAPPING = {
    "date": {"column": "Date", "format": "%Y-%m-%d"},
    "amount": {"mode": "single", "column": "Amount", "sign": "natural"},
    "description_column": "Description",
}
THREE_ROWS = (
    b"Date,Description,Amount\n"
    b"2026-01-02,Coffee,-4.35\n"
    b"2026-01-03,Groceries,-53.20\n"
    b"2026-01-05,Payroll,2500.00\n"
)


@asynccontextmanager
async def _login(email: str, password: str = "a-strong-passphrase-1"):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=CSRF_HEADERS,
    ) as client:
        r = await client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        yield client


async def _account(c, name="Checking"):
    return (await c.post("/ledger/accounts", json={"name": name, "type": "checking"})).json()["id"]


async def _pipeline(c, csv=THREE_ROWS, account=None):
    """upload -> stage -> dedup, returning (batch_id, account_id)."""
    if account is None:
        account = await _account(c)
    batch = (await c.post("/imports/upload", files={"file": ("f.csv", csv, "text/csv")})).json()["id"]
    await c.post(f"/imports/{batch}/stage", json={"mapping": MAPPING})
    await c.post(f"/imports/{batch}/dedup", json={"account_id": account})
    return batch, account


async def test_full_commit_creates_transactions_with_provenance(seed_session):
    _, mem = await make_household(seed_session, "c1@example.com")
    await seed_session.commit()
    async with _login("c1@example.com") as c:
        batch, acct = await _pipeline(c)
        summary = (await c.post(f"/imports/{batch}/commit")).json()
        assert summary["committed"] == 3
        # Cent-exact total of accepted rows.
        assert summary["total_minor"] == -435 - 5320 + 250000

        # Transactions now visible in the ledger.
        txns = (await c.get("/ledger/transactions")).json()["data"]
        assert len(txns) == 3
        # Account balance recomputed.
        bal = (await c.get("/ledger/accounts")).json()["data"][0]["current_balance_minor"]
        assert bal == -435 - 5320 + 250000

    # Provenance: every committed row links back to the batch + a record.
    rows = (
        await seed_session.execute(
            select(Transaction).where(Transaction.household_id == mem.household_id)
        )
    ).scalars().all()
    assert all(t.import_batch_id is not None for t in rows)
    assert all(t.imported_record_id is not None for t in rows)
    assert all(t.source == "csv" for t in rows)


async def test_skipped_rows_are_not_committed(seed_session):
    await make_household(seed_session, "c2@example.com")
    await seed_session.commit()
    async with _login("c2@example.com") as c:
        batch, acct = await _pipeline(c)
        # Skip the first row.
        await c.patch(f"/imports/{batch}/records/1", json={"decision": "skip"})
        summary = (await c.post(f"/imports/{batch}/commit")).json()
        assert summary["committed"] == 2
        descriptions = {t["description"] for t in (await c.get("/ledger/transactions")).json()["data"]}
        assert "Coffee" not in descriptions


async def test_review_set_category_applies_on_commit(seed_session):
    await make_household(seed_session, "c3@example.com")
    await seed_session.commit()
    async with _login("c3@example.com") as c:
        cat_id = (await c.post("/ledger/categories", json={"name": "Food", "type": "expense"})).json()["id"]
        batch, acct = await _pipeline(c)
        await c.patch(f"/imports/{batch}/records/1", json={"category_id": cat_id})
        await c.post(f"/imports/{batch}/commit")
        # The Coffee row now carries the chosen category.
        by_cat = (await c.get("/ledger/transactions", params={"category_id": cat_id})).json()["data"]
        assert [t["description"] for t in by_cat] == ["Coffee"]


async def test_bulk_skip_then_commit(seed_session):
    await make_household(seed_session, "c4@example.com")
    await seed_session.commit()
    async with _login("c4@example.com") as c:
        batch, acct = await _pipeline(c)
        bulk = (await c.post(f"/imports/{batch}/records/bulk", json={"decision": "skip"})).json()
        assert bulk["updated"] == 3
        summary = (await c.post(f"/imports/{batch}/commit")).json()
        assert summary["committed"] == 0


async def test_accepting_error_row_is_rejected(seed_session):
    await make_household(seed_session, "c5@example.com")
    await seed_session.commit()
    bad = b"Date,Description,Amount\nnope,Broken,-1.00\n"
    async with _login("c5@example.com") as c:
        batch, acct = await _pipeline(c, csv=bad)
        r = await c.patch(f"/imports/{batch}/records/1", json={"decision": "accept"})
        assert r.status_code == 400


async def test_commit_is_atomic_on_failure(seed_session, monkeypatch):
    """A failure mid-commit must leave the batch 'staged' with no rows written."""
    import app.modules.ledger.accounts as accounts_mod

    async def _boom(*args, **kwargs):
        raise RuntimeError("injected failure")

    await make_household(seed_session, "c6@example.com")
    await seed_session.commit()
    async with _login("c6@example.com") as c:
        batch, acct = await _pipeline(c)
        monkeypatch.setattr(accounts_mod, "recompute_account_balance", _boom)
        resp = await c.post(f"/imports/{batch}/commit")
        assert resp.status_code >= 500  # the injected error propagates

        # Nothing was written; the batch can still be committed.
        records = await c.get(f"/imports/{batch}/records")
        assert records.json()["batch"]["status"] == "staged"
        assert (await c.get("/ledger/transactions")).json()["data"] == []


async def test_recommit_is_rejected(seed_session):
    await make_household(seed_session, "c7@example.com")
    await seed_session.commit()
    async with _login("c7@example.com") as c:
        batch, acct = await _pipeline(c)
        assert (await c.post(f"/imports/{batch}/commit")).status_code == 200
        # Second commit refused.
        assert (await c.post(f"/imports/{batch}/commit")).status_code == 400


async def test_large_batch_commits_via_chunking(seed_session):
    """Cross the COMMIT_CHUNK (500) boundary to exercise chunked flushing."""
    await make_household(seed_session, "c8@example.com")
    await seed_session.commit()
    lines = [b"Date,Description,Amount"]
    for i in range(600):
        day = 1 + (i % 27)
        lines.append(f"2026-01-{day:02d},Store {i},-{(i % 100) + 1}.00".encode())
    big_csv = b"\n".join(lines) + b"\n"
    async with _login("c8@example.com") as c:
        batch, acct = await _pipeline(c, csv=big_csv)
        summary = (await c.post(f"/imports/{batch}/commit")).json()
        assert summary["committed"] == 600

    count = await seed_session.scalar(select(func.count()).select_from(Transaction))
    assert count == 600
