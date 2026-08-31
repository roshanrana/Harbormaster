"""Writing canonical records out for the reconciliation engine.

Output is typed Parquet, not CSV (ADR-006). Two properties matter and CSV has
neither: a null stays distinguishable from a zero, and money stays a decimal
rather than becoming a float. A missing settlement price that arrives
downstream as ``0.00`` breaks against every row; a net amount that round-trips
through float64 eventually produces a one-cent difference that costs an analyst
an afternoon and costs the tool its credibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl

from inspector.mapping import canonical as c
from inspector.mapping.tier1 import Mapping, to_decimal
from inspector.parsers.base import ParsedTable

# Fields carrying money or quantities. Stored as Decimal128 so arithmetic
# downstream is exact.
_DECIMAL_FIELDS = (
    "quantity",
    "trade_price",
    "settlement_price",
    "gross_amount",
    "net_amount",
    "market_value",
)

_DECIMAL_PRECISION = 28
_DECIMAL_SCALE = 8

# Side values normalise to these so the recon engine compares like with like.
_SIDE_NORMALISATION = {
    "b": "BUY",
    "buy": "BUY",
    "bought": "BUY",
    "1": "BUY",
    "l": "LONG",
    "long": "LONG",
    "s": "SELL",
    "sell": "SELL",
    "sold": "SELL",
    "2": "SELL",
    "sh": "SHORT",
    "short": "SHORT",
}


@dataclass(slots=True)
class EmitResult:
    path: Path
    uri: str
    row_count: int


def normalise_side(raw: str) -> str | None:
    text = raw.strip().lower()
    if not text:
        return None
    return _SIDE_NORMALISATION.get(text, raw.strip().upper())


def build_records(
    *,
    table: ParsedTable,
    mappings: list[Mapping],
    arrival_id: str,
    client_id: str,
    value_date: str,
    domain: str,
    source_system: str,
    account_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Project parsed rows onto the canonical schema.

    Fields Harbormaster determined itself (client, value date, domain) are
    stamped on rather than read from a column. A column claiming to be the
    value date is exactly the input this system exists to distrust, so it is
    never allowed to reach the output directly.
    """
    by_field = {m.canonical_field: m.source_field for m in mappings if m.canonical_field}
    names = account_names or {}
    out: list[dict[str, Any]] = []

    for row in table.rows:
        record: dict[str, Any] = {
            "arrival_id": arrival_id,
            "client_id": client_id,
            "value_date": value_date,
            "domain": domain,
            "source_system": source_system,
        }
        for canonical_field in c.CANONICAL_FIELDS:
            if canonical_field in record:
                continue
            source = by_field.get(canonical_field)
            raw = (row.get(source) or "").strip() if source else ""
            if canonical_field in _DECIMAL_FIELDS:
                record[canonical_field] = to_decimal(raw)
            elif canonical_field == "side":
                record[canonical_field] = normalise_side(raw)
            else:
                record[canonical_field] = raw or None

        account_id = record.get("account_id")
        if not record.get("account_name") and account_id:
            # The registry knows account names even when the file omits them,
            # and names are what an operator recognises on a board.
            record["account_name"] = names.get(account_id)
        out.append(record)
    return out


def _schema() -> dict[str, pl.DataType]:
    schema: dict[str, pl.DataType] = {}
    for name in c.CANONICAL_FIELDS:
        if name in _DECIMAL_FIELDS:
            schema[name] = pl.Decimal(precision=_DECIMAL_PRECISION, scale=_DECIMAL_SCALE)
        else:
            schema[name] = pl.Utf8
    return schema


def write_parquet(records: list[dict[str, Any]], destination: Path) -> EmitResult:
    """Write canonical records to Parquet and return the object-store URI."""
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not records:
        # An empty file is still a fact the reconciliation needs: "the client
        # sent nothing today" is different from "the client sent nothing yet".
        frame = pl.DataFrame(schema=_schema())
    else:
        normalised = [
            {
                k: (_as_decimal(v) if k in _DECIMAL_FIELDS else (str(v) if v is not None else None))
                for k, v in record.items()
            }
            for record in records
        ]
        frame = pl.DataFrame(normalised, schema=_schema(), strict=False)

    frame.write_parquet(destination)
    return EmitResult(path=destination, uri=f"fs://{destination.name}", row_count=frame.height)


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return to_decimal(str(value))
