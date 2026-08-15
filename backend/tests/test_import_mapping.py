"""CSV mapping + presets (T-071): sniffing/preview, auto-suggestion, built-in
presets, and saved mappings.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from app.modules.ingestion import parser
from app.modules.ingestion.mapping import suggest_mapping
from app.modules.ingestion.presets import match_presets
from main import app
from tests.conftest import CSRF_HEADERS
from tests.helpers import make_household

CHASE_CSV = (
    b"Transaction Date,Post Date,Description,Category,Type,Amount\n"
    b"01/02/2026,01/03/2026,COFFEE SHOP,Food & Drink,Sale,-4.50\n"
    b"01/05/2026,01/06/2026,PAYROLL,Income,Payment,2500.00\n"
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


# --------------------------------------------------------------------------- #
# Pure parsing/mapping (no DB)
# --------------------------------------------------------------------------- #
def test_parser_sniffs_delimiter_and_bom():
    # UTF-8 BOM + semicolon delimiter.
    data = "﻿Date;Description;Amount\n2026-01-01;Tea;-2.00\n".encode()
    parsed = parser.parse_csv(data)
    assert parsed.delimiter == ";"
    assert parsed.headers == ["Date", "Description", "Amount"]
    assert parsed.rows[0]["Description"] == "Tea"
    assert parsed.total_rows == 1


def test_parser_handles_latin1():
    data = "Date,Description,Amount\n2026-01-01,Caf\xe9,-3.00\n".encode("latin-1")
    parsed = parser.parse_csv(data)
    assert parsed.encoding in ("latin-1", "utf-8")  # café decodes under latin-1
    assert parsed.rows[0]["Amount"] == "-3.00"


def test_suggest_mapping_from_headers():
    headers = ["Transaction Date", "Description", "Amount", "Category"]
    mapping, notes = suggest_mapping(headers)
    assert mapping is not None
    assert mapping.date.column == "Transaction Date"
    assert mapping.description_column == "Description"
    assert mapping.amount.mode == "single"
    assert mapping.amount.column == "Amount"
    assert mapping.category_column == "Category"


def test_suggest_mapping_detects_debit_credit_pair():
    mapping, _ = suggest_mapping(["Transaction Date", "Description", "Debit", "Credit"])
    assert mapping is not None
    assert mapping.amount.mode == "debit_credit"
    assert mapping.amount.debit_column == "Debit"
    assert mapping.amount.credit_column == "Credit"


def test_preset_matching():
    matched = match_presets(["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount"])
    keys = [p.key for p in matched]
    assert "chase" in keys


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
async def _upload(client, data=CHASE_CSV, name="chase.csv"):
    r = await client.post("/imports/upload", files={"file": (name, data, "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_preview_returns_headers_sample_and_suggestion(seed_session):
    await make_household(seed_session, "prev@example.com")
    await seed_session.commit()
    async with _login("prev@example.com") as c:
        batch_id = await _upload(c)
        preview = (await c.get(f"/imports/{batch_id}/preview")).json()
        assert preview["headers"][0] == "Transaction Date"
        assert preview["total_rows"] == 2
        assert len(preview["sample_rows"]) == 2
        assert preview["suggested_mapping"]["description_column"] == "Description"
        assert any(p["key"] == "chase" for p in preview["presets"])


async def test_save_and_list_mapping(seed_session):
    await make_household(seed_session, "map@example.com")
    await seed_session.commit()
    async with _login("map@example.com") as c:
        batch_id = await _upload(c)
        suggested = (await c.get(f"/imports/{batch_id}/preview")).json()["suggested_mapping"]

        saved = await c.post(
            "/imports/mappings", json={"name": "My Chase", "mapping": suggested}
        )
        assert saved.status_code == 201
        listing = (await c.get("/imports/mappings")).json()["data"]
        assert [m["name"] for m in listing] == ["My Chase"]

        # Duplicate name rejected.
        dup = await c.post("/imports/mappings", json={"name": "My Chase", "mapping": suggested})
        assert dup.status_code == 400


async def test_preview_is_tenant_scoped(seed_session):
    await make_household(seed_session, "pa@example.com")
    await make_household(seed_session, "pb@example.com")
    await seed_session.commit()
    async with _login("pb@example.com") as b:
        b_batch = await _upload(b)
    async with _login("pa@example.com") as a:
        # A cannot preview B's batch.
        assert (await a.get(f"/imports/{b_batch}/preview")).status_code == 400
