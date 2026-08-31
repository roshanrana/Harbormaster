"""Excel parsing against a workbook with the quirks real ones have."""

from __future__ import annotations

from pathlib import Path

import pytest

from corpus.generate import VENUES, CorpusGenerator
from inspector.parsers.base import ParseError
from inspector.parsers.excel import ExcelParser


@pytest.fixture
def parser() -> ExcelParser:
    return ExcelParser()


@pytest.fixture
def workbook(tmp_path: Path) -> Path:
    from datetime import date

    gen = CorpusGenerator(seed=1)
    trades = gen.trades(
        account_ids=["GB-2201-4407"], venue="LSEG", value_date=date(2026, 8, 28), count=9
    )
    path = tmp_path / "HF_Custody_Positions_28Aug2026.xlsx"
    gen.write_excel(path, trades, VENUES["LSEG"], cover_sheet=True)
    return path


def test_data_sheet_is_selected_over_the_cover_sheet(parser: ExcelParser, workbook: Path) -> None:
    # Taking sheet 0 would parse the confidentiality notice as data.
    table = parser.parse(workbook)
    assert table.evidence["sheet"] == "Holdings"
    assert table.evidence["sheet_count"] == "2"


def test_header_found_below_the_title_banner(parser: ExcelParser, workbook: Path) -> None:
    table = parser.parse(workbook)
    assert "Custody Account" in table.headers
    assert "Valuation Price" in table.headers
    assert table.evidence["header_row_index"] == "3"


def test_totals_row_is_excluded(parser: ExcelParser, workbook: Path) -> None:
    # 9 trades plus a totals row. Counting the total as a holding inflates the
    # reconciliation and produces a break that looks genuine.
    table = parser.parse(workbook)
    assert table.row_count == 9
    assert any("summary row" in w for w in table.warnings)


def test_values_survive_as_strings(parser: ExcelParser, workbook: Path) -> None:
    table = parser.parse(workbook)
    row = table.rows[0]
    assert row["Custody Account"] == "GB-2201-4407"
    assert row["Currency Code"] == "GBP"
    assert float(row["Units"]) != 0


def test_sniff_uses_magic_bytes_not_the_extension(parser: ExcelParser, workbook: Path) -> None:
    head = workbook.read_bytes()[:2048]
    assert parser.sniff(head, "HF_Custody.xlsx") > 0.9
    # A workbook renamed .csv is still a workbook (FR-17).
    assert parser.sniff(head, "renamed.csv") > 0.5
    assert parser.sniff(b"A,B,C\n1,2,3\n", "x.xlsx") == 0.0


def test_merged_header_cells_are_forward_filled(parser: ExcelParser, tmp_path: Path) -> None:
    # A merged header reports its value only in the top-left cell. Unfilled,
    # the other columns lose their names and their data is orphaned.
    from openpyxl import Workbook

    wb = Workbook()
    sheet = wb.active
    assert sheet is not None
    sheet["A1"] = "Account"
    sheet["B1"] = "Prices"
    sheet.merge_cells("B1:C1")
    sheet["A2"] = "8842-00119"
    sheet["B2"] = 100.5
    sheet["C2"] = 101.5
    path = tmp_path / "merged.xlsx"
    wb.save(path)

    table = parser.parse(path)
    assert len(table.headers) == 3
    assert table.headers[1] == "Prices"
    assert table.headers[2] == "Prices__1"
    assert table.rows[0]["Prices"] == "100.5"
    assert table.rows[0]["Prices__1"] == "101.5"


def test_single_sheet_workbook_needs_no_selection(parser: ExcelParser, tmp_path: Path) -> None:
    from datetime import date

    gen = CorpusGenerator(seed=2)
    trades = gen.trades(
        account_ids=["GB-2201-4407"], venue="LSEG", value_date=date(2026, 8, 28), count=3
    )
    path = tmp_path / "simple.xlsx"
    gen.write_excel(path, trades, VENUES["LSEG"], cover_sheet=False)
    table = parser.parse(path)
    assert table.evidence["sheet"] == "Holdings"
    assert table.row_count == 3


def test_non_workbook_raises(parser: ExcelParser, tmp_path: Path) -> None:
    path = tmp_path / "fake.xlsx"
    path.write_text("this is not a workbook")
    with pytest.raises(ParseError):
        parser.parse(path)
