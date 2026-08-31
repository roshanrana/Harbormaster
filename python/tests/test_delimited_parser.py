"""Delimited parser against the shapes real counterparty extracts arrive in."""

from __future__ import annotations

from pathlib import Path

import pytest

from inspector.parsers.base import ParseError
from inspector.parsers.delimited import DelimitedParser


@pytest.fixture
def parser() -> DelimitedParser:
    return DelimitedParser()


def write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


def test_plain_csv(parser: DelimitedParser, tmp_path: Path) -> None:
    p = write(tmp_path, "t.csv", "TradeID,Qty,Price\nT1,100,42.50\nT2,50,42.75\n")
    table = parser.parse(p)
    assert table.headers == ["TradeID", "Qty", "Price"]
    assert table.row_count == 2
    assert table.rows[1]["Price"] == "42.75"


def test_preamble_rows_above_the_header_are_skipped(
    parser: DelimitedParser, tmp_path: Path
) -> None:
    # Custody extracts routinely carry a title banner and a blank spacer.
    body = (
        "MERIDIAN CAPITAL PARTNERS - DAILY TRADE EXTRACT\n"
        "Generated 2026-08-31 06:40 UTC\n"
        "\n"
        "TradeID,Qty,Price\n"
        "T1,100,42.50\n"
    )
    table = parser.parse(write(tmp_path, "t.csv", body))
    assert table.headers == ["TradeID", "Qty", "Price"]
    assert table.row_count == 1
    assert table.evidence["header_row_index"] == "2"


def test_trailing_total_row_is_excluded(parser: DelimitedParser, tmp_path: Path) -> None:
    # A totals line counted as a trade inflates the reconciliation by one row
    # and produces a break that looks like a genuine discrepancy.
    body = "TradeID,Qty,Price\nT1,100,42.50\nT2,50,42.75\nTotal,150,\n"
    table = parser.parse(write(tmp_path, "t.csv", body))
    assert table.row_count == 2
    assert any("summary row" in w for w in table.warnings)


def test_pipe_delimiter_detected(parser: DelimitedParser, tmp_path: Path) -> None:
    body = "TradeID|Qty|Price\nT1|100|42.50\n"
    table = parser.parse(write(tmp_path, "t.txt", body))
    assert table.headers == ["TradeID", "Qty", "Price"]
    assert table.evidence["delimiter"] == "pipe"


def test_commas_inside_a_description_do_not_beat_the_real_delimiter(
    parser: DelimitedParser, tmp_path: Path
) -> None:
    # ',' is the most frequent character here, but '|' is the real delimiter.
    # Only column-count consistency reveals that.
    body = (
        "TradeID|Description|Qty|Price\n"
        "T1|CME, Eurodollar, Dec 26|100|42.50\n"
        "T2|ICE, Brent Crude, Mar 27|50|42.75\n"
    )
    table = parser.parse(write(tmp_path, "t.txt", body))
    assert table.headers == ["TradeID", "Description", "Qty", "Price"]
    assert table.rows[0]["Description"] == "CME, Eurodollar, Dec 26"


def test_tab_delimiter(parser: DelimitedParser, tmp_path: Path) -> None:
    table = parser.parse(write(tmp_path, "t.tsv", "TradeID\tQty\tPrice\nT1\t100\t42.5\n"))
    assert table.evidence["delimiter"] == "tab"


def test_duplicate_headers_are_suffixed_not_dropped(
    parser: DelimitedParser, tmp_path: Path
) -> None:
    # Both columns must survive into mapping so the price disambiguator can
    # tell them apart. Keeping the last one would silently lose a column.
    body = "TradeID,Price,Price\nT1,42.50,42.80\n"
    table = parser.parse(write(tmp_path, "t.csv", body))
    assert table.headers == ["TradeID", "Price", "Price__1"]
    assert table.rows[0]["Price"] == "42.50"
    assert table.rows[0]["Price__1"] == "42.80"


def test_ragged_short_row_is_padded(parser: DelimitedParser, tmp_path: Path) -> None:
    table = parser.parse(write(tmp_path, "t.csv", "A,B,C\n1,2\n"))
    assert table.rows[0] == {"A": "1", "B": "2", "C": ""}


def test_latin1_file_does_not_fail_the_arrival(parser: DelimitedParser, tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_bytes("Account,Name\n8842,Crédit Agricole\n".encode("latin-1"))
    table = parser.parse(p)
    assert table.row_count == 1


def test_empty_file_raises(parser: DelimitedParser, tmp_path: Path) -> None:
    with pytest.raises(ParseError):
        parser.parse(write(tmp_path, "t.csv", "\n\n\n"))


def test_sniff_prefers_csv_over_json_and_xml(parser: DelimitedParser) -> None:
    assert parser.sniff(b"A,B,C\n1,2,3\n4,5,6\n", "x.csv") > 0.5
    assert parser.sniff(b'{"a": 1, "b": 2}', "x.json") == 0.0
    assert parser.sniff(b"<root><a/></root>", "x.xml") == 0.0


def test_sniff_ignores_a_misleading_extension(parser: DelimitedParser) -> None:
    # A CSV named .txt must still be recognised as CSV (FR-17).
    assert parser.sniff(b"TradeID,Qty,Price\nT1,100,42.5\nT2,1,2\n", "extract.txt") > 0.5
