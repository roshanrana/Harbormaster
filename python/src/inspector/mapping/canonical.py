"""The canonical record and the Tier 1 alias dictionary.

Every exchange and every client names its columns differently. A settlement
amount arrives as "Net Settlement Value", "Settle Amt", "Cash Amount (USD)",
"Proceeds", "NetMoney" or raw FIX tag 118. The reconciliation engine downstream
understands exactly one schema, so something upstream has to normalise. This is
that something.

Tier 1 is a dictionary lookup on a normalised header. It is deterministic, it
costs microseconds, and it resolves the large majority of real columns, because
the industry's vocabulary is smaller than it first appears. Tiers 2 and 3 exist
for the residue, not the bulk (ADR-004).

The alias lists below are drawn from the column conventions of clearing,
custody and exchange reports: ICE end-of-day, CME ClearPort, OCC position
files, Refinitiv/LSEG custody cash statements, Eurex clearing collateral
statements, DTCC-style settlement extracts, and standard FIX/FIXML tag names.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Domain(StrEnum):
    """What kind of general-ledger-relevant event a record represents."""

    TRADE = "TRADE"
    POSITION = "POSITION"
    CASH = "CASH"
    COLLATERAL = "COLLATERAL"
    UNKNOWN = "UNKNOWN"


class Tier(StrEnum):
    """How a field mapping was resolved. Mirrors ResolutionTier in the proto."""

    ALIAS = "ALIAS"
    LOCAL = "LOCAL"
    LLM = "LLM"
    HUMAN = "HUMAN"
    UNRESOLVED = "UNRESOLVED"


# The canonical schema. Order is the column order of the Parquet output.
CANONICAL_FIELDS: tuple[str, ...] = (
    "arrival_id",
    "source_system",
    "client_id",
    "account_id",
    "account_name",
    "trade_id",
    "instrument_id",
    "instrument_type",
    "trade_date",
    "value_date",
    "quantity",
    "trade_price",
    "settlement_price",
    "gross_amount",
    "net_amount",
    "market_value",
    "currency",
    "side",
    "domain",
)

# Fields the mapper is allowed to assign from source columns. The rest are
# populated by Harbormaster itself (arrival_id, client_id, value_date, domain)
# and must never be taken from a column, because a column claiming to be the
# value date is exactly the input this system exists to distrust.
MAPPABLE_FIELDS: frozenset[str] = frozenset(
    {
        "source_system",
        "account_id",
        "account_name",
        "trade_id",
        "instrument_id",
        "instrument_type",
        "trade_date",
        "quantity",
        "trade_price",
        "settlement_price",
        "gross_amount",
        "net_amount",
        "market_value",
        "currency",
        "side",
    }
)

# Economically material fields carry more weight in the confidence score: a
# mis-mapped net amount produces a wrong reconciliation, a mis-mapped trade id
# produces a findable one.
FIELD_WEIGHTS: dict[str, int] = {
    "quantity": 3,
    "trade_price": 3,
    "settlement_price": 3,
    "gross_amount": 3,
    "net_amount": 3,
    "market_value": 3,
    "account_id": 2,
    "instrument_id": 2,
    "trade_id": 2,
    "trade_date": 2,
    "currency": 2,
}
DEFAULT_FIELD_WEIGHT = 1

# Which canonical fields a domain actually requires. Scoring a cash statement
# against trade-specific fields would quarantine every cash file ever sent.
REQUIRED_BY_DOMAIN: dict[Domain, frozenset[str]] = {
    Domain.TRADE: frozenset(
        {
            "account_id",
            "instrument_id",
            "trade_date",
            "quantity",
            "trade_price",
            "net_amount",
            "currency",
        }
    ),
    Domain.POSITION: frozenset(
        {"account_id", "instrument_id", "quantity", "settlement_price", "market_value"}
    ),
    Domain.CASH: frozenset({"account_id", "net_amount", "currency"}),
    Domain.COLLATERAL: frozenset({"account_id", "instrument_id", "market_value", "currency"}),
    Domain.UNKNOWN: frozenset(),
}


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "source_system": (
        "source",
        "sourcesystem",
        "venue",
        "exchange",
        "market",
        "clearinghouse",
        "mic",
    ),
    "account_id": (
        "accountid",
        "account",
        "acctno",
        "acctnum",
        "accountnumber",
        "acctid",
        "accountno",
        "clientaccount",
        "custodyaccount",
        "safekeepingaccount",
        "portfolioid",
        "portfolio",
        "book",
        "bookid",
        "subaccount",
        "omnibusaccount",
        "clearingaccount",
        "acct",
    ),
    "account_name": (
        "accountname",
        "acctname",
        "portfolioname",
        "fundname",
        "clientname",
        "accounttitle",
        "safekeepingaccountname",
        "bookname",
    ),
    "trade_id": (
        "tradeid",
        "trdid",
        "dealid",
        "executionid",
        "execid",
        "orderid",
        "transactionid",
        "ticket",
        "ticketno",
        "ticketnumber",
        "referencenumber",
        "refno",
        "reference",
        "tradereference",
        "confirmationid",
        "clordid",
        "tradenumber",
    ),
    "instrument_id": (
        "instrument",
        "instrumentid",
        "symbol",
        "ticker",
        "isin",
        "cusip",
        "sedol",
        "figi",
        "securityid",
        "secid",
        "contractcode",
        "contract",
        "occsymbol",
        "productcode",
        "product",
        "underlying",
        "underlyingsymbol",
        "securitydescription",
        "description",
        "instrumentcode",
        "ric",
        "bbgticker",
    ),
    "instrument_type": (
        "instrumenttype",
        "assetclass",
        "producttype",
        "sectype",
        "securitytype",
        "cficode",
        "instrumentclass",
        "assettype",
        "contracttype",
    ),
    "trade_date": (
        "tradedate",
        "trddate",
        "dealdate",
        "executiondate",
        "transactiondate",
        "dateexecuted",
        "businessdate",
        "activitydate",
        "bookingdate",
        "asof",
        "asofdate",
        "date",
    ),
    "quantity": (
        "qty",
        "quantity",
        "lastqty",
        "filledqty",
        "shares",
        "units",
        "contracts",
        "numberofcontracts",
        "faceamount",
        "facevalue",
        "nominal",
        "nominalamount",
        "lotsize",
        "position",
        "netposition",
        "positionquantity",
        "openquantity",
        "balance",
        "holdings",
        "tradequantity",
        "settlementquantity",
    ),
    "trade_price": (
        "price",
        "tradeprice",
        "lastprice",
        "execprice",
        "executionprice",
        "fillprice",
        "dealprice",
        "avgprice",
        "averageprice",
        "executedprice",
        "lastpx",
        "avgpx",
        "pricetraded",
        "unitprice",
        "cleanprice",
        "grossprice",
    ),
    "settlement_price": (
        "settleprice",
        "settlementprice",
        "closeprice",
        "closingprice",
        "mtmprice",
        "marktomarketprice",
        "marktomarket",
        "officialsettlementprice",
        "officialprice",
        "dccprice",
        "eodprice",
        "priorsettleprice",
        "previoussettlementprice",
        "endofdayprice",
        "valuationprice",
        "markprice",
        "settlementpx",
    ),
    "gross_amount": (
        "grossamount",
        "grossamt",
        "grossvalue",
        "grossproceeds",
        "principal",
        "principalamount",
        "grosscash",
        "grossconsideration",
        "consideration",
    ),
    "net_amount": (
        "netamount",
        "netamt",
        "netmoney",
        "netcash",
        "proceeds",
        "netproceeds",
        "settlementamount",
        "settlementvalue",
        "settleamt",
        "settlementamt",
        "cashamount",
        "netsettlementvalue",
        "totalamount",
        "amountdue",
        "amount",
        "netconsideration",
        "cashvalue",
        "movementamount",
        "debitcredit",
    ),
    "market_value": (
        "marketvalue",
        "mktval",
        "mktvalue",
        "mv",
        "currentmarketvalue",
        "fairvalue",
        "notionalvalue",
        "notional",
        "valuation",
        "positionvalue",
        "collateralvalue",
        "marketvalueinbase",
        "basemarketvalue",
    ),
    "currency": (
        "currency",
        "ccy",
        "curr",
        "cur",
        "settlementcurrency",
        "settleccy",
        "tradecurrency",
        "tradeccy",
        "currencycode",
        "isocurrency",
        "denomination",
    ),
    "side": (
        "side",
        "buysell",
        "buyorsell",
        "direction",
        "action",
        "longshort",
        "transactiontype",
        "dealtype",
        "bs",
        "sidecode",
    ),
}

# Units and qualifiers that appear in headers but carry no mapping signal.
# "Market Value (USD)" and "Market Value" are the same column.
_NOISE_TOKENS = (
    "usd",
    "eur",
    "gbp",
    "jpy",
    "chf",
    "hkd",
    "local",
    "base",
    "reporting",
    "inbase",
    "inlocal",
    "amt",
    "value1",
    "col",
)


def normalize_header(raw: str) -> str:
    """Reduce a header to comparable form.

    ``"Net Settlement Value ($)"``, ``"net_settlement_value"`` and
    ``"NET-SETTLEMENT-VALUE"`` all normalise to ``netsettlementvalue``.
    """
    return "".join(ch for ch in raw.lower() if ch.isalnum())


def strip_noise(normalized: str) -> str:
    """Remove trailing currency and unit qualifiers from a normalised header."""
    out = normalized
    for token in _NOISE_TOKENS:
        if out.endswith(token) and len(out) > len(token) + 2:
            out = out[: -len(token)]
    return out


_ALIAS_INDEX: dict[str, str] = {}
for _canonical, _aliases in FIELD_ALIASES.items():
    _ALIAS_INDEX[_canonical] = _canonical
    _ALIAS_INDEX[normalize_header(_canonical)] = _canonical
    for _alias in _aliases:
        if _alias in _ALIAS_INDEX and _ALIAS_INDEX[_alias] != _canonical:
            raise ValueError(  # pragma: no cover - guards a dictionary edit mistake
                f"alias {_alias!r} maps to both {_ALIAS_INDEX[_alias]!r} and {_canonical!r}"
            )
        _ALIAS_INDEX[_alias] = _canonical


def alias_lookup(raw_header: str) -> str | None:
    """Tier 1 resolution. Returns a canonical field name, or None."""
    normalized = normalize_header(raw_header)
    hit = _ALIAS_INDEX.get(normalized)
    if hit is not None:
        return hit
    return _ALIAS_INDEX.get(strip_noise(normalized))


def alias_count() -> int:
    """Size of the dictionary. Used by tests and the ship report."""
    return len(_ALIAS_INDEX)


@dataclass(slots=True)
class CanonicalRecord:
    """One normalised row, ready for the reconciliation engine.

    Money and quantities are ``Decimal``, never ``float``. A float64 net amount
    eventually produces a one-cent break that costs an analyst an afternoon and
    convinces them the tool is unreliable.
    """

    arrival_id: str
    source_system: str | None = None
    client_id: str | None = None
    account_id: str | None = None
    account_name: str | None = None
    trade_id: str | None = None
    instrument_id: str | None = None
    instrument_type: str | None = None
    trade_date: str | None = None
    value_date: str | None = None
    quantity: Decimal | None = None
    trade_price: Decimal | None = None
    settlement_price: Decimal | None = None
    gross_amount: Decimal | None = None
    net_amount: Decimal | None = None
    market_value: Decimal | None = None
    currency: str | None = None
    side: str | None = None
    domain: str = Domain.UNKNOWN
