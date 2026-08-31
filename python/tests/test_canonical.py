"""Tier 1 alias dictionary behaviour."""

from __future__ import annotations

import pytest

from inspector.mapping import canonical as c


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        # Header cosmetics must not matter.
        ("Net Settlement Value", "net_amount"),
        ("net_settlement_value", "net_amount"),
        ("NET-SETTLEMENT-VALUE", "net_amount"),
        ("  Net  Settlement  Value  ", "net_amount"),
        # Real venue and custody vocabulary.
        ("Settle Amt", "net_amount"),
        ("NetMoney", "net_amount"),
        ("Proceeds", "net_amount"),
        ("LastPx", "trade_price"),
        ("Exec Price", "trade_price"),
        ("Official Settlement Price", "settlement_price"),
        ("MTM Price", "settlement_price"),
        ("Prior Settle Price", "settlement_price"),
        ("Number of Contracts", "quantity"),
        ("Face Amount", "quantity"),
        ("Safekeeping Account", "account_id"),
        ("ISIN", "instrument_id"),
        ("OCC Symbol", "instrument_id"),
        ("CCY", "currency"),
        ("Buy/Sell", "side"),
    ],
)
def test_alias_resolution(header: str, expected: str) -> None:
    assert c.alias_lookup(header) == expected


@pytest.mark.parametrize(
    "header", ["Market Value (USD)", "Market Value USD", "MarketValueInBase", "market_value_base"]
)
def test_currency_and_unit_qualifiers_are_stripped(header: str) -> None:
    # "Market Value (USD)" and "Market Value" are the same column.
    assert c.alias_lookup(header) == "market_value"


def test_trade_and_settlement_prices_never_collide() -> None:
    # The distinction the whole mapping layer exists to protect.
    trade = {"Price", "Trade Price", "Exec Price", "Fill Price", "LastPx", "Avg Price"}
    settle = {"Settle Price", "Settlement Price", "Close Price", "MTM Price", "EOD Price"}
    assert all(c.alias_lookup(h) == "trade_price" for h in trade)
    assert all(c.alias_lookup(h) == "settlement_price" for h in settle)
    assert not (trade & settle)


def test_unknown_headers_return_none_rather_than_guessing() -> None:
    # Escalation to Tier 2 depends on Tier 1 admitting it does not know.
    for header in ["Zorblat", "Widget Factor 7", "xyzzy", ""]:
        assert c.alias_lookup(header) is None


def test_dictionary_has_no_conflicting_aliases() -> None:
    # Import-time guard; this asserts it stayed true.
    assert c.alias_count() > 200


def test_value_date_is_not_mappable_from_a_column() -> None:
    # A column claiming to be the value date is precisely the input this system
    # exists to distrust, so the mapper is not allowed to assign it.
    assert "value_date" not in c.MAPPABLE_FIELDS
    assert "client_id" not in c.MAPPABLE_FIELDS
    assert "value_date" in c.CANONICAL_FIELDS


def test_material_fields_outweigh_identifiers() -> None:
    assert c.FIELD_WEIGHTS["net_amount"] > c.FIELD_WEIGHTS["trade_id"]
    assert c.FIELD_WEIGHTS["settlement_price"] > c.DEFAULT_FIELD_WEIGHT


def test_required_fields_differ_by_domain() -> None:
    # Scoring a cash statement against trade fields would quarantine every
    # cash file ever sent.
    assert "trade_price" in c.REQUIRED_BY_DOMAIN[c.Domain.TRADE]
    assert "trade_price" not in c.REQUIRED_BY_DOMAIN[c.Domain.CASH]
    assert "market_value" in c.REQUIRED_BY_DOMAIN[c.Domain.POSITION]
