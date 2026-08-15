"""Canonical ledger endpoints (T-061): list/filter/paginate, edit, soft-delete,
merchant auto-create, balance recompute, and fingerprint properties.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.modules.identity.models import AuditEvent
from app.modules.ledger.models import Merchant
from app.modules.ledger.service import compute_fingerprint, normalize_description
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


async def _make_account(client, name="Checking", type="checking") -> str:
    r = await client.post("/ledger/accounts", json={"name": name, "type": type})
    assert r.status_code == 201
    return r.json()["id"]


async def _add_tx(client, account_id, amount_minor, booked_date, description="Store"):
    r = await client.post(
        "/ledger/transactions",
        json={
            "account_id": account_id,
            "amount_minor": amount_minor,
            "booked_date": booked_date.isoformat(),
            "description": description,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --------------------------------------------------------------------------- #
# Pure-function properties (no DB)
# --------------------------------------------------------------------------- #
def test_fingerprint_is_whitespace_and_case_invariant():
    a = compute_fingerprint(
        account_id=1, booked_date=date(2026, 1, 2), amount_minor=-500,
        normalized_desc=normalize_description("  Blue   Bottle  COFFEE "),
    )
    b = compute_fingerprint(
        account_id=1, booked_date=date(2026, 1, 2), amount_minor=-500,
        normalized_desc=normalize_description("blue bottle coffee"),
    )
    assert a == b
    # A different amount changes the fingerprint.
    c = compute_fingerprint(
        account_id=1, booked_date=date(2026, 1, 2), amount_minor=-501,
        normalized_desc=normalize_description("blue bottle coffee"),
    )
    assert a != c


# --------------------------------------------------------------------------- #
# API behaviour
# --------------------------------------------------------------------------- #
async def test_minor_unit_round_trip_and_listing(seed_session):
    await make_household(seed_session, "list@example.com")
    await seed_session.commit()
    async with _login("list@example.com") as c:
        acct = await _make_account(c)
        await _add_tx(c, acct, -12345, date.today(), "Widget")
        data = (await c.get("/ledger/transactions")).json()["data"]
        assert len(data) == 1
        assert data[0]["amount_minor"] == -12345
        assert isinstance(data[0]["amount_minor"], int)
        assert data[0]["description"] == "Widget"


async def test_edit_updates_fields_recomputes_balance_and_audits(seed_session):
    _, mem = await make_household(seed_session, "edit@example.com")
    await seed_session.commit()
    async with _login("edit@example.com") as c:
        acct = await _make_account(c)
        cat_id = (await c.post("/ledger/categories", json={"name": "Food", "type": "expense"})).json()["id"]
        tx_id = await _add_tx(c, acct, -1000, date.today(), "Corner Store")

        # Balance reflects the transaction.
        accounts = (await c.get("/ledger/accounts")).json()["data"]
        assert accounts[0]["current_balance_minor"] == -1000

        # Edit amount + category + description.
        edited = await c.patch(
            f"/ledger/transactions/{tx_id}",
            json={"amount_minor": -2500, "category_id": cat_id, "description": "Corner Store #2"},
        )
        assert edited.status_code == 200
        assert edited.json()["amount_minor"] == -2500
        assert edited.json()["category_id"] == cat_id
        assert edited.json()["description"] == "Corner Store #2"

        # Balance recomputed.
        accounts = (await c.get("/ledger/accounts")).json()["data"]
        assert accounts[0]["current_balance_minor"] == -2500

    # An audit event was written for the edit.
    count = await seed_session.scalar(
        select(func.count()).select_from(AuditEvent).where(
            AuditEvent.household_id == mem.household_id,
            AuditEvent.action == "transaction.edit",
        )
    )
    assert count == 1


async def test_soft_delete_hides_and_restores_balance(seed_session):
    await make_household(seed_session, "del@example.com")
    await seed_session.commit()
    async with _login("del@example.com") as c:
        acct = await _make_account(c)
        await _add_tx(c, acct, -500, date.today(), "Keep")
        drop_id = await _add_tx(c, acct, -700, date.today(), "Drop")
        assert (await c.get("/ledger/accounts")).json()["data"][0]["current_balance_minor"] == -1200

        assert (await c.delete(f"/ledger/transactions/{drop_id}")).status_code == 200

        data = (await c.get("/ledger/transactions")).json()["data"]
        assert [t["description"] for t in data] == ["Keep"]
        assert (await c.get("/ledger/accounts")).json()["data"][0]["current_balance_minor"] == -500


async def test_merchant_is_auto_created_and_shared(seed_session):
    _, mem = await make_household(seed_session, "merch@example.com")
    await seed_session.commit()
    async with _login("merch@example.com") as c:
        acct = await _make_account(c)
        # Two transactions with the same (differently-cased) payee.
        await _add_tx(c, acct, -100, date.today(), "Blue Bottle")
        await _add_tx(c, acct, -200, date.today() - timedelta(days=1), "BLUE   BOTTLE")

    merchants = (
        await seed_session.execute(
            select(Merchant).where(Merchant.household_id == mem.household_id)
        )
    ).scalars().all()
    # One normalized merchant shared by both transactions.
    assert [m.canonical_name for m in merchants] == ["blue bottle"]


async def test_list_filters(seed_session):
    await make_household(seed_session, "filt@example.com")
    await seed_session.commit()
    async with _login("filt@example.com") as c:
        acct = await _make_account(c)
        cat_id = (await c.post("/ledger/categories", json={"name": "Bills", "type": "expense"})).json()["id"]
        await _add_tx(c, acct, -100, date(2026, 1, 5), "January small")
        await _add_tx(c, acct, -9000, date(2026, 3, 5), "March big")
        # Categorize the March one.
        march = [t for t in (await c.get("/ledger/transactions")).json()["data"] if t["description"] == "March big"][0]
        await c.post(f"/ledger/transactions/{march['id']}/recategorize", json={"category_id": cat_id})

        # Date filter.
        jan = (await c.get("/ledger/transactions", params={"start_date": "2026-01-01", "end_date": "2026-01-31"})).json()["data"]
        assert [t["description"] for t in jan] == ["January small"]
        # Amount filter.
        big = (await c.get("/ledger/transactions", params={"max_amount_minor": -1000})).json()["data"]
        assert [t["description"] for t in big] == ["March big"]
        # Search.
        found = (await c.get("/ledger/transactions", params={"search": "january"})).json()["data"]
        assert [t["description"] for t in found] == ["January small"]
        # Category + uncategorized.
        by_cat = (await c.get("/ledger/transactions", params={"category_id": cat_id})).json()["data"]
        assert [t["description"] for t in by_cat] == ["March big"]
        uncat = (await c.get("/ledger/transactions", params={"uncategorized": True})).json()["data"]
        assert [t["description"] for t in uncat] == ["January small"]


async def test_cursor_pagination_is_stable_under_inserts(seed_session):
    await make_household(seed_session, "page@example.com")
    await seed_session.commit()
    async with _login("page@example.com") as c:
        acct = await _make_account(c)
        # 4 transactions on distinct, increasing dates: d1..d4 (d4 newest).
        base = date(2026, 2, 1)
        for i in range(4):
            await _add_tx(c, acct, -(i + 1) * 100, base + timedelta(days=i), f"tx{i + 1}")

        # Page 1 (newest first): tx4, tx3.
        page1 = (await c.get("/ledger/transactions", params={"limit": 2})).json()
        assert [t["description"] for t in page1["data"]] == ["tx4", "tx3"]
        cursor = page1["next_cursor"]
        assert cursor

        # Insert a brand-new (newest) transaction between pages.
        await _add_tx(c, acct, -999, base + timedelta(days=10), "tx-new")

        # Page 2 continues from the cursor, unaffected by the insert.
        page2 = (await c.get("/ledger/transactions", params={"limit": 2, "cursor": cursor})).json()
        assert [t["description"] for t in page2["data"]] == ["tx2", "tx1"]
        # The new insert never leaks into an already-started pagination window.
        assert all(t["description"] != "tx-new" for t in page2["data"])


async def test_cross_tenant_edit_and_delete_rejected(seed_session):
    await make_household(seed_session, "ea@example.com")
    await make_household(seed_session, "eb@example.com")
    await seed_session.commit()
    async with _login("eb@example.com") as b:
        b_acct = await _make_account(b)
        b_tx = await _add_tx(b, b_acct, -100, date.today(), "B private")

    async with _login("ea@example.com") as a:
        assert (await a.patch(f"/ledger/transactions/{b_tx}", json={"amount_minor": -1})).status_code == 400
        assert (await a.delete(f"/ledger/transactions/{b_tx}")).status_code == 400
