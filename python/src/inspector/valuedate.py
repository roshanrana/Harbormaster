"""Determining what business day a file's contents actually represent.

This is the problem the project exists for. A file named
``MCP_TRD_20260831.csv`` landing at 06:40 on the 31st routinely contains the
28th's business, because the client's batch ran late. Reconciling its contents
against the 31st's ledger produces a break on every row, and an analyst then
spends a morning discovering that nothing was wrong except the date.

Three independent sources are consulted, and they are ranked by how much they
actually know:

1. **Content, explicit.** A settlement or value date column. The client's own
   system stated what these records settle on. Strongest evidence available.
2. **Content, inferred.** No value-date column, but a trade date column plus a
   known settlement convention. Weaker, because the convention is our
   assumption rather than their statement.
3. **Filename.** Convenient and frequently wrong. Used only when the content
   is silent.
4. **Arrival time.** Last resort, and barely evidence at all.

Where the filename and the content disagree, the content wins and the
disagreement is *always* flagged (FR-12). It is never silently resolved: a
recurring mismatch means the client's batch schedule has drifted, and someone
should find out from an operations screen rather than from a break report six
weeks later.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from inspector.registry import Calendar

# Method labels, carried into the proto message and the audit record.
METHOD_CONTENT_EXPLICIT = "CONTENT_EXPLICIT"
METHOD_CONTENT_INFERRED = "CONTENT_INFERRED"
METHOD_FILENAME = "FILENAME"
METHOD_ARRIVAL = "ARRIVAL_MINUS_CALENDAR"
METHOD_LLM = "LLM_ADJUDICATED"
METHOD_HUMAN = "HUMAN"

CONF_CONTENT_EXPLICIT = 0.97
CONF_CONTENT_INFERRED = 0.85
CONF_FILENAME = 0.70
CONF_ARRIVAL = 0.55

# Penalty applied when a date had to be rolled onto a business day. The file
# claimed a day the market was shut, so something upstream is already wrong.
ROLL_PENALTY = 0.10

# Date formats seen in real extracts, most specific first.
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%b-%Y",
    "%d%b%Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%Y%m%d",
    "%d.%m.%Y",
)

# Compact date embedded in a filename: 20260831, 2026-08-31, 31AUG2026.
_FILENAME_DATE = re.compile(
    r"(?P<iso>\d{4}-\d{2}-\d{2})|(?P<compact>(?<!\d)\d{8}(?!\d))|(?P<dmy>\d{2}[A-Za-z]{3}\d{4})"
)


@dataclass(slots=True)
class Resolution:
    """The resolved value date and everything that informed it."""

    resolved: date | None
    method: str
    confidence: float
    from_filename: date | None = None
    from_content: list[date] = field(default_factory=list)
    from_arrival: date | None = None
    mismatch_flagged: bool = False
    calendar_id: str = ""
    notes: str = ""

    @property
    def resolved_iso(self) -> str:
        return self.resolved.isoformat() if self.resolved else ""


def parse_date(text: str) -> date | None:
    """Parse a date cell in any of the formats real extracts use.

    Ambiguity between ``%d/%m/%Y`` and ``%m/%d/%Y`` is resolved by trying
    day-first before month-first, then rejecting anything impossible. A value
    that parses under both is genuinely ambiguous and the caller sees it as
    whichever the ordering chose; the disagreement surfaces later when the two
    interpretations imply different business days.
    """
    raw = text.strip()
    if not raw:
        return None
    # Trim a time component: "2026-08-28 17:30:00" and "2026-08-28T17:30:00Z".
    raw = re.split(r"[T ]", raw, maxsplit=1)[0].strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
        # Guard against a quantity or price being read as a compact date.
        if 1990 <= parsed.year <= 2100:
            return parsed
    return None


def date_from_filename(name: str) -> date | None:
    """Extract a date from a filename, if one is present."""
    m = _FILENAME_DATE.search(name)
    if not m:
        return None
    for group in ("iso", "compact", "dmy"):
        text = m.group(group)
        if text:
            return parse_date(text)
    return None


def find_value_date_column(headers: list[str], hints: list[str]) -> str | None:
    """Locate the column carrying the value or settlement date.

    Client-configured hints are tried first, because a client that has told us
    what their column is called outranks any general pattern.
    """
    normalized = {_norm(h): h for h in headers}
    for hint in hints:
        hit = normalized.get(_norm(hint))
        if hit:
            return hit
    for pattern in (
        "valuedate",
        "valdate",
        "settlementdate",
        "settledate",
        "settldate",
        "settlmntdate",
        "cashsettlementdate",
        "effectivedate",
        "posteddate",
        "postingdate",
        "valuedt",
        "settldt",
    ):
        hit = normalized.get(pattern)
        if hit:
            return hit
    # Fall back to a contains-match so "Trade Settlement Date" is found.
    for norm, original in normalized.items():
        if "settlementdate" in norm or "valuedate" in norm:
            return original
    return None


def find_trade_date_column(headers: list[str]) -> str | None:
    normalized = {_norm(h): h for h in headers}
    for pattern in (
        "tradedate",
        "trddate",
        "dealdate",
        "executiondate",
        "transactiondate",
        "businessdate",
        "activitydate",
        "bookingdate",
        "asofdate",
    ):
        hit = normalized.get(pattern)
        if hit:
            return hit
    return None


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def resolve(
    *,
    headers: list[str],
    rows: list[dict[str, str]],
    filename: str,
    arrival_day: date,
    calendar: Calendar,
    hints: list[str] | None = None,
    settlement_offset_days: int = 1,
) -> Resolution:
    """Resolve the value date for a parsed file."""
    hints = hints or []
    filename_date = date_from_filename(filename)

    explicit_col = find_value_date_column(headers, hints)
    explicit_dates = _column_dates(rows, explicit_col) if explicit_col else []

    if explicit_dates:
        return _finish(
            candidates=explicit_dates,
            method=METHOD_CONTENT_EXPLICIT,
            base_confidence=CONF_CONTENT_EXPLICIT,
            filename_date=filename_date,
            arrival_day=arrival_day,
            calendar=calendar,
            note=f"value date read from column {explicit_col!r}",
        )

    trade_col = find_trade_date_column(headers)
    trade_dates = _column_dates(rows, trade_col) if trade_col else []
    if trade_dates:
        inferred = [calendar.add_business_days(d, settlement_offset_days) for d in trade_dates]
        return _finish(
            candidates=inferred,
            method=METHOD_CONTENT_INFERRED,
            base_confidence=CONF_CONTENT_INFERRED,
            filename_date=filename_date,
            arrival_day=arrival_day,
            calendar=calendar,
            note=(
                f"no value-date column; inferred from {trade_col!r} "
                f"plus T+{settlement_offset_days} on this client's calendar"
            ),
        )

    if filename_date:
        return _finish(
            candidates=[filename_date],
            method=METHOD_FILENAME,
            base_confidence=CONF_FILENAME,
            filename_date=filename_date,
            arrival_day=arrival_day,
            calendar=calendar,
            note="file contents carried no date; fell back to the filename",
        )

    # Nothing in the file says anything. The most defensible guess is the
    # previous business day, since a batch almost always reports completed
    # business rather than today's.
    fallback = calendar.previous_business_day(arrival_day)
    return _finish(
        candidates=[fallback],
        method=METHOD_ARRIVAL,
        base_confidence=CONF_ARRIVAL,
        filename_date=None,
        arrival_day=arrival_day,
        calendar=calendar,
        note="no date found in the filename or the contents",
    )


def _column_dates(rows: list[dict[str, str]], column: str | None) -> list[date]:
    if not column:
        return []
    out: list[date] = []
    for row in rows:
        parsed = parse_date(row.get(column, ""))
        if parsed:
            out.append(parsed)
    return out


def _finish(
    *,
    candidates: list[date],
    method: str,
    base_confidence: float,
    filename_date: date | None,
    arrival_day: date,
    calendar: Calendar,
    note: str,
) -> Resolution:
    distinct = sorted(set(candidates))
    counts = Counter(candidates)
    winner = counts.most_common(1)[0][0]

    confidence = base_confidence
    notes = [note]

    if len(distinct) > 1:
        # A file spanning several value dates is split into per-date
        # sub-batches by the caller (FR-16). The dominant date is reported
        # here so a single-slot caller still behaves sensibly.
        share = counts[winner] / len(candidates)
        confidence *= 0.9
        notes.append(
            f"contents span {len(distinct)} value dates; "
            f"{winner.isoformat()} covers {share:.0%} of rows"
        )

    rolled = calendar.roll(winner)
    if rolled != winner:
        reason = calendar.holiday_name(winner) or "a weekend"
        notes.append(
            f"{winner.isoformat()} was not a business day ({reason}); "
            f"rolled back to {rolled.isoformat()}"
        )
        confidence -= ROLL_PENALTY
        winner = rolled

    mismatch = filename_date is not None and filename_date != winner
    if mismatch and filename_date is not None:
        # Never silently resolved. A recurring mismatch means the client's
        # batch schedule has drifted, and that belongs on an operations screen.
        notes.append(
            f"filename says {filename_date.isoformat()} but the contents "
            f"resolve to {winner.isoformat()}"
        )

    return Resolution(
        resolved=winner,
        method=method,
        confidence=round(max(0.0, min(confidence, 1.0)), 3),
        from_filename=filename_date,
        from_content=distinct,
        from_arrival=arrival_day,
        mismatch_flagged=mismatch,
        calendar_id=calendar.calendar_id,
        notes="; ".join(notes),
    )


def split_by_value_date(
    rows: list[dict[str, str]], headers: list[str], hints: list[str] | None = None
) -> dict[str, list[dict[str, str]]]:
    """Partition rows by the value date each one carries (FR-16).

    Returns an empty mapping when the file has no explicit value-date column,
    in which case there is nothing to split on and the whole file belongs to
    one resolved date.
    """
    column = find_value_date_column(headers, hints or [])
    if not column:
        return {}
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        parsed = parse_date(row.get(column, ""))
        if parsed is None:
            continue
        groups.setdefault(parsed.isoformat(), []).append(row)
    return groups if len(groups) > 1 else {}
