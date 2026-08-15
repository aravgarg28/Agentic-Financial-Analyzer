"""CSV staging + row validation (T-072).

The money parser is the correctness core: amounts go straight to integer minor
units via Decimal, never float. The float trap (4.35 * 100 == 434.9999...) is
tested explicitly.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.modules.ingestion import coerce
from app.modules.ingestion.models import ImportedRecord
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


# --------------------------------------------------------------------------- #
# Money parser — pure, no DB
# --------------------------------------------------------------------------- #
def test_parse_amount_minor_variants():
    cases = {
        "12.34": 1234,
        "1,234.56": 123456,
        "$1,234.56": 123456,
        "-12.34": -1234,
        "(12.34)": -1234,
        "12.34 DR": -1234,
        "12.34 CR": 1234,
        "12": 1200,
        "0.05": 5,
        ".5": 50,
        "+7.00": 700,
    }
    for raw, expected in cases.items():
        minor, err = coerce.parse_amount_minor(raw)
        assert err is None, f"{raw!r} -> {err}"
        assert minor == expected, f"{raw!r} -> {minor} (want {expected})"


def test_parse_amount_avoids_float_rounding():
    # 4.35 * 100 == 434.9999999999 in binary float; Decimal must give 435.
    for raw, expected in {"4.35": 435, "2.67": 267, "1.10": 110, "19.99": 1999}.items():
        minor, err = coerce.parse_amount_minor(raw)
        assert err is None and minor == expected, f"{raw} -> {minor}"


def test_parse_amount_rejects_garbage():
    for raw in ("abc", "", "   ", "1.2.3", "$"):
        minor, err = coerce.parse_amount_minor(raw)
        assert minor is None and err is not None


def test_sign_convention_and_debit_credit():
    assert coerce.apply_sign_convention(1234, "natural") == 1234
    assert coerce.apply_sign_convention(1234, "expense_positive") == -1234
    assert coerce.parse_amount_debit_credit("12.34", "") == (-1234, None)
    assert coerce.parse_amount_debit_credit("", "50.00") == (5000, None)
    minor, err = coerce.parse_amount_debit_credit("", "")
    assert minor is None and err is not None


def test_parse_date_formats():
    assert coerce.parse_date("01/02/2026", "%m/%d/%Y") == (date(2026, 1, 2), None)
    assert coerce.parse_date("2026-01-02", "auto") == (date(2026, 1, 2), None)
    assert coerce.parse_date("01/02/2026", "auto") == (date(2026, 1, 2), None)
    d, err = coerce.parse_date("nope", "auto")
    assert d is None and err is not None


# --------------------------------------------------------------------------- #
# Staging integration
# --------------------------------------------------------------------------- #
GENERIC_CSV = (
    b"Date,Description,Amount\n"
    b"2026-01-02,Coffee,-4.35\n"
    b"2026-01-05,Payroll,2500.00\n"
)
GENERIC_MAPPING = {
    "date": {"column": "Date", "format": "%Y-%m-%d"},
    "amount": {"mode": "single", "column": "Amount", "sign": "natural"},
    "description_column": "Description",
}


async def _upload(client, data, name="f.csv"):
    r = await client.post("/imports/upload", files={"file": (name, data, "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _records(session, batch_public_id_owner_household):
    result = await session.execute(
        select(ImportedRecord).order_by(ImportedRecord.row_number)
    )
    return list(result.scalars().all())


async def test_stage_produces_parsed_records(seed_session):
    await make_household(seed_session, "stg@example.com")
    await seed_session.commit()
    async with _login("stg@example.com") as c:
        batch = await _upload(c, GENERIC_CSV)
        summary = (await c.post(f"/imports/{batch}/stage", json={"mapping": GENERIC_MAPPING})).json()
        assert summary["total"] == 2
        assert summary["errors"] == 0

    records = await _records(seed_session, None)
    assert [r.parsed_amount_minor for r in records] == [-435, 250000]
    assert [r.parsed_date for r in records] == [date(2026, 1, 2), date(2026, 1, 5)]
    assert records[0].parsed_description == "Coffee"


async def test_stage_flags_invalid_rows(seed_session):
    await make_household(seed_session, "bad@example.com")
    await seed_session.commit()
    bad_csv = b"Date,Description,Amount\nnot-a-date,Ok,-1.00\n2026-01-02,,oops\n"
    async with _login("bad@example.com") as c:
        batch = await _upload(c, bad_csv)
        summary = (await c.post(f"/imports/{batch}/stage", json={"mapping": GENERIC_MAPPING})).json()
        assert summary["total"] == 2
        assert summary["errors"] == 2  # row1 bad date, row2 bad amount

    records = await _records(seed_session, None)
    assert any("date" in e for e in records[0].validation["errors"])
    assert any("amount" in e for e in records[1].validation["errors"])


async def test_stage_is_rerunnable(seed_session):
    await make_household(seed_session, "re@example.com")
    await seed_session.commit()
    async with _login("re@example.com") as c:
        batch = await _upload(c, GENERIC_CSV)
        await c.post(f"/imports/{batch}/stage", json={"mapping": GENERIC_MAPPING})
        # Re-stage with the same mapping — records replaced, not duplicated.
        again = (await c.post(f"/imports/{batch}/stage", json={"mapping": GENERIC_MAPPING})).json()
        assert again["total"] == 2

    records = await _records(seed_session, None)
    assert len(records) == 2


async def test_stage_rejects_mapping_with_missing_column(seed_session):
    await make_household(seed_session, "miss@example.com")
    await seed_session.commit()
    async with _login("miss@example.com") as c:
        batch = await _upload(c, GENERIC_CSV)
        bad_mapping = dict(GENERIC_MAPPING, description_column="Nonexistent")
        r = await c.post(f"/imports/{batch}/stage", json={"mapping": bad_mapping})
        assert r.status_code == 400


async def test_expense_positive_flips_sign(seed_session):
    await make_household(seed_session, "amex@example.com")
    await seed_session.commit()
    amex_csv = b"Date,Description,Amount\n01/02/2026,Restaurant,45.00\n"
    mapping = {
        "date": {"column": "Date", "format": "%m/%d/%Y"},
        "amount": {"mode": "single", "column": "Amount", "sign": "expense_positive"},
        "description_column": "Description",
    }
    async with _login("amex@example.com") as c:
        batch = await _upload(c, amex_csv)
        await c.post(f"/imports/{batch}/stage", json={"mapping": mapping})

    records = await _records(seed_session, None)
    assert records[0].parsed_amount_minor == -4500  # positive charge -> negative expense
