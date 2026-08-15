"""Duplicate detection engine (T-073).

Verdicts: 'duplicate' (exact fingerprint match against the committed ledger),
'near_dup' (a repeat fingerprint within the same batch — a legit same-day
same-amount pair, surfaced for review not auto-dropped), 'new' otherwise.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.modules.ingestion.models import ImportedRecord
from main import app
from tests.conftest import CSRF_HEADERS
from tests.helpers import make_household

MAPPING = {
    "date": {"column": "Date", "format": "%Y-%m-%d"},
    "amount": {"mode": "single", "column": "Amount", "sign": "natural"},
    "description_column": "Description",
}


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


async def _commit_tx(c, acct, amount_minor, booked_date, description):
    r = await c.post(
        "/ledger/transactions",
        json={"account_id": acct, "amount_minor": amount_minor, "booked_date": booked_date, "description": description},
    )
    assert r.status_code == 201


async def _upload_stage(c, csv: bytes):
    batch = (await c.post("/imports/upload", files={"file": ("f.csv", csv, "text/csv")})).json()["id"]
    await c.post(f"/imports/{batch}/stage", json={"mapping": MAPPING})
    return batch


async def _verdicts(session):
    rows = (await session.execute(select(ImportedRecord).order_by(ImportedRecord.row_number))).scalars().all()
    return [(r.dedup_verdict, r.user_decision) for r in rows]


async def test_dedup_flags_committed_duplicate_and_new(seed_session):
    await make_household(seed_session, "d1@example.com")
    await seed_session.commit()
    csv = b"Date,Description,Amount\n2026-01-02,Coffee,-4.35\n2026-01-03,New Store,-9.99\n"
    async with _login("d1@example.com") as c:
        acct = await _account(c)
        await _commit_tx(c, acct, -435, "2026-01-02", "Coffee")  # matches row 1
        batch = await _upload_stage(c, csv)
        summary = (await c.post(f"/imports/{batch}/dedup", json={"account_id": acct})).json()
        assert summary["duplicate"] == 1
        assert summary["new"] == 1

    assert await _verdicts(seed_session) == [("duplicate", "skip"), ("new", "accept")]


async def test_reimport_same_file_is_all_duplicate(seed_session):
    await make_household(seed_session, "d2@example.com")
    await seed_session.commit()
    csv = b"Date,Description,Amount\n2026-01-02,Coffee,-4.35\n2026-01-03,Lunch,-12.00\n"
    async with _login("d2@example.com") as c:
        acct = await _account(c)
        # "Commit" both rows to the ledger, then re-import the same file.
        await _commit_tx(c, acct, -435, "2026-01-02", "Coffee")
        await _commit_tx(c, acct, -1200, "2026-01-03", "Lunch")
        batch = await _upload_stage(c, csv)
        summary = (await c.post(f"/imports/{batch}/dedup", json={"account_id": acct})).json()
        assert summary == {"batch_id": batch, "new": 0, "duplicate": 2, "near_dup": 0, "error": 0}


async def test_intrabatch_repeat_is_near_dup_not_dropped(seed_session):
    await make_household(seed_session, "d3@example.com")
    await seed_session.commit()
    # Two identical coffees the same day — legit repeat.
    csv = b"Date,Description,Amount\n2026-01-02,Coffee,-4.35\n2026-01-02,Coffee,-4.35\n"
    async with _login("d3@example.com") as c:
        acct = await _account(c)
        batch = await _upload_stage(c, csv)
        summary = (await c.post(f"/imports/{batch}/dedup", json={"account_id": acct})).json()
        assert summary["new"] == 1
        assert summary["near_dup"] == 1

    verdicts = await _verdicts(seed_session)
    # The repeat is flagged for review (pending), never auto-skipped.
    assert verdicts == [("new", "accept"), ("near_dup", "pending")]


async def test_dedup_is_whitespace_and_case_invariant(seed_session):
    await make_household(seed_session, "d4@example.com")
    await seed_session.commit()
    csv = b"Date,Description,Amount\n2026-01-02,BLUE   BOTTLE,-4.35\n"
    async with _login("d4@example.com") as c:
        acct = await _account(c)
        await _commit_tx(c, acct, -435, "2026-01-02", "Blue Bottle")
        batch = await _upload_stage(c, csv)
        summary = (await c.post(f"/imports/{batch}/dedup", json={"account_id": acct})).json()
        assert summary["duplicate"] == 1


async def test_dedup_requires_account(seed_session):
    await make_household(seed_session, "d5@example.com")
    await seed_session.commit()
    csv = b"Date,Description,Amount\n2026-01-02,Coffee,-4.35\n"
    async with _login("d5@example.com") as c:
        # Upload with no account, stage, then dedup with no account -> 400.
        batch = await _upload_stage(c, csv)
        r = await c.post(f"/imports/{batch}/dedup", json={})
        assert r.status_code == 400


async def test_error_rows_are_not_deduped(seed_session):
    await make_household(seed_session, "d6@example.com")
    await seed_session.commit()
    csv = b"Date,Description,Amount\nbad-date,Broken,-4.35\n2026-01-02,Ok,-1.00\n"
    async with _login("d6@example.com") as c:
        acct = await _account(c)
        batch = await _upload_stage(c, csv)
        summary = (await c.post(f"/imports/{batch}/dedup", json={"account_id": acct})).json()
        assert summary["error"] == 1
        assert summary["new"] == 1

    verdicts = await _verdicts(seed_session)
    assert verdicts[0] == (None, "skip")  # error row not committable
