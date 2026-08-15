"""Column-mapping schema + auto-suggestion (T-071).

A mapping tells the stager how to turn source CSV columns into canonical fields:
which column is the date (and its strptime format), how the amount is expressed
(a single signed column, or separate debit/credit columns, plus a sign
convention), which column is the description, and optionally category/currency.
Money conventions are applied at staging (T-072); this module only describes and
validates the mapping.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DateSpec(BaseModel):
    column: str
    # strptime format, or "auto" to try a list of common formats at staging.
    format: str = "auto"


class AmountSpec(BaseModel):
    mode: Literal["single", "debit_credit"] = "single"
    # single mode:
    column: str | None = None
    # 'natural': value as-is (negative = money out). 'expense_positive': positive
    # numbers are expenses (credit-card exports) and get their sign flipped.
    sign: Literal["natural", "expense_positive"] = "natural"
    # debit_credit mode:
    debit_column: str | None = None
    credit_column: str | None = None

    @model_validator(mode="after")
    def _check(self) -> AmountSpec:
        if self.mode == "single":
            if not self.column:
                raise ValueError("single amount mode requires 'column'")
        else:
            if not (self.debit_column and self.credit_column):
                raise ValueError(
                    "debit_credit mode requires 'debit_column' and 'credit_column'"
                )
        return self


class MappingSpec(BaseModel):
    date: DateSpec
    amount: AmountSpec
    description_column: str
    category_column: str | None = None
    currency: str | None = Field(None, min_length=3, max_length=3)
    skip_rows: int = Field(0, ge=0, le=100)

    def referenced_columns(self) -> list[str]:
        cols = [self.date.column, self.description_column]
        if self.amount.mode == "single" and self.amount.column:
            cols.append(self.amount.column)
        else:
            cols += [self.amount.debit_column or "", self.amount.credit_column or ""]
        if self.category_column:
            cols.append(self.category_column)
        return [c for c in cols if c]

    def validate_against(self, headers: list[str]) -> list[str]:
        """Return the list of referenced columns missing from ``headers``."""
        header_set = set(headers)
        return [c for c in self.referenced_columns() if c not in header_set]


# Header-name hints for auto-suggestion (lowercased substring match).
_DATE_HINTS = ("transaction date", "trans. date", "trans date", "posted date", "post date", "date")
_DESC_HINTS = ("description", "payee", "merchant", "name", "memo", "details")
_AMOUNT_HINTS = ("amount", "value")
_DEBIT_HINTS = ("debit", "withdrawal", "money out")
_CREDIT_HINTS = ("credit", "deposit", "money in")
_CATEGORY_HINTS = ("category",)


def _first_match(headers: list[str], hints: tuple[str, ...]) -> str | None:
    lowered = [(h, h.lower()) for h in headers]
    for hint in hints:
        for original, low in lowered:
            if hint == low:
                return original
    for hint in hints:
        for original, low in lowered:
            if hint in low:
                return original
    return None


def suggest_mapping(headers: list[str]) -> tuple[MappingSpec | None, list[str]]:
    """Best-effort mapping from header names. Returns (mapping_or_None, notes).
    Ambiguity is surfaced as notes rather than guessed silently."""
    notes: list[str] = []
    date_col = _first_match(headers, _DATE_HINTS)
    desc_col = _first_match(headers, _DESC_HINTS)
    debit_col = _first_match(headers, _DEBIT_HINTS)
    credit_col = _first_match(headers, _CREDIT_HINTS)
    amount_col = _first_match(headers, _AMOUNT_HINTS)
    category_col = _first_match(headers, _CATEGORY_HINTS)

    if not date_col:
        notes.append("Could not identify a date column.")
    if not desc_col:
        notes.append("Could not identify a description column.")

    amount: AmountSpec | None = None
    if debit_col and credit_col:
        amount = AmountSpec(mode="debit_credit", debit_column=debit_col, credit_column=credit_col)
    elif amount_col:
        amount = AmountSpec(mode="single", column=amount_col, sign="natural")
        notes.append(
            "Assumed negative amounts are expenses; if this is a credit-card "
            "export where charges are positive, set sign to 'expense_positive'."
        )
    else:
        notes.append("Could not identify an amount column (or debit/credit pair).")

    if not (date_col and desc_col and amount):
        return None, notes

    return (
        MappingSpec(
            date=DateSpec(column=date_col, format="auto"),
            amount=amount,
            description_column=desc_col,
            category_column=category_col,
        ),
        notes,
    )
