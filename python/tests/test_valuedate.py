"""Value-date resolution: the logic the whole project turns on."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from inspector import registry
from inspector import valuedate as vd

CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture(scope="module")
def reg() -> registry.Registry:
    return registry.load(CONFIG)


@pytest.fixture
def us(reg: registry.Registry) -> registry.Calendar:
    cal = reg.calendar("US_EQUITY")
    assert cal is not None
    return cal


def rows(column: str, *values: str) -> list[dict[str, str]]:
    return [{"TradeID": f"T{i}", column: v} for i, v in enumerate(values)]


# --- date parsing ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-08-28", date(2026, 8, 28)),
        ("2026/08/28", date(2026, 8, 28)),
        ("20260828", date(2026, 8, 28)),
        ("28-Aug-2026", date(2026, 8, 28)),
        ("28AUG2026", date(2026, 8, 28)),
        ("28.08.2026", date(2026, 8, 28)),
        ("2026-08-28T17:30:00Z", date(2026, 8, 28)),
        ("2026-08-28 17:30:00", date(2026, 8, 28)),
        ("", None),
        ("not a date", None),
    ],
)
def test_parse_date_handles_real_formats(raw: str, expected: date | None) -> None:
    assert vd.parse_date(raw) == expected


def test_a_price_is_not_mistaken_for_a_compact_date() -> None:
    # 54012.50 must not parse, and an 8-digit quantity must not become a date
    # in the year 5401.
    assert vd.parse_date("54012.50") is None
    assert vd.parse_date("54012500") is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("MCP_TRD_20260828.csv", date(2026, 8, 28)),
        ("meridian-trades-2026-08-28.csv", date(2026, 8, 28)),
        ("HF_Custody_Positions_28Aug2026.xlsx", date(2026, 8, 28)),
        ("trades.csv", None),
    ],
)
def test_filename_date_extraction(name: str, expected: date | None) -> None:
    assert vd.date_from_filename(name) == expected


# --- resolution ------------------------------------------------------------


def test_explicit_value_date_column_wins(us: registry.Calendar) -> None:
    r = vd.resolve(
        headers=["TradeID", "Value Date"],
        rows=rows("Value Date", "2026-08-28", "2026-08-28"),
        filename="MCP_TRD_20260831.csv",
        arrival_day=date(2026, 8, 31),
        calendar=us,
    )
    assert r.resolved == date(2026, 8, 28)
    assert r.method == vd.METHOD_CONTENT_EXPLICIT
    assert r.confidence == pytest.approx(0.97)


def test_filename_content_disagreement_is_always_flagged(us: registry.Calendar) -> None:
    # FR-12. The late-batch case: file named for the 31st, contents from the
    # 28th. Content wins, and the disagreement is surfaced, never swallowed.
    r = vd.resolve(
        headers=["TradeID", "SettleDate"],
        rows=rows("SettleDate", "2026-08-28"),
        filename="MCP_TRD_20260831.csv",
        arrival_day=date(2026, 8, 31),
        calendar=us,
    )
    assert r.resolved == date(2026, 8, 28)
    assert r.mismatch_flagged is True
    assert "20260831" not in r.notes  # the note reads as dates, not filenames
    assert "2026-08-31" in r.notes and "2026-08-28" in r.notes


def test_agreement_is_not_flagged(us: registry.Calendar) -> None:
    r = vd.resolve(
        headers=["Value Date"],
        rows=rows("Value Date", "2026-08-28"),
        filename="MCP_TRD_20260828.csv",
        arrival_day=date(2026, 8, 28),
        calendar=us,
    )
    assert r.mismatch_flagged is False


def test_client_hint_finds_a_nonstandard_column(
    reg: registry.Registry, us: registry.Calendar
) -> None:
    client = reg.client("CLNT011")
    assert client is not None
    r = vd.resolve(
        headers=["TrdID", "ValueDt"],
        rows=rows("ValueDt", "2026-08-28"),
        filename="NGAM_20260828_TRADES.xml",
        arrival_day=date(2026, 8, 28),
        calendar=us,
        hints=client.value_date_hints(),
    )
    assert r.resolved == date(2026, 8, 28)
    assert r.method == vd.METHOD_CONTENT_EXPLICIT


def test_inferred_from_trade_date_when_no_value_date_column(us: registry.Calendar) -> None:
    r = vd.resolve(
        headers=["TradeID", "Trade Date"],
        rows=rows("Trade Date", "2026-08-28"),
        filename="trades.csv",
        arrival_day=date(2026, 8, 31),
        calendar=us,
        settlement_offset_days=1,
    )
    # T+1 from Friday the 28th is Monday the 31st, not Saturday the 29th.
    assert r.resolved == date(2026, 8, 31)
    assert r.method == vd.METHOD_CONTENT_INFERRED
    assert r.confidence == pytest.approx(0.85)


def test_filename_fallback_when_contents_are_silent(us: registry.Calendar) -> None:
    r = vd.resolve(
        headers=["TradeID", "Qty"],
        rows=[{"TradeID": "T1", "Qty": "100"}],
        filename="MCP_TRD_20260828.csv",
        arrival_day=date(2026, 8, 31),
        calendar=us,
    )
    assert r.resolved == date(2026, 8, 28)
    assert r.method == vd.METHOD_FILENAME
    assert r.confidence == pytest.approx(0.70)


def test_last_resort_uses_the_previous_business_day(us: registry.Calendar) -> None:
    r = vd.resolve(
        headers=["TradeID"],
        rows=[{"TradeID": "T1"}],
        filename="extract.csv",
        arrival_day=date(2026, 8, 31),
        calendar=us,
    )
    assert r.resolved == date(2026, 8, 28)
    assert r.method == vd.METHOD_ARRIVAL
    assert r.confidence < 0.6


def test_non_business_day_is_rolled_and_penalised(us: registry.Calendar) -> None:
    # Contents claim Saturday. A reconciliation for a day the market was shut
    # would never find a counterpart, so the date is rolled and confidence cut.
    r = vd.resolve(
        headers=["Value Date"],
        rows=rows("Value Date", "2026-08-29"),
        filename="x.csv",
        arrival_day=date(2026, 8, 31),
        calendar=us,
    )
    assert r.resolved == date(2026, 8, 28)
    assert r.confidence < vd.CONF_CONTENT_EXPLICIT
    assert "not a business day" in r.notes


def test_holiday_is_rolled_and_named(us: registry.Calendar) -> None:
    r = vd.resolve(
        headers=["Value Date"],
        rows=rows("Value Date", "2026-12-25"),
        filename="x.csv",
        arrival_day=date(2026, 12, 28),
        calendar=us,
    )
    assert r.resolved == date(2026, 12, 24)
    assert "Christmas" in r.notes


def test_resolved_date_is_always_a_business_day(reg: registry.Registry) -> None:
    # Property: whatever the input claims, the answer is a day the market was
    # open. Anything else guarantees a reconciliation with no counterpart.
    for cal_id in ("US_EQUITY", "UK_EQUITY", "EUR_DERIV", "HK_EQUITY"):
        cal = reg.calendar(cal_id)
        assert cal is not None
        for claimed in ("2026-08-29", "2026-08-30", "2026-12-25", "2026-01-01", "2026-04-03"):
            r = vd.resolve(
                headers=["Value Date"],
                rows=rows("Value Date", claimed),
                filename="x.csv",
                arrival_day=date(2026, 12, 28),
                calendar=cal,
            )
            assert r.resolved is not None
            assert cal.is_business_day(r.resolved), f"{cal_id} returned {r.resolved}"


def test_mixed_dates_report_the_dominant_one_and_lower_confidence(us: registry.Calendar) -> None:
    r = vd.resolve(
        headers=["Value Date"],
        rows=rows("Value Date", "2026-08-28", "2026-08-28", "2026-08-28", "2026-08-27"),
        filename="x.csv",
        arrival_day=date(2026, 8, 31),
        calendar=us,
    )
    assert r.resolved == date(2026, 8, 28)
    assert len(r.from_content) == 2
    assert r.confidence < vd.CONF_CONTENT_EXPLICIT
    assert "span 2 value dates" in r.notes


# --- multi-date splitting --------------------------------------------------


def test_split_partitions_rows_by_value_date() -> None:
    data = rows("Value Date", "2026-08-27", "2026-08-28", "2026-08-28")
    groups = vd.split_by_value_date(data, ["TradeID", "Value Date"])
    assert set(groups) == {"2026-08-27", "2026-08-28"}
    assert len(groups["2026-08-28"]) == 2
    assert sum(len(v) for v in groups.values()) == len(data)


def test_single_date_file_is_not_split() -> None:
    data = rows("Value Date", "2026-08-28", "2026-08-28")
    assert vd.split_by_value_date(data, ["TradeID", "Value Date"]) == {}


def test_file_without_a_value_date_column_is_not_split() -> None:
    assert vd.split_by_value_date([{"TradeID": "T1"}], ["TradeID"]) == {}
