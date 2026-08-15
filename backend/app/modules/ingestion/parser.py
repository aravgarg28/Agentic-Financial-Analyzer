"""CSV sniffing + row parsing (T-071).

Decoding is tried utf-8-sig (BOM) -> utf-8 -> latin-1 (never fails), so real-world
bank exports with BOMs or Latin-1 bytes don't crash. The delimiter is sniffed
from a sample. Row values are returned as strings; amount/date parsing to
minor-units/dates happens at staging (T-072), never here.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1")
_DELIMITERS = [",", ";", "\t", "|"]
_MAX_FIELD = 10000


@dataclass
class ParsedCsv:
    encoding: str
    delimiter: str
    headers: list[str]
    rows: list[dict[str, str]] = field(default_factory=list)
    total_rows: int = 0


def decode_bytes(data: bytes) -> tuple[str, str]:
    """Return (text, encoding_used). latin-1 decodes any byte string, so this
    always succeeds."""
    for enc in _ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace"), "latin-1"


def sniff_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(_DELIMITERS))
        return dialect.delimiter
    except csv.Error:
        # Fall back to whichever candidate appears most on the first line.
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        return max(_DELIMITERS, key=first_line.count) if first_line else ","


def parse_csv(data: bytes, *, skip_rows: int = 0, sample_limit: int | None = None) -> ParsedCsv:
    """Parse CSV bytes into headers + row dicts. ``skip_rows`` drops leading
    preamble lines before the header. ``sample_limit`` caps returned rows (for
    preview); total_rows always reflects the full count."""
    text, encoding = decode_bytes(data)
    sample = text[:8192]
    delimiter = sniff_delimiter(sample)

    csv.field_size_limit(_MAX_FIELD)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows = [r for r in reader]

    # Drop preamble, then the header row.
    body = all_rows[skip_rows:]
    if not body:
        return ParsedCsv(encoding=encoding, delimiter=delimiter, headers=[], rows=[], total_rows=0)

    headers = [h.strip() for h in body[0]]
    data_rows = body[1:]

    rows: list[dict[str, str]] = []
    for raw in data_rows:
        if not any(cell.strip() for cell in raw):
            continue  # skip fully blank lines
        row = {headers[i]: (raw[i] if i < len(raw) else "") for i in range(len(headers))}
        rows.append(row)

    total = len(rows)
    if sample_limit is not None:
        rows = rows[:sample_limit]
    return ParsedCsv(
        encoding=encoding, delimiter=delimiter, headers=headers, rows=rows, total_rows=total
    )
