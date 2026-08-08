"""Category taxonomy (T-062): system defaults, user CRUD, 2-level hierarchy,
type safety, and transaction recategorization.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from httpx import ASGITransport, AsyncClient

from app.modules.ledger.system_categories import ensure_system_categories
from main import app
from tests.conftest import CSRF_HEADERS
from tests.helpers import add_account, add_transaction, make_household


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


async def test_system_categories_available_and_readonly(seed_session):
    await make_household(seed_session, "sys@example.com")
    await ensure_system_categories(seed_session)
    await seed_session.commit()

    async with _login("sys@example.com") as c:
        cats = (await c.get("/ledger/categories")).json()["data"]
        system = [x for x in cats if x["is_system"]]
        types = {x["type"] for x in system}
        assert types == {"income", "expense", "transfer"}
        assert any(x["name"] == "Groceries" for x in system)

        # System categories are read-only for a household (resolves as not-found).
        sys_id = system[0]["id"]
        assert (await c.patch(f"/ledger/categories/{sys_id}", json={"name": "Hijack"})).status_code == 400
        assert (await c.delete(f"/ledger/categories/{sys_id}")).status_code == 400


async def test_user_category_crud_and_hierarchy(seed_session):
    await make_household(seed_session, "cat@example.com")
    await seed_session.commit()

    async with _login("cat@example.com") as c:
        # Create a top-level expense category.
        parent = await c.post(
            "/ledger/categories", json={"name": "Food", "type": "expense"}
        )
        assert parent.status_code == 201
        assert parent.json()["is_system"] is False
        parent_id = parent.json()["id"]

        # A child under it is allowed (2 levels).
        child = await c.post(
            "/ledger/categories",
            json={"name": "Restaurants", "type": "expense", "parent_id": parent_id},
        )
        assert child.status_code == 201
        child_id = child.json()["id"]

        # A grandchild is rejected (max 2 levels).
        grandchild = await c.post(
            "/ledger/categories",
            json={"name": "Fast Food", "type": "expense", "parent_id": child_id},
        )
        assert grandchild.status_code == 400

        # Subcategory type must match its parent.
        bad_type = await c.post(
            "/ledger/categories",
            json={"name": "Bonus", "type": "income", "parent_id": parent_id},
        )
        assert bad_type.status_code == 400

        # Duplicate (household, parent, name) rejected.
        dup = await c.post("/ledger/categories", json={"name": "Food", "type": "expense"})
        assert dup.status_code == 400

        # Rename works.
        renamed = await c.patch(f"/ledger/categories/{parent_id}", json={"name": "Groceries & Dining"})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Groceries & Dining"


async def test_invalid_type_rejected(seed_session):
    await make_household(seed_session, "typ@example.com")
    await seed_session.commit()
    async with _login("typ@example.com") as c:
        r = await c.post("/ledger/categories", json={"name": "X", "type": "asset"})
        assert r.status_code == 400


async def test_delete_soft_deletes_and_cascades_children(seed_session):
    await make_household(seed_session, "del@example.com")
    await seed_session.commit()
    async with _login("del@example.com") as c:
        parent_id = (await c.post("/ledger/categories", json={"name": "Home", "type": "expense"})).json()["id"]
        await c.post("/ledger/categories", json={"name": "Rent", "type": "expense", "parent_id": parent_id})

        before = (await c.get("/ledger/categories")).json()["data"]
        assert {"Home", "Rent"} <= {x["name"] for x in before}

        assert (await c.delete(f"/ledger/categories/{parent_id}")).status_code == 200

        after = {x["name"] for x in (await c.get("/ledger/categories")).json()["data"]}
        assert "Home" not in after and "Rent" not in after


async def test_recategorize_transaction(seed_session):
    _, mem = await make_household(seed_session, "recat@example.com")
    acct = await add_account(seed_session, mem.household_id)
    tx = await add_transaction(
        seed_session,
        household_id=mem.household_id,
        account_id=acct.id,
        amount_minor=-2500,
        booked_date=date.today(),
        description="mystery charge",
    )
    await seed_session.commit()
    tx_pid = tx.public_id

    async with _login("recat@example.com") as c:
        cat_id = (await c.post("/ledger/categories", json={"name": "Misc", "type": "expense"})).json()["id"]

        # Assign.
        assigned = await c.post(f"/ledger/transactions/{tx_pid}/recategorize", json={"category_id": cat_id})
        assert assigned.status_code == 200
        assert assigned.json()["category_id"] == cat_id

        # Clear (uncategorize).
        cleared = await c.post(f"/ledger/transactions/{tx_pid}/recategorize", json={"category_id": None})
        assert cleared.status_code == 200
        assert cleared.json()["category_id"] is None


async def test_recategorize_rejects_foreign_category(seed_session):
    _, mem_a = await make_household(seed_session, "ra@example.com")
    _, mem_b = await make_household(seed_session, "rb@example.com")
    acct_a = await add_account(seed_session, mem_a.household_id)
    tx = await add_transaction(
        seed_session,
        household_id=mem_a.household_id,
        account_id=acct_a.id,
        amount_minor=-100,
        booked_date=date.today(),
        description="a charge",
    )
    await seed_session.commit()
    tx_pid = tx.public_id

    async with _login("rb@example.com") as b:
        b_cat = (await b.post("/ledger/categories", json={"name": "B Cat", "type": "expense"})).json()["id"]

    async with _login("ra@example.com") as a:
        # A's transaction cannot be tagged with B's category.
        r = await a.post(f"/ledger/transactions/{tx_pid}/recategorize", json={"category_id": b_cat})
        assert r.status_code == 400
