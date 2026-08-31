"""Resolving source columns onto the canonical schema.

Tier 1 (this module) is the deterministic dictionary pass plus the structural
reasoning needed to separate columns that the dictionary alone cannot. Tiers 2
and 3 attach at the seams left here.

The interesting problem is prices. A cleared-futures extract routinely carries
four or more price-like columns — traded price, prior settlement, current
settlement, and a mark — and the reconciliation is wrong in a way nobody
notices if trade price and settlement price are swapped. Header text resolves
most of them. What resolves the rest is structure: a settlement price is a
property of an instrument on a day, so it repeats across every row sharing that
instrument, while a trade price is a property of an execution and varies. That
observation is worth more than any amount of string similarity, and it is
checked here before anything escalates to a model.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from inspector.mapping import canonical as c
from inspector.parsers.base import ParsedTable

# Header fragments that decide a price column outright.
_SETTLEMENT_TOKENS = (
    "settle",
    "sett",
    "close",
    "closing",
    "mtm",
    "marktomarket",
    "official",
    "eod",
    "dcc",
    "valuation",
    "mark",
)
_TRADE_TOKENS = ("exec", "fill", "deal", "traded", "tradeprice", "last", "avg", "average")

_PRICE_HINT = re.compile(r"(price|px|rate|quote)", re.IGNORECASE)

_NUMERIC_CLEAN = re.compile(r"[,\s$€£¥%]")


@dataclass(slots=True)
class Mapping:
    """One resolved column, with the evidence that resolved it."""

    source_field: str
    canonical_field: str | None
    tier: c.Tier
    confidence: float
    evidence: str


def to_decimal(raw: str) -> Decimal | None:
    """Parse a monetary or quantity cell.

    Handles thousands separators, currency symbols, and the accounting
    convention where negatives are parenthesised. Returns None rather than
    raising: an unparseable cell is data to be flagged, not a crash.
    """
    text = raw.strip() if raw else ""
    if not text or text in {"-", "--", "n/a", "N/A", "NULL", "null"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = _NUMERIC_CLEAN.sub("", text)
    if text.endswith("-"):  # trailing-minus convention from mainframe extracts
        text, negative = text[:-1], True
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return -value if negative else value


def _norm(header: str) -> str:
    return c.normalize_header(header)


def _has(header: str, tokens: tuple[str, ...]) -> bool:
    n = _norm(header)
    return any(t in n for t in tokens)


def looks_like_price_column(header: str, values: list[str]) -> bool:
    """A column is price-like if its name suggests it and its values are numeric."""
    if not _PRICE_HINT.search(header):
        return False
    parsed = [to_decimal(v) for v in values[:200] if v.strip()]
    usable = [p for p in parsed if p is not None]
    return bool(usable) and len(usable) >= max(1, int(0.8 * len(parsed)))


def variation_ratio(values: list[str], group_by: list[str] | None) -> float:
    """How much a column varies within groups sharing the same instrument.

    Returns 0.0 when the column is constant within every group (the signature
    of a settlement price) and approaches 1.0 when it varies per row (the
    signature of a trade price). With no grouping column available, falls back
    to overall distinctness.
    """
    cleaned = [v.strip() for v in values]
    if not cleaned:
        return 0.0
    if not group_by or len(group_by) != len(cleaned):
        distinct = len({v for v in cleaned if v})
        non_empty = sum(1 for v in cleaned if v)
        return distinct / non_empty if non_empty else 0.0

    groups: dict[str, set[str]] = defaultdict(set)
    sizes: dict[str, int] = defaultdict(int)
    for key, value in zip(group_by, cleaned, strict=True):
        if not value:
            continue
        groups[key].add(value)
        sizes[key] += 1

    # Only groups with more than one row carry information about variation.
    informative = [(k, v) for k, v in groups.items() if sizes[k] > 1]
    if not informative:
        distinct = len({v for v in cleaned if v})
        non_empty = sum(1 for v in cleaned if v)
        return distinct / non_empty if non_empty else 0.0

    varying = sum(1 for _, values_in_group in informative if len(values_in_group) > 1)
    return varying / len(informative)


class Tier1Mapper:
    """Deterministic mapping: alias dictionary, client overrides, structure."""

    def __init__(self, field_overrides: dict[str, str] | None = None) -> None:
        # Client-specific overrides beat the global dictionary: a client that
        # calls its settlement price "Px_Sett" has told us so in configuration,
        # and configuration outranks inference (FR-28 promotion target).
        self.field_overrides = {_norm(k): v for k, v in (field_overrides or {}).items()}

    def map_table(self, table: ParsedTable) -> list[Mapping]:
        """Resolve every column, returning one Mapping per source column."""
        mappings: list[Mapping] = []
        claimed: set[str] = set()
        deferred_prices: list[str] = []

        for header in table.headers:
            override = self.field_overrides.get(_norm(header))
            if override:
                mappings.append(
                    Mapping(header, override, c.Tier.HUMAN, 1.0, f"client override -> {override}")
                )
                claimed.add(override)
                continue

            hit = c.alias_lookup(header)
            if hit in {"trade_price", "settlement_price"}:
                # Defer every price column until all are known: deciding them
                # one at a time is how two columns both become trade_price.
                deferred_prices.append(header)
                continue
            if hit and hit in c.MAPPABLE_FIELDS and hit not in claimed:
                mappings.append(Mapping(header, hit, c.Tier.ALIAS, 1.0, f"alias:{_norm(header)}"))
                claimed.add(hit)
                continue
            if hit and hit in claimed:
                # Two columns claim the same canonical field. Neither is
                # trusted; the ambiguity is surfaced rather than resolved by
                # column order, which would be arbitrary.
                mappings.append(
                    Mapping(
                        header,
                        None,
                        c.Tier.UNRESOLVED,
                        0.0,
                        f"conflicts with an earlier column already mapped to {hit}",
                    )
                )
                continue

            if looks_like_price_column(header, table.column(header)):
                deferred_prices.append(header)
                continue

            mappings.append(Mapping(header, None, c.Tier.UNRESOLVED, 0.0, "no alias match"))

        mappings.extend(self._resolve_prices(table, deferred_prices, mappings))
        return self._in_source_order(table.headers, mappings)

    def _resolve_prices(
        self, table: ParsedTable, headers: list[str], settled: list[Mapping]
    ) -> list[Mapping]:
        """Assign trade_price and settlement_price among the price candidates.

        Runs in three passes: header vocabulary, then structural variation for
        anything the vocabulary could not decide, then explicit non-assignment
        for surplus columns. Surplus is the common case in cleared-futures
        extracts and must not be guessed at: silently promoting a prior
        settlement to the current mark is a wrong answer that looks right.
        """
        if not headers:
            return []

        instrument_col = next(
            (m.source_field for m in settled if m.canonical_field == "instrument_id"), None
        )
        group_by = table.column(instrument_col) if instrument_col else None

        settlement_candidates: list[tuple[str, float]] = []
        trade_candidates: list[tuple[str, float]] = []
        undecided: list[str] = []

        for header in headers:
            settlement = _has(header, _SETTLEMENT_TOKENS)
            trade = _has(header, _TRADE_TOKENS)
            if settlement and not trade:
                settlement_candidates.append((header, _settlement_preference(header)))
            elif trade and not settlement:
                trade_candidates.append((header, _trade_preference(header)))
            else:
                undecided.append(header)

        results: list[Mapping] = []
        taken: set[str] = set()

        for candidates, field, reason in (
            (settlement_candidates, "settlement_price", "header names a settlement or mark price"),
            (trade_candidates, "trade_price", "header names an execution price"),
        ):
            if not candidates:
                continue
            candidates.sort(key=lambda pair: pair[1], reverse=True)
            winner, _ = candidates[0]
            results.append(Mapping(winner, field, c.Tier.ALIAS, 0.98, reason))
            taken.add(field)
            for surplus, _ in candidates[1:]:
                results.append(
                    Mapping(
                        surplus,
                        None,
                        c.Tier.UNRESOLVED,
                        0.0,
                        f"also names a {field.replace('_', ' ')}; "
                        f"{winner!r} is the stronger match for this file",
                    )
                )

        # Structure. A settlement price is a property of an instrument on a day
        # and repeats across rows; a trade price is a property of an execution
        # and varies. This is what resolves a column labelled only "Price".
        scored = [(h, variation_ratio(table.column(h), group_by)) for h in undecided]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        for header, ratio in scored:
            basis = "within instrument groups" if group_by else "across all rows"
            if "trade_price" not in taken and ratio >= 0.5:
                results.append(
                    Mapping(
                        header,
                        "trade_price",
                        c.Tier.LOCAL,
                        _price_conf(ratio),
                        f"varies per row {basis} (ratio {ratio:.2f})",
                    )
                )
                taken.add("trade_price")
            elif "settlement_price" not in taken and ratio < 0.5:
                results.append(
                    Mapping(
                        header,
                        "settlement_price",
                        c.Tier.LOCAL,
                        _price_conf(1 - ratio),
                        f"constant {basis} (ratio {ratio:.2f})",
                    )
                )
                taken.add("settlement_price")
            else:
                results.append(
                    Mapping(
                        header,
                        None,
                        c.Tier.UNRESOLVED,
                        0.0,
                        f"additional price column, roles already assigned (ratio {ratio:.2f})",
                    )
                )
        return results

    def _in_source_order(self, headers: list[str], mappings: list[Mapping]) -> list[Mapping]:
        by_source = {m.source_field: m for m in mappings}
        return [by_source[h] for h in headers if h in by_source]


def _settlement_preference(header: str) -> float:
    """Rank competing settlement-price columns.

    A file carrying both a prior and an official settlement price means the
    current one, so historical qualifiers are demoted rather than treated as
    equivalent.
    """
    n = _norm(header)
    score = 1.0
    if "official" in n:
        score += 0.5
    if "settlement" in n or "settle" in n:
        score += 0.3
    if any(q in n for q in ("prior", "previous", "yesterday", "prev", "open")):
        score -= 0.8
    return score


def _trade_preference(header: str) -> float:
    """Rank competing trade-price columns; an explicit execution price wins."""
    n = _norm(header)
    score = 1.0
    if any(q in n for q in ("exec", "fill", "traded", "tradeprice")):
        score += 0.5
    if "avg" in n or "average" in n:
        score -= 0.2
    return score


def _price_conf(strength: float) -> float:
    """Structural evidence is good but not certain; cap it below alias level."""
    return round(min(0.55 + 0.35 * strength, 0.90), 3)


def cross_check_amount(table: ParsedTable, mappings: list[Mapping]) -> tuple[bool | None, str]:
    """Verify quantity x trade_price is consistent with the net amount.

    This is the arithmetic tie-break from LLD 5.3. It cannot prove a mapping
    correct, but it catches the case where trade and settlement prices were
    swapped, because only one of them reconciles against the booked amount.
    """
    by_field = {m.canonical_field: m.source_field for m in mappings if m.canonical_field}
    qty_col, price_col, amount_col = (
        by_field.get("quantity"),
        by_field.get("trade_price"),
        by_field.get("net_amount") or by_field.get("gross_amount"),
    )
    if not (qty_col and price_col and amount_col):
        return None, "insufficient columns for an arithmetic cross-check"

    agree = 0
    checked = 0
    for row in table.rows[:200]:
        qty, price, amount = (
            to_decimal(row.get(qty_col, "")),
            to_decimal(row.get(price_col, "")),
            to_decimal(row.get(amount_col, "")),
        )
        if qty is None or price is None or amount is None or amount == 0:
            continue
        checked += 1
        expected = abs(qty * price)
        # Tolerance absorbs fees, commissions and contract multipliers, which
        # are legitimately absent from a bare quantity-times-price product.
        if abs(expected - abs(amount)) <= abs(amount) * Decimal("0.05"):
            agree += 1
    if checked == 0:
        return None, "no rows had all three values populated"
    ratio = agree / checked
    return ratio >= 0.8, f"quantity x price reconciles to amount on {agree}/{checked} rows"
