"""Value coercion for staging (T-072): strings -> integer minor units / dates.

Money is parsed via Decimal and never through float (G-MONEY / FIN-01), handling
thousands separators, currency symbols, parentheses-negatives, and DR/CR
suffixes. Dates are parsed against the mapping's format, or a list of common
formats when the format is "auto" (US month/day ordering, per D1).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Strip currency symbols, thousands separators, and whitespace (NOT the sign).
_STRIP = re.compile(r"[,\s$€£¥]")
_DR = re.compile(r"(?i)\s*DR\.?$")
_CR = re.compile(r"(?i)\s*CR\.?$")

_AUTO_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%Y/%m/%d",
    "%m-%d-%Y",
    "%d-%b-%Y",
    "%b %d, %Y",
    "%d %b %Y",
)


def parse_amount_minor(raw: str) -> tuple[int | None, str | None]:
    """Parse a money string to signed integer minor units (cents).

    Returns (minor, error). Never uses float. Understands: '1,234.56', '$1,234.56',
    '(12.34)' (negative), '12.34 DR' (negative) / '12.34 CR' (positive), and a
    leading +/-.
    """
    if raw is None:
        return None, "missing amount"
    s = raw.strip()
    if s == "":
        return None, "empty amount"

    negative = False
    # DR/CR debit/credit indicators.
    if _DR.search(s):
        negative = True
        s = _DR.sub("", s).strip()
    elif _CR.search(s):
        negative = False
        s = _CR.sub("", s).strip()

    # Parentheses accounting-negative.
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()

    cleaned = _STRIP.sub("", s)
    if cleaned in ("", "+", "-"):
        return None, f"unparseable amount: {raw!r}"
    try:
        dec = Decimal(cleaned)
    except InvalidOperation:
        return None, f"unparseable amount: {raw!r}"

    magnitude = (abs(dec) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    minor = int(magnitude)
    if negative or dec < 0:
        minor = -minor
    return minor, None


def apply_sign_convention(minor: int, sign: str) -> int:
    """'natural' keeps the parsed sign; 'expense_positive' flips it so a positive
    charge (credit-card export) becomes a negative expense."""
    if sign == "expense_positive":
        return -minor
    return minor


def parse_amount_debit_credit(
    debit_raw: str | None, credit_raw: str | None
) -> tuple[int | None, str | None]:
    """Combine a debit/credit column pair: debit is money out (negative), credit
    is money in (positive). Exactly one side is normally populated."""
    debit_minor = 0
    credit_minor = 0
    if debit_raw and debit_raw.strip():
        debit_minor, err = parse_amount_minor(debit_raw)
        if err:
            return None, err
        debit_minor = abs(debit_minor)
    if credit_raw and credit_raw.strip():
        credit_minor, err = parse_amount_minor(credit_raw)
        if err:
            return None, err
        credit_minor = abs(credit_minor)
    if debit_minor == 0 and credit_minor == 0:
        return None, "no debit or credit value"
    return credit_minor - debit_minor, None


def parse_date(raw: str, fmt: str) -> tuple[date | None, str | None]:
    """Parse a date string. ``fmt`` is a strptime format, or 'auto' to try a list
    of common formats (US month/day ordering)."""
    if raw is None or raw.strip() == "":
        return None, "empty date"
    s = raw.strip()
    formats = _AUTO_DATE_FORMATS if fmt == "auto" else (fmt,)
    for f in formats:
        try:
            return datetime.strptime(s, f).date(), None
        except ValueError:
            continue
    return None, f"unparseable date: {raw!r}"
