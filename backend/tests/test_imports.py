"""CSV import — upload endpoint (T-070): validation, storage, idempotency, quota.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from app.config import settings
from main import app
from tests.conftest import CSRF_HEADERS
from tests.helpers import make_household

SAMPLE_CSV = b"Date,Amount,Description\n2026-01-02,-12.34,Coffee Shop\n2026-01-03,2000.00,Payroll\n"


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


def _file(data: bytes = SAMPLE_CSV, name: str = "bank.csv", ctype: str = "text/csv"):
    return {"file": (name, data, ctype)}


async def test_upload_creates_staged_batch(seed_session):
    await make_household(seed_session, "up@example.com")
    await seed_session.commit()
    async with _login("up@example.com") as c:
        r = await c.post("/imports/upload", files=_file())
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["created"] is True
        assert body["status"] == "staged"
        assert body["filename"] == "bank.csv"


async def test_duplicate_checksum_returns_existing_batch(seed_session):
    await make_household(seed_session, "dup@example.com")
    await seed_session.commit()
    async with _login("dup@example.com") as c:
        first = (await c.post("/imports/upload", files=_file())).json()
        second = await c.post("/imports/upload", files=_file())
        assert second.status_code == 201
        body = second.json()
        assert body["created"] is False
        assert body["id"] == first["id"]


async def test_wrong_extension_rejected(seed_session):
    await make_household(seed_session, "ext@example.com")
    await seed_session.commit()
    async with _login("ext@example.com") as c:
        r = await c.post("/imports/upload", files=_file(b"MZ...", "malware.exe", "application/octet-stream"))
        assert r.status_code == 400


async def test_empty_file_rejected(seed_session):
    await make_household(seed_session, "empty@example.com")
    await seed_session.commit()
    async with _login("empty@example.com") as c:
        r = await c.post("/imports/upload", files=_file(b"", "empty.csv", "text/csv"))
        assert r.status_code == 400


async def test_oversize_rejected(seed_session, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 50)
    await make_household(seed_session, "big@example.com")
    await seed_session.commit()
    async with _login("big@example.com") as c:
        r = await c.post("/imports/upload", files=_file(b"x" * 200, "big.csv", "text/csv"))
        assert r.status_code == 413


async def test_quota_enforced(seed_session, monkeypatch):
    monkeypatch.setattr(settings, "household_document_quota_bytes", len(SAMPLE_CSV) + 5)
    await make_household(seed_session, "quota@example.com")
    await seed_session.commit()
    async with _login("quota@example.com") as c:
        first = await c.post("/imports/upload", files=_file())
        assert first.status_code == 201
        # A second, different file pushes past the tiny quota.
        r = await c.post("/imports/upload", files=_file(SAMPLE_CSV + b"2026-01-04,-1.00,Tea\n"))
        assert r.status_code == 400


async def test_upload_with_foreign_account_rejected(seed_session):
    await make_household(seed_session, "fa@example.com")
    _, mem_b = await make_household(seed_session, "fb@example.com")
    await seed_session.commit()
    async with _login("fb@example.com") as b:
        b_acct = (await b.post("/ledger/accounts", json={"name": "B", "type": "checking"})).json()["id"]
    async with _login("fa@example.com") as a:
        r = await a.post("/imports/upload", files=_file(), data={"account_id": b_acct})
        assert r.status_code == 400
