"""The recon stub's contract, and its deliberate lack of intelligence."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from reconstub.main import reconcile


def row(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "account_id": "8842-00119",
        "instrument_id": "ESZ6",
        "trade_id": "T1",
        "quantity": Decimal("10"),
        "trade_price": Decimal("5401.25"),
        "settlement_price": Decimal("5399.50"),
        "net_amount": Decimal("54012.50"),
        "currency": "USD",
    }
    base.update(kw)
    return base


def test_identical_sides_produce_no_breaks() -> None:
    assert reconcile([row()], [row()]) == []


def test_missing_row_on_each_side_is_reported() -> None:
    breaks = reconcile([row(trade_id="T1")], [row(trade_id="T2")])
    kinds = {b.kind for b in breaks}
    assert kinds == {"MISSING_SIDE_1", "MISSING_SIDE_2"}


def test_value_mismatch_names_the_field() -> None:
    breaks = reconcile([row()], [row(quantity=Decimal("11"))])
    assert len(breaks) == 1
    assert breaks[0].kind == "VALUE_MISMATCH"
    assert breaks[0].field_name == "quantity"
    assert breaks[0].side_1_value == "10"
    assert breaks[0].side_2_value == "11"


def test_rounding_within_tolerance_is_not_a_break() -> None:
    assert (
        reconcile([row(net_amount=Decimal("54012.50"))], [row(net_amount=Decimal("54012.505"))])
        == []
    )


def test_null_is_not_treated_as_zero() -> None:
    # The distinction ADR-006 exists to preserve. If a missing settlement
    # price silently became 0.00, every row would break.
    breaks = reconcile([row(settlement_price=None)], [row(settlement_price=None)])
    assert breaks == []
    breaks = reconcile([row(settlement_price=None)], [row(settlement_price=Decimal("0"))])
    assert len(breaks) == 1


def test_swapped_prices_produce_visible_breaks() -> None:
    # If Harbormaster mapped trade and settlement prices the wrong way round,
    # this is what the operator sees. The engine cannot detect the cause; it
    # only reports that the numbers disagree.
    side_1 = [row()]
    side_2 = [row(trade_price=Decimal("5399.50"), settlement_price=Decimal("5401.25"))]
    breaks = reconcile(side_1, side_2)
    assert {b.field_name for b in breaks} == {"trade_price", "settlement_price"}


def test_currency_difference_is_a_break() -> None:
    breaks = reconcile([row(currency="USD")], [row(currency="EUR")])
    assert breaks[0].field_name == "currency"


def test_join_is_on_account_instrument_and_trade() -> None:
    # Same trade id under a different account is a different record.
    breaks = reconcile([row(account_id="A")], [row(account_id="B")])
    assert len(breaks) == 2
    assert {b.kind for b in breaks} == {"MISSING_SIDE_1", "MISSING_SIDE_2"}
