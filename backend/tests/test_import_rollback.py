"""Import batch rollback (T-075).

Rollback deletes exactly the batch's transactions, returning the ledger to a
byte-identical state, and is refused if any imported row was edited since.
"""
from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from main import app
from tests.conftest import CSRF_HEADERS
from tests.helpers import make_household

MAPPING = {
    "date": {"column": "Date", "format": "%Y-%m-%d"},
    "amount": {"mode": "single", "column": "Amount", "sign": "natural"},
    "description_column": "Description",
}
CSV = b"Date,Description,Amount\n2026-02-01,Store A,-10.00\n2026-02-02,Store B,-20.00\n"


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


async def _account(c):
    return (await c.post("/ledger/accounts", json={"name": "Chk", "type": "checking"})).json()["id"]


async def _ledger_state(c):
    rows = (await c.get("/ledger/transactions", params={"limit": 200})).json()["data"]
    key = sorted((r["amount_minor"], r["booked_date"], r["description"]) for r in rows)
    digest = hashlib.sha256(repr(key).encode()).hexdigest()
    bal = (await c.get("/ledger/accounts")).json()["data"][0]["current_balance_minor"]
    return digest, len(rows), bal


async def _import_and_commit(c, account):
    batch = (await c.post("/imports/upload", files={"file": ("f.csv", CSV, "text/csv")})).json()["id"]
    await c.post(f"/imports/{batch}/stage", json={"mapping": MAPPING})
    await c.post(f"/imports/{batch}/dedup", json={"account_id": account})
    await c.post(f"/imports/{batch}/commit")
    return batch


async def test_rollback_returns_ledger_to_identical_state(seed_session):
    await make_household(seed_session, "rb1@example.com")
    await seed_session.commit()
    async with _login("rb1@example.com") as c:
        acct = await _account(c)
        # A pre-existing manual transaction so the ledger isn't empty.
        await c.post("/ledger/transactions", json={"account_id": acct, "amount_minor": -500, "booked_date": "2026-01-15", "description": "Manual"})
        before = await _ledger_state(c)

        batch = await _import_and_commit(c, acct)
        assert (await _ledger_state(c))[1] == before[1] + 2  # two rows added

        rolled = await c.post(f"/imports/{batch}/rollback")
        assert rolled.status_code == 200
        assert rolled.json()["deleted"] == 2

        after = await _ledger_state(c)
        assert after == before  # byte-identical digest, count, and balance


async def test_rollback_refused_if_row_edited(seed_session):
    await make_household(seed_session, "rb2@example.com")
    await seed_session.commit()
    async with _login("rb2@example.com") as c:
        acct = await _account(c)
        batch = await _import_and_commit(c, acct)
        # Edit one imported transaction.
        tx = (await c.get("/ledger/transactions")).json()["data"][0]
        await c.patch(f"/ledger/transactions/{tx['id']}", json={"amount_minor": -1})

        r = await c.post(f"/imports/{batch}/rollback")
        assert r.status_code == 400
        # Ledger untouched — both imported rows still present.
        assert len((await c.get("/ledger/transactions")).json()["data"]) == 2


async def test_rollback_only_committed_batches(seed_session):
    await make_household(seed_session, "rb3@example.com")
    await seed_session.commit()
    async with _login("rb3@example.com") as c:
        await _account(c)
        batch = (await c.post("/imports/upload", files={"file": ("f.csv", CSV, "text/csv")})).json()["id"]
        await c.post(f"/imports/{batch}/stage", json={"mapping": MAPPING})
        # Staged (not committed) -> rollback refused.
        assert (await c.post(f"/imports/{batch}/rollback")).status_code == 400


async def test_reupload_allowed_after_rollback(seed_session):
    await make_household(seed_session, "rb4@example.com")
    await seed_session.commit()
    async with _login("rb4@example.com") as c:
        acct = await _account(c)
        batch = await _import_and_commit(c, acct)
        await c.post(f"/imports/{batch}/rollback")
        # The same file can be uploaded again (rolled_back frees the checksum).
        again = await c.post("/imports/upload", files={"file": ("f.csv", CSV, "text/csv")})
        assert again.status_code == 201
        assert again.json()["created"] is True


async def test_rollback_is_tenant_scoped(seed_session):
    await make_household(seed_session, "rba@example.com")
    await make_household(seed_session, "rbb@example.com")
    await seed_session.commit()
    async with _login("rbb@example.com") as b:
        b_acct = await _account(b)
        b_batch = await _import_and_commit(b, b_acct)
    async with _login("rba@example.com") as a:
        assert (await a.post(f"/imports/{b_batch}/rollback")).status_code == 400
