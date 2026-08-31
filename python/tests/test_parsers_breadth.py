"""XML, FIXML, JSON and email-text parsers, against generated corpus files."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from corpus.generate import VENUES, CorpusGenerator
from inspector.parsers.base import ParseError
from inspector.parsers.email_text import EmailTextParser
from inspector.parsers.fixml import FIXMLParser
from inspector.parsers.json_parser import JSONParser, flatten
from inspector.parsers.xml_parser import XMLParser

VALUE_DATE = date(2026, 8, 28)


@pytest.fixture
def gen() -> CorpusGenerator:
    return CorpusGenerator(seed=7)


@pytest.fixture
def eurex_trades(gen: CorpusGenerator) -> list:
    return gen.trades(account_ids=["DE-77120-004"], venue="EUREX", value_date=VALUE_DATE, count=6)


@pytest.fixture
def cme_trades(gen: CorpusGenerator) -> list:
    return gen.trades(account_ids=["8842-00119"], venue="CME", value_date=VALUE_DATE, count=6)


# --- XML -------------------------------------------------------------------


def test_xml_finds_the_record_element_under_a_wrapper(
    gen: CorpusGenerator, eurex_trades: list, tmp_path: Path
) -> None:
    # Records sit at TradeExtract > Trades > Trade. Taking the root's children
    # would yield one row containing everything.
    path = tmp_path / "NGAM_20260828_TRADES.xml"
    gen.write_xml(path, eurex_trades, VENUES["EUREX"])
    table = XMLParser().parse(path)
    assert table.evidence["record_element"] == "Trade"
    assert table.row_count == 6


def test_xml_flattens_attributes_and_elements(
    gen: CorpusGenerator, eurex_trades: list, tmp_path: Path
) -> None:
    path = tmp_path / "t.xml"
    gen.write_xml(path, eurex_trades, VENUES["EUREX"])
    table = XMLParser().parse(path)
    assert "@id" in table.headers  # attribute, prefixed so it cannot collide
    assert "SettlPric" in table.headers
    assert "ValueDt" in table.headers
    assert table.rows[0]["ValueDt"] == "2026-08-28"


def test_xml_paths_are_the_source_field_names(
    gen: CorpusGenerator, eurex_trades: list, tmp_path: Path
) -> None:
    # Provenance: an operator sees where a value came from.
    path = tmp_path / "t.xml"
    gen.write_xml(path, eurex_trades, VENUES["EUREX"])
    table = XMLParser().parse(path)
    assert "SettlementAmount" in table.headers
    assert all(table.rows[0][h] is not None for h in table.headers)


def test_xml_repeating_group_is_suffixed_not_overwritten() -> None:
    parser = XMLParser()
    import tempfile

    body = """<?xml version="1.0"?>
<Extract>
  <Trade id="T1"><Leg>USD</Leg><Leg>EUR</Leg><Qty>10</Qty></Trade>
  <Trade id="T2"><Leg>GBP</Leg><Leg>JPY</Leg><Qty>20</Qty></Trade>
</Extract>"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "legs.xml"
        p.write_text(body)
        table = parser.parse(p)
    assert table.rows[0]["Leg[0]"] == "USD"
    assert table.rows[0]["Leg[1]"] == "EUR"


def test_xml_defers_to_fixml(gen: CorpusGenerator, cme_trades: list, tmp_path: Path) -> None:
    # FIXML is XML, but it has tag semantics worth using.
    path = tmp_path / "f.xml"
    gen.write_fixml(path, cme_trades)
    head = path.read_bytes()[:2048]
    assert FIXMLParser().sniff(head, "f.xml") > XMLParser().sniff(head, "f.xml")


def test_malformed_xml_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.xml"
    p.write_text("<Root><Unclosed>")
    with pytest.raises(ParseError):
        XMLParser().parse(p)


# --- FIXML -----------------------------------------------------------------


def test_fixml_tags_become_dictionary_friendly_headers(
    gen: CorpusGenerator, cme_trades: list, tmp_path: Path
) -> None:
    path = tmp_path / "exec.fixml"
    gen.write_fixml(path, cme_trades)
    table = FIXMLParser().parse(path)
    assert "LastPx" in table.headers
    assert "Settlement Price" in table.headers
    assert "Settlement Date" in table.headers
    assert table.row_count == 6


def test_fixml_side_codes_are_translated(
    gen: CorpusGenerator, cme_trades: list, tmp_path: Path
) -> None:
    # "1" is not something a reviewer should have to decode.
    path = tmp_path / "exec.fixml"
    gen.write_fixml(path, cme_trades)
    table = FIXMLParser().parse(path)
    assert set(table.column("Side")) <= {"BUY", "SELL"}


def test_fixml_identifier_is_named_by_its_source(
    gen: CorpusGenerator, cme_trades: list, tmp_path: Path
) -> None:
    # IDSrc=4 means ISIN. An ISIN and a CUSIP are both "ID" in FIXML, so
    # naming the column by source is what lets the alias dictionary resolve it.
    path = tmp_path / "exec.fixml"
    gen.write_fixml(path, cme_trades)
    table = FIXMLParser().parse(path)
    assert "ISIN" in table.headers
    assert "Symbol" in table.headers


