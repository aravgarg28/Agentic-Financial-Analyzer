"""Built-in CSV mapping presets for common US bank/card exports (T-071).

These are shipped as data (not user rows) so a first import is one click. Formats
are approximate and header-matched case-insensitively; the definitive fixtures
live in the T-076 corpus. A preset matches when all of its ``match_headers`` are
present (case-insensitive), and the best (most-specific) match is suggested.
"""
from __future__ import annotations

from app.modules.ingestion.mapping import AmountSpec, DateSpec, MappingSpec


class Preset:
    def __init__(self, key: str, name: str, match_headers: list[str], mapping: MappingSpec):
        self.key = key
        self.name = name
        self.match_headers = [h.lower() for h in match_headers]
        self.mapping = mapping


BUILTIN_PRESETS: list[Preset] = [
    Preset(
        key="chase",
        name="Chase (checking/credit)",
        match_headers=["Transaction Date", "Description", "Amount"],
        mapping=MappingSpec(
            date=DateSpec(column="Transaction Date", format="%m/%d/%Y"),
            amount=AmountSpec(mode="single", column="Amount", sign="natural"),
            description_column="Description",
            category_column="Category",
        ),
    ),
    Preset(
        key="bofa",
        name="Bank of America (checking)",
        match_headers=["Date", "Description", "Amount", "Running Bal."],
        mapping=MappingSpec(
            date=DateSpec(column="Date", format="%m/%d/%Y"),
            amount=AmountSpec(mode="single", column="Amount", sign="natural"),
            description_column="Description",
        ),
    ),
    Preset(
        key="amex",
        name="American Express (card)",
        match_headers=["Date", "Description", "Amount"],
        mapping=MappingSpec(
            date=DateSpec(column="Date", format="%m/%d/%Y"),
            # Amex lists charges as positive numbers -> flip so expenses are negative.
            amount=AmountSpec(mode="single", column="Amount", sign="expense_positive"),
            description_column="Description",
        ),
    ),
    Preset(
        key="discover",
        name="Discover (card)",
        match_headers=["Trans. Date", "Description", "Amount", "Category"],
        mapping=MappingSpec(
            date=DateSpec(column="Trans. Date", format="%m/%d/%Y"),
            amount=AmountSpec(mode="single", column="Amount", sign="expense_positive"),
            description_column="Description",
            category_column="Category",
        ),
    ),
    Preset(
        key="capitalone",
        name="Capital One (card, debit/credit)",
        match_headers=["Transaction Date", "Description", "Debit", "Credit"],
        mapping=MappingSpec(
            date=DateSpec(column="Transaction Date", format="%Y-%m-%d"),
            amount=AmountSpec(mode="debit_credit", debit_column="Debit", credit_column="Credit"),
            description_column="Description",
            category_column="Category",
        ),
    ),
    Preset(
        key="generic",
        name="Generic (Date, Description, Amount)",
        match_headers=["Date", "Description", "Amount"],
        mapping=MappingSpec(
            date=DateSpec(column="Date", format="auto"),
            amount=AmountSpec(mode="single", column="Amount", sign="natural"),
            description_column="Description",
        ),
    ),
]


def match_presets(headers: list[str]) -> list[Preset]:
    """Presets whose match_headers are all present, most-specific first."""
    header_set = {h.lower() for h in headers}
    matched = [p for p in BUILTIN_PRESETS if all(h in header_set for h in p.match_headers)]
    matched.sort(key=lambda p: len(p.match_headers), reverse=True)
    return matched


def serialize_preset(preset: Preset) -> dict:
    return {
        "key": preset.key,
        "name": preset.name,
        "mapping": preset.mapping.model_dump(),
    }
