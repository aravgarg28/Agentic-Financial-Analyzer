"""End-to-end import corpus (T-076).

Six anonymized, real-world-shaped bank/card CSV fixtures are driven through the
whole pipeline (upload -> preview/preset -> stage -> dedup -> commit) and the
resulting ledger rows are asserted cent-exact. This locks ingestion correctness;
add a fixture + expected block here when supporting a new format.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from tests.conftest import CSRF_HEADERS
from tests.helpers import make_household

FIXTURES = Path(__file__).parent / "fixtures" / "csv"

# fixture filename, preset key to apply, expected {(booked_date, amount_minor, description)}
CORPUS = [
    (
        "chase.csv", "chase",
        {
            ("2026-01-02", -575, "STARBUCKS STORE 123"),
            ("2026-01-04", 320000, "PAYROLL DEPOSIT"),
            ("2026-01-06", -4210, "AMAZON MARKETPLACE"),
        },
    ),
    (
        "bofa.csv", "bofa",
        {
            ("2026-01-10", -5820, "GROCERY STORE #45"),
            ("2026-01-11", -4000, "SHELL GAS STATION"),
            ("2026-01-12", 120000, "DIRECT DEPOSIT"),
        },
    ),
    (
        "amex.csv", "amex",
        {
            ("2026-01-12", -22050, "GRAND HOTEL"),
            ("2026-01-13", -45000, "SKYWARD AIRLINES"),
            ("2026-01-14", 50000, "PAYMENT THANK YOU"),
        },
    ),
    (
        "discover.csv", "discover",
        {
            ("2026-01-15", -3540, "CORNER RESTAURANT"),
            ("2026-01-16", -8999, "ONLINE STORE INC"),
            ("2026-01-17", 1000, "CASHBACK BONUS"),
        },
    ),
    (
        "capitalone.csv", "capitalone",
        {
            ("2026-01-17", -425, "COFFEE HOUSE"),
            ("2026-01-18", 1500, "PURCHASE REFUND"),
            ("2026-01-19", -2780, "BOOKSTORE"),
        },
    ),
    (
        "creditunion.csv", "generic",
        {
            ("2026-01-20", 100000, "MEMBER SHARE DEPOSIT"),
            ("2026-01-21", -10000, "ATM WITHDRAWAL"),
            ("2026-01-22", 253, "DIVIDEND CREDIT"),
        },
    ),
]


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


@pytest.mark.parametrize("filename,preset_key,expected", CORPUS)
async def test_corpus_imports_cent_exact(seed_session, filename, preset_key, expected):
    email = f"corpus-{preset_key}@example.com"
    await make_household(seed_session, email)
    await seed_session.commit()
    data = (FIXTURES / filename).read_bytes()

    async with _login(email) as c:
        acct = (await c.post("/ledger/accounts", json={"name": "Import", "type": "checking"})).json()["id"]
        batch = (await c.post("/imports/upload", files={"file": (filename, data, "text/csv")})).json()["id"]

        # The matching preset must be offered by preview; use its mapping.
        preview = (await c.get(f"/imports/{batch}/preview")).json()
        preset = next((p for p in preview["presets"] if p["key"] == preset_key), None)
        assert preset is not None, f"{preset_key} not offered for {filename}"

        await c.post(f"/imports/{batch}/stage", json={"mapping": preset["mapping"]})
        dedup = (await c.post(f"/imports/{batch}/dedup", json={"account_id": acct})).json()
        assert dedup["error"] == 0, f"{filename} had parse errors: {dedup}"
        commit = (await c.post(f"/imports/{batch}/commit")).json()
        assert commit["committed"] == len(expected)

        rows = (await c.get("/ledger/transactions", params={"account_id": acct, "limit": 200})).json()["data"]
        got = {(r["booked_date"], r["amount_minor"], r["description"]) for r in rows}
    assert got == expected