def test_fixml_customer_account_is_extracted_from_pty(
    gen: CorpusGenerator, cme_trades: list, tmp_path: Path
) -> None:
    path = tmp_path / "exec.fixml"
    gen.write_fixml(path, cme_trades)
    table = FIXMLParser().parse(path)
    assert "Account ID" in table.headers
    assert table.rows[0]["Account ID"] == "8842-00119"


def test_fixml_without_reports_raises(tmp_path: Path) -> None:
    p = tmp_path / "empty.fixml"
    p.write_text('<FIXML v="5.0"></FIXML>')
    with pytest.raises(ParseError):
        FIXMLParser().parse(p)


# --- JSON ------------------------------------------------------------------


def test_json_finds_records_and_flattens_nesting(
    gen: CorpusGenerator, cme_trades: list, tmp_path: Path
) -> None:
    path = tmp_path / "payload.json"
    gen.write_json(path, cme_trades, VENUES["CME"])
    table = JSONParser().parse(path)
    assert table.evidence["records_at"] == "records"
    assert table.row_count == 6
    assert "economics.netAmount" in table.headers
    assert "dates.valueDate" in table.headers
    assert table.rows[0]["dates.valueDate"] == "2026-08-28"


def test_json_envelope_fields_are_kept_on_every_row(
    gen: CorpusGenerator, cme_trades: list, tmp_path: Path
) -> None:
    # "venue": "CME" is real evidence about the file, not noise.
    path = tmp_path / "payload.json"
    gen.write_json(path, cme_trades, VENUES["CME"])
    table = JSONParser().parse(path)
    assert set(table.column("venue")) == {"CME"}


def test_json_bare_array_is_handled(tmp_path: Path) -> None:
    p = tmp_path / "arr.json"
    p.write_text('[{"a": 1, "b": 2}, {"a": 3, "b": 4}]')
    table = JSONParser().parse(p)
    assert table.row_count == 2
    assert table.evidence["records_at"] == "$"


def test_json_scalar_list_becomes_one_cell() -> None:
    assert flatten({"tags": ["a", "b", "c"]})["tags"] == "a, b, c"


def test_json_flatten_is_depth_bounded() -> None:
    # An arrival that exhausts the stack blocks its whole partition.
    deep: dict = {"v": 1}
    for _ in range(50):
        deep = {"n": deep}
    result = flatten(deep)
    assert result
    assert all(len(k.split(".")) <= 12 for k in result)


def test_malformed_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text('{"unclosed": ')
    with pytest.raises(ParseError):
        JSONParser().parse(p)


# --- email text ------------------------------------------------------------


@pytest.fixture
def advice(gen: CorpusGenerator, tmp_path: Path) -> Path:
    path = tmp_path / "ardent-cash-2026-08-28.txt"
    gen.write_email(
        path,
        [
            ("AGM-5590-01", Decimal("1250000.00"), "USD", VALUE_DATE),
            ("AGM-5590-01", Decimal("-487350.25"), "USD", VALUE_DATE),
            ("AGM-5590-01", Decimal("96200.00"), "EUR", VALUE_DATE),
        ],
    )
    return path


def test_email_extracts_every_movement(advice: Path) -> None:
    table = EmailTextParser().parse(advice)
    assert table.row_count == 3
    assert table.evidence["movements_found"] == "3"


def test_email_amounts_directions_and_currencies(advice: Path) -> None:
    table = EmailTextParser().parse(advice)
    amounts = table.column("Net Amount")
    assert "1250000.00" in amounts
    assert "-487350.25" in amounts  # debit is signed negative
    assert set(table.column("Currency")) == {"USD", "EUR"}
    assert set(table.column("Direction")) == {"CREDIT", "DEBIT"}


def test_email_value_date_is_extracted(advice: Path) -> None:
    table = EmailTextParser().parse(advice)
    assert set(table.column("Value Date")) == {"2026-08-28"}


def test_email_carries_per_line_extraction_confidence(advice: Path) -> None:
    # How much of the body was actually understood travels downstream, so a
    # thinly-parsed advice can be quarantined rather than trusted.
    table = EmailTextParser().parse(advice)
    for value in table.column("Extraction Confidence"):
        assert 0.5 <= float(value) <= 1.0
    assert all(table.column("Source Line"))


def test_email_headers_are_not_treated_as_movements(advice: Path) -> None:
    table = EmailTextParser().parse(advice)
    assert not any("Subject:" in line for line in table.column("Source Line"))


def test_email_sniff_rejects_delimited_text(advice: Path) -> None:
    parser = EmailTextParser()
    assert parser.sniff(advice.read_bytes()[:2048], advice.name) > 0.8
    assert parser.sniff(b"A,B,C,D\n1,2,3,4\n5,6,7,8\n", "x.csv") == 0.0
    assert parser.sniff(b'{"a":1}', "x.json") == 0.0


def test_email_with_no_movements_raises(tmp_path: Path) -> None:
    p = tmp_path / "chatty.txt"
    p.write_text("From: a@b.example\nSubject: lunch\n\nAre we still on for Thursday?\n")
    with pytest.raises(ParseError):
        EmailTextParser().parse(p)
