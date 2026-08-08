"""Accounts & institutions CRUD (T-060).

Exercises the account lifecycle (create → list → update → archive → unarchive),
institution create/list/attach, validation, and cross-tenant isolation through
the HTTP surface.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from main import app
from tests.conftest import CSRF_HEADERS
from tests.helpers import make_household


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


async def test_account_lifecycle(seed_session):
    """create → visible in default list → rename → archive (hidden) →
    include_archived shows it → unarchive → visible again."""
    await make_household(seed_session, "life@example.com")
    await seed_session.commit()

    async with _login("life@example.com") as c:
        # Create.
        created = await c.post(
            "/ledger/accounts",
            json={"name": "Everyday Checking", "type": "checking"},
        )
        assert created.status_code == 201
        acct = created.json()
        assert acct["name"] == "Everyday Checking"
        assert acct["tracking_mode"] == "transactions"
        assert acct["currency"] == "USD"  # defaulted from household base
        assert acct["archived"] is False
        pid = acct["id"]

        # Appears in the default list.
        listing = (await c.get("/ledger/accounts")).json()["data"]
        assert [a["id"] for a in listing] == [pid]

        # Rename.
        renamed = await c.patch(
            f"/ledger/accounts/{pid}", json={"name": "Primary Checking"}
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Primary Checking"

        # Archive → hidden from the default list, still present with the flag.
        archived = await c.post(f"/ledger/accounts/{pid}/archive")
        assert archived.status_code == 200
        assert archived.json()["archived"] is True
        assert (await c.get("/ledger/accounts")).json()["data"] == []
        with_archived = (
            await c.get("/ledger/accounts", params={"include_archived": True})
        ).json()["data"]
        assert [a["id"] for a in with_archived] == [pid]

        # Unarchive → back in the default list.
        unarchived = await c.post(f"/ledger/accounts/{pid}/unarchive")
        assert unarchived.status_code == 200
        assert unarchived.json()["archived"] is False
        assert len((await c.get("/ledger/accounts")).json()["data"]) == 1


async def test_create_account_validates_type_and_tracking_mode(seed_session):
    await make_household(seed_session, "val@example.com")
    await seed_session.commit()
    async with _login("val@example.com") as c:
        bad_type = await c.post(
            "/ledger/accounts", json={"name": "X", "type": "crypto_wallet"}
        )
        assert bad_type.status_code == 400
        bad_mode = await c.post(
            "/ledger/accounts",
            json={"name": "X", "type": "checking", "tracking_mode": "guesswork"},
        )
        assert bad_mode.status_code == 400


async def test_balance_only_account_holds_user_balance(seed_session):
    """balance-only accounts (D10: property/investment) carry a user-set balance;
    transactions-mode accounts reject a direct balance write."""
    await make_household(seed_session, "bal@example.com")
    await seed_session.commit()
    async with _login("bal@example.com") as c:
        created = await c.post(
            "/ledger/accounts",
            json={
                "name": "Brokerage",
                "type": "investment",
                "tracking_mode": "balance_only",
                "opening_balance_minor": 1_000_000,
            },
        )
        assert created.status_code == 201
        pid = created.json()["id"]
        assert created.json()["current_balance_minor"] == 1_000_000

        updated = await c.patch(
            f"/ledger/accounts/{pid}", json={"current_balance_minor": 1_250_000}
        )
        assert updated.status_code == 200
        assert updated.json()["current_balance_minor"] == 1_250_000

        # A transactions-mode account cannot have its balance set directly.
        tx_acct = (
            await c.post("/ledger/accounts", json={"name": "Chk", "type": "checking"})
        ).json()["id"]
        reject = await c.patch(
            f"/ledger/accounts/{tx_acct}", json={"current_balance_minor": 42}
        )
        assert reject.status_code == 400


async def test_institution_create_list_and_attach(seed_session):
    await make_household(seed_session, "inst@example.com")
    await seed_session.commit()
    async with _login("inst@example.com") as c:
        inst = await c.post("/ledger/institutions", json={"name": "Acme Bank"})
        assert inst.status_code == 201
        inst_id = inst.json()["id"]

        # Duplicate name rejected.
        dup = await c.post("/ledger/institutions", json={"name": "Acme Bank"})
        assert dup.status_code == 400

        listing = (await c.get("/ledger/institutions")).json()["data"]
        assert [i["name"] for i in listing] == ["Acme Bank"]

        # Attach on create.
        acct = await c.post(
            "/ledger/accounts",
            json={"name": "Acme Checking", "type": "checking", "institution_id": inst_id},
        )
        assert acct.status_code == 201
        assert acct.json()["institution"] == {"id": inst_id, "name": "Acme Bank"}

        # Detach.
        pid = acct.json()["id"]
        detached = await c.patch(
            f"/ledger/accounts/{pid}", json={"clear_institution": True}
        )
        assert detached.json()["institution"] is None


async def test_cross_tenant_account_is_invisible_and_unwritable(seed_session):
    """SEC-01: B's account id is unusable from A's session (404-ish 400)."""
    await make_household(seed_session, "own@example.com")
    _, mem_b = await make_household(seed_session, "other@example.com")
    await seed_session.commit()

    # B creates an account.
    async with _login("other@example.com") as b:
        b_pid = (
            await b.post("/ledger/accounts", json={"name": "B Secret", "type": "savings"})
        ).json()["id"]

    async with _login("own@example.com") as a:
        # A cannot see it.
        assert (await a.get("/ledger/accounts")).json()["data"] == []
        # A cannot rename or archive it.
        assert (await a.patch(f"/ledger/accounts/{b_pid}", json={"name": "hijack"})).status_code == 400
        assert (await a.post(f"/ledger/accounts/{b_pid}/archive")).status_code == 400
