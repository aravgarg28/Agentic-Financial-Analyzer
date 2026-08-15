"""Cross-tenant isolation matrix (T-022, SEC-01/AGT-05).

Proves that a session for household A can never read or write household B's
data, and forces every future route to be explicitly classified: the matrix
test fails if the app grows a route not listed as public or tenant-scoped.
"""
from __future__ import annotations

from datetime import date

from httpx import ASGITransport, AsyncClient

from main import app
from tests.conftest import CSRF_HEADERS
from tests.helpers import add_account, add_category, add_transaction, make_household

# Every registered application route must appear in exactly one bucket. A new
# route with no classification trips ``test_every_route_is_classified`` — the
# guarantee that future endpoints get considered for tenant isolation.
PUBLIC_ROUTES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    # OpenAPI/docs are framework routes, not tenant data.
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
}

# Authenticated routes: reject anonymous callers, and only ever serve the
# caller's own household.
AUTHENTICATED_ROUTES = {
    ("POST", "/auth/logout"),
    ("POST", "/auth/logout-all"),
    ("GET", "/auth/me"),
    ("PATCH", "/household"),
    ("GET", "/insights/spending-by-category"),
    ("GET", "/insights/monthly-trends"),
    ("GET", "/insights/cash-flow-summary"),
    ("GET", "/insights/top-merchants"),
    ("GET", "/insights/recent-transactions"),
    ("GET", "/insights/budgets"),
    ("PUT", "/insights/budgets"),
    ("GET", "/insights/budget-alerts"),
    ("GET", "/ledger/accounts"),
    ("POST", "/ledger/accounts"),
    ("PATCH", "/ledger/accounts/{public_id}"),
    ("POST", "/ledger/accounts/{public_id}/archive"),
    ("POST", "/ledger/accounts/{public_id}/unarchive"),
    ("GET", "/ledger/institutions"),
    ("POST", "/ledger/institutions"),
    ("POST", "/ledger/transactions"),
    ("GET", "/ledger/transactions"),
    ("PATCH", "/ledger/transactions/{public_id}"),
    ("DELETE", "/ledger/transactions/{public_id}"),
    ("GET", "/ledger/categories"),
    ("POST", "/ledger/categories"),
    ("PATCH", "/ledger/categories/{category_id}"),
    ("DELETE", "/ledger/categories/{category_id}"),
    ("POST", "/ledger/transactions/{public_id}/recategorize"),
    ("POST", "/imports/upload"),
    ("GET", "/imports/{batch_id}/preview"),
    ("POST", "/imports/{batch_id}/stage"),
    ("GET", "/imports/mappings"),
    ("POST", "/imports/mappings"),
    ("POST", "/agent/query"),
}


def _app_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if not path or not methods:
            continue
        for m in methods:
            if m in ("HEAD", "OPTIONS"):
                continue
            routes.add((m, path))
    return routes


def test_every_route_is_classified():
    """Any new route must be added to PUBLIC or AUTHENTICATED explicitly."""
    classified = PUBLIC_ROUTES | AUTHENTICATED_ROUTES
    unclassified = _app_routes() - classified
    assert not unclassified, (
        f"Unclassified routes (add to tenant matrix): {sorted(unclassified)}"
    )


async def _new_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=CSRF_HEADERS,
    )


async def test_authenticated_routes_reject_anonymous(seed_session):
    """No cookie -> 401/403 on every authenticated route, never 200 data."""
    async with await _new_client() as anon:
        for method, path in AUTHENTICATED_ROUTES:
            resp = await anon.request(method, path, json={})
            assert resp.status_code in (401, 403), f"{method} {path} -> {resp.status_code}"


async def test_cross_tenant_account_and_data_isolation(seed_session):
    """SEC-01: A's session cannot use B's account id, and A's insights never
    include B's transactions."""
    # Arrange two households with their own account + a transaction each.
    _, mem_a = await make_household(seed_session, "a@example.com")
    _, mem_b = await make_household(seed_session, "b@example.com")
    acct_a = await add_account(seed_session, mem_a.household_id, "A-Checking")
    acct_b = await add_account(seed_session, mem_b.household_id, "B-Checking")
    cat = await add_category(seed_session, None, "Groceries")
    await add_transaction(
        seed_session,
        household_id=mem_a.household_id,
        account_id=acct_a.id,
        amount_minor=-1500,
        booked_date=date.today(),
        description="A-only coffee",
        category_id=cat.id,
    )
    await add_transaction(
        seed_session,
        household_id=mem_b.household_id,
        account_id=acct_b.id,
        amount_minor=-9999,
        booked_date=date.today(),
        description="B-secret yacht",
        category_id=cat.id,
    )
    await seed_session.commit()
    acct_b_public = acct_b.public_id

    # Log in as A.
    async with await _new_client() as a:
        login = await a.post(
            "/auth/login",
            json={"email": "a@example.com", "password": "a-strong-passphrase-1"},
        )
        assert login.status_code == 200

        # A lists accounts: only A's account is visible.
        accounts = (await a.get("/ledger/accounts")).json()["data"]
        names = {x["name"] for x in accounts}
        assert names == {"A-Checking"}

        # A tries to post a transaction into B's account -> rejected (404-ish 400).
        attack = await a.post(
            "/ledger/transactions",
            json={
                "account_id": acct_b_public,
                "amount_minor": -100,
                "booked_date": date.today().isoformat(),
                "description": "cross-tenant write",
            },
        )
        assert attack.status_code == 400

        # A's recent transactions never include B's data.
        recent = (await a.get("/insights/recent-transactions")).json()["data"]
        descriptions = " ".join(str(r["description"]) for r in recent)
        assert "yacht" not in descriptions
        assert "coffee" in descriptions

        # A's cash-flow reflects only A's spend (1500 minor), not B's.
        summary = (await a.get("/insights/cash-flow-summary")).json()
        assert summary["expenses_minor"] == 1500


def test_agent_memory_key_is_tenant_scoped():
    """AGT-05: the Redis conversation key derives from the household id, so two
    households with the same conversation id get distinct keys."""
    from app.agent.memory import conversation_key

    assert conversation_key(1, "chat") != conversation_key(2, "chat")
    assert conversation_key(1, "chat").startswith("chat:1:")
