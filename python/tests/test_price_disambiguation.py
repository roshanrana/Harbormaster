"""Trade price versus settlement price.

The failure this guards against is silent: if the two are swapped, the
reconciliation still runs, still produces a number, and is wrong.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from inspector.mapping import canonical as c
from inspector.mapping.tier1 import Tier1Mapper, cross_check_amount, to_decimal
from inspector.parsers.base import ParsedTable


def table(headers: list[str], rows: list[list[str]]) -> ParsedTable:
    return ParsedTable(headers=headers, rows=[dict(zip(headers, r, strict=True)) for r in rows])


def mapped(t: ParsedTable, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """canonical field -> source column."""
    return {
        m.canonical_field: m.source_field
        for m in Tier1Mapper(overrides).map_table(t)
        if m.canonical_field
    }


def test_named_price_columns_resolve_by_vocabulary() -> None:
    t = table(
        ["TradeID", "Symbol", "Qty", "Exec Price", "Settlement Price"],
        [["T1", "ESZ6", "10", "5401.25", "5399.50"]],
    )
    got = mapped(t)
    assert got["trade_price"] == "Exec Price"
    assert got["settlement_price"] == "Settlement Price"


def test_four_price_columns_resolve_the_two_that_matter() -> None:
    # A cleared-futures extract routinely carries this many.
    t = table(
        [
            "Symbol",
            "Qty",
            "Traded Price",
            "Prior Settle Price",
            "Official Settlement Price",
            "Mark Price",
        ],
        [["ESZ6", "10", "5401.25", "5390.00", "5399.50", "5399.50"]],
    )
    mappings = Tier1Mapper().map_table(t)
    got = {m.canonical_field: m.source_field for m in mappings if m.canonical_field}
    assert got["trade_price"] == "Traded Price"
    # Both a prior and an official settlement price are present; the current
    # one wins and the historical one is explicitly left unassigned.
    assert got["settlement_price"] == "Official Settlement Price"
    # The surplus price columns are left unresolved rather than guessed at.
    unresolved = [m for m in mappings if m.canonical_field is None]
    assert len(unresolved) >= 1
    assert all(m.evidence for m in unresolved)


def test_bare_price_column_resolved_by_structure() -> None:
    # Only "Price" and "Settle" are offered; "Price" varies per execution
    # while the settlement value repeats for the instrument. Structure, not
    # string similarity, is what separates them.
    rows = [
        ["ESZ6", "10", "5401.25", "5399.50"],
        ["ESZ6", "5", "5402.75", "5399.50"],
        ["ESZ6", "8", "5400.00", "5399.50"],
        ["NQZ6", "3", "19850.25", "19845.00"],
        ["NQZ6", "7", "19851.75", "19845.00"],
    ]
    t = table(["Symbol", "Qty", "Price", "Px"], rows)
    got = mapped(t)
    assert got["trade_price"] == "Price"
    assert got["settlement_price"] == "Px"


def test_structural_resolution_records_its_reasoning() -> None:
    rows = [
        ["ESZ6", "5401.25", "5399.50"],
        ["ESZ6", "5402.75", "5399.50"],
        ["ESZ6", "5400.00", "5399.50"],
    ]
    t = table(["Symbol", "Price", "Px"], rows)
    mappings = {m.canonical_field: m for m in Tier1Mapper().map_table(t) if m.canonical_field}
    assert mappings["settlement_price"].tier == c.Tier.LOCAL
    assert "constant" in mappings["settlement_price"].evidence
    assert "varies" in mappings["trade_price"].evidence


def test_client_override_beats_the_dictionary() -> None:
    t = table(["Px_Sett", "Px_Last", "Qty"], [["5399.50", "5401.25", "10"]])
    got = mapped(t, {"Px_Sett": "settlement_price", "Px_Last": "trade_price"})
    assert got["settlement_price"] == "Px_Sett"
    assert got["trade_price"] == "Px_Last"


def test_duplicate_claim_is_surfaced_not_silently_resolved() -> None:
    # Two columns both alias to quantity. Picking by column order would be
    # arbitrary, so neither is trusted.
    t = table(["Qty", "Quantity", "Price"], [["10", "10", "42.5"]])
    mappings = Tier1Mapper().map_table(t)
    unresolved = [m for m in mappings if m.canonical_field is None]
    assert any("conflicts" in m.evidence for m in unresolved)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,234.56", Decimal("1234.56")),
        ("$1,234.56", Decimal("1234.56")),
        ("(1,234.56)", Decimal("-1234.56")),
        ("1234.56-", Decimal("-1234.56")),
        ("  42  ", Decimal("42")),
        ("", None),
        ("n/a", None),
        ("not a number", None),
    ],
)
def test_amount_parsing_handles_real_conventions(raw: str, expected: Decimal | None) -> None:
    assert to_decimal(raw) == expected


def test_arithmetic_cross_check_confirms_a_correct_mapping() -> None:
    t = table(
        ["Symbol", "Qty", "Exec Price", "Settlement Price", "Net Amount"],
        [
            ["ESZ6", "10", "100.00", "99.00", "1000.00"],
            ["ESZ6", "5", "100.00", "99.00", "500.00"],
        ],
    )
    ok, evidence = cross_check_amount(t, Tier1Mapper().map_table(t))
    assert ok is True
    assert "2/2" in evidence


def test_arithmetic_cross_check_flags_a_swapped_mapping() -> None:
    # Here the amounts reconcile against the settlement price, not the trade
    # price, which is the signature of the two having been swapped.
    t = table(
        ["Symbol", "Qty", "Exec Price", "Settlement Price", "Net Amount"],
        [
            ["ESZ6", "10", "500.00", "99.00", "990.00"],
            ["ESZ6", "5", "500.00", "99.00", "495.00"],
        ],
    )
    ok, _ = cross_check_amount(t, Tier1Mapper().map_table(t))
    assert ok is False


def test_cross_check_is_inconclusive_without_the_needed_columns() -> None:
    t = table(["Symbol", "Exec Price"], [["ESZ6", "100.00"]])
    ok, evidence = cross_check_amount(t, Tier1Mapper().map_table(t))
    assert ok is None
    assert "insufficient" in evidence


def test_cross_check_tolerates_commission() -> None:
    # quantity x price rarely equals the booked amount exactly; fees and
    # contract multipliers legitimately intervene.
    t = table(
        ["Symbol", "Qty", "Exec Price", "Net Amount"],
        [["ESZ6", "10", "100.00", "1002.50"], ["ESZ6", "10", "100.00", "1003.10"]],
    )
    ok, _ = cross_check_amount(t, Tier1Mapper().map_table(t))
    assert ok is True
