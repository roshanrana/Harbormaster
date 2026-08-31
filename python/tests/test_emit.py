"""Canonical output: typed, decimal, and null-preserving."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from inspector import emit
from inspector.mapping import canonical as c
from inspector.mapping.tier1 import Mapping
from inspector.parsers.base import ParsedTable


def table() -> ParsedTable:
    headers = [
        "Account ID",
        "Symbol",
        "TradeID",
        "Qty",
        "Exec Price",
        "Settle Price",
        "Net Amount",
        "CCY",
        "B/S",
    ]
    rows = [
        dict(
            zip(
                headers,
                ["8842-00119", "ESZ6", "T1", "10", "5401.25", "5399.50", "54012.50", "USD", "B"],
                strict=True,
            )
        ),
        dict(
            zip(
                headers,
                ["8842-00119", "ESZ6", "T2", "-5", "5402.75", "5399.50", "(27013.75)", "USD", "S"],
                strict=True,
            )
        ),
    ]
    return ParsedTable(headers=headers, rows=rows)


def mappings() -> list[Mapping]:
    pairs = {
        "Account ID": "account_id",
        "Symbol": "instrument_id",
        "TradeID": "trade_id",
        "Qty": "quantity",
        "Exec Price": "trade_price",
        "Settle Price": "settlement_price",
        "Net Amount": "net_amount",
        "CCY": "currency",
        "B/S": "side",
    }
    return [Mapping(s, f, c.Tier.ALIAS, 1.0, "alias") for s, f in pairs.items()]


def records() -> list[dict[str, object]]:
    return emit.build_records(
        table=table(),
        mappings=mappings(),
        arrival_id="arr-1",
        client_id="CLNT004",
        value_date="2026-08-28",
        domain="TRADE",
        source_system="CME",
        account_names={"8842-00119": "Meridian Global Macro"},
    )


def test_harbormaster_determined_fields_are_stamped_not_read() -> None:
    for r in records():
        assert r["client_id"] == "CLNT004"
        assert r["value_date"] == "2026-08-28"
        assert r["domain"] == "TRADE"
        assert r["arrival_id"] == "arr-1"


def test_amounts_become_decimals_not_floats() -> None:
    r = records()[0]
    assert isinstance(r["net_amount"], Decimal)
    assert r["net_amount"] == Decimal("54012.50")
    assert not isinstance(r["net_amount"], float)


def test_accounting_negatives_are_parsed() -> None:
    r = records()[1]
    assert r["net_amount"] == Decimal("-27013.75")
    assert r["quantity"] == Decimal("-5")


def test_side_is_normalised() -> None:
    assert records()[0]["side"] == "BUY"
    assert records()[1]["side"] == "SELL"


def test_account_name_is_filled_from_the_registry() -> None:
    assert records()[0]["account_name"] == "Meridian Global Macro"


def test_unmapped_field_is_null_not_empty_string() -> None:
    # market_value was never mapped. It must be null, so the recon engine can
    # tell "not provided" from "provided as blank".
    assert records()[0]["market_value"] is None


def test_parquet_round_trip_preserves_decimals(tmp_path: Path) -> None:
    result = emit.write_parquet(records(), tmp_path / "out.parquet")
    assert result.row_count == 2
    frame = pl.read_parquet(result.path)
    assert isinstance(frame.schema["net_amount"], pl.Decimal)
    values = frame["net_amount"].to_list()
    assert values[0] == Decimal("54012.50")
    assert values[1] == Decimal("-27013.75")


def test_null_survives_the_round_trip(tmp_path: Path) -> None:
    # The distinction ADR-006 exists to protect: a missing settlement price
    # must not arrive downstream as 0.00.
    result = emit.write_parquet(records(), tmp_path / "out.parquet")
    frame = pl.read_parquet(result.path)
    assert frame["market_value"].to_list() == [None, None]
    assert frame["market_value"].null_count() == 2


def test_schema_matches_the_canonical_field_order(tmp_path: Path) -> None:
    result = emit.write_parquet(records(), tmp_path / "out.parquet")
    assert pl.read_parquet(result.path).columns == list(c.CANONICAL_FIELDS)


def test_empty_file_still_writes_a_valid_parquet(tmp_path: Path) -> None:
    # "The client sent nothing today" is a different fact from "the client has
    # not sent anything yet", and the reconciliation needs the first one.
    result = emit.write_parquet([], tmp_path / "empty.parquet")
    assert result.row_count == 0
    frame = pl.read_parquet(result.path)
    assert frame.columns == list(c.CANONICAL_FIELDS)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("B", "BUY"),
        ("buy", "BUY"),
        ("S", "SELL"),
        ("sold", "SELL"),
        ("1", "BUY"),
        ("2", "SELL"),
        ("Long", "LONG"),
        ("", None),
        ("XX", "XX"),
    ],
)
def test_side_normalisation_table(raw: str, expected: str | None) -> None:
    assert emit.normalise_side(raw) == expected
