"""The Inspector end to end, from a file on disk to a wire message."""

from __future__ import annotations

from pathlib import Path

import pytest

from harbormaster.v1 import harbormaster_pb2 as hm
from inspector import confidence, registry
from inspector.main import Inspector, template_fingerprint, to_proto, topic_for
from inspector.parsers.base import ParseError

CONFIG = Path(__file__).resolve().parents[2] / "config"

CLEAN_TRADE_FILE = """Account ID,Symbol,TradeID,Trade Date,Value Date,Qty,Exec Price,Settle Price,Net Amount,CCY,B/S
8842-00119,ESZ6,T1,2026-08-27,2026-08-28,10,5401.25,5399.50,54012.50,USD,B
8842-00119,ESZ6,T2,2026-08-27,2026-08-28,5,5402.75,5399.50,27013.75,USD,B
8842-00204,NQZ6,T3,2026-08-27,2026-08-28,3,19850.25,19845.00,59550.75,USD,S
"""


@pytest.fixture(scope="module")
def reg() -> registry.Registry:
    return registry.load(CONFIG)


@pytest.fixture
def inspector(reg: registry.Registry, tmp_path: Path) -> Inspector:
    return Inspector(reg, tmp_path)


def write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


def test_clean_file_classifies_and_dispatches(inspector: Inspector, tmp_path: Path) -> None:
    path = write(tmp_path, "MCP_TRD_20260828.csv", CLEAN_TRADE_FILE)
    results = inspector.classify("arr-1", path, "MCP_TRD_20260828.csv")

    assert len(results) == 1
    r = results[0]
    assert r.client_id == "CLNT004"
    assert r.domain == "TRADE"
    assert r.value_date.resolved_iso == "2026-08-28"
    assert r.score.disposition == confidence.DISPATCHED
    assert r.row_count == 3


def test_late_file_resolves_to_its_true_value_date(inspector: Inspector, tmp_path: Path) -> None:
    # The headline case. Filename says the 31st; contents say the 28th.
    # Content wins and the disagreement is flagged, not swallowed.
    path = write(tmp_path, "MCP_TRD_20260831.csv", CLEAN_TRADE_FILE)
    r = inspector.classify("arr-2", path, "MCP_TRD_20260831.csv")[0]

    assert r.value_date.resolved_iso == "2026-08-28"
    assert r.value_date.mismatch_flagged is True
    assert r.value_date.method == "CONTENT_EXPLICIT"
    assert r.score.disposition == confidence.DISPATCHED
    assert any("value-date disagreement" in reason for reason in r.score.reasons)


def test_prices_are_mapped_the_right_way_round(inspector: Inspector, tmp_path: Path) -> None:
    path = write(tmp_path, "MCP_TRD_20260828.csv", CLEAN_TRADE_FILE)
    r = inspector.classify("arr-3", path, "MCP_TRD_20260828.csv")[0]
    by_field = {m.canonical_field: m.source_field for m in r.mappings if m.canonical_field}
    assert by_field["trade_price"] == "Exec Price"
    assert by_field["settlement_price"] == "Settle Price"


def test_every_mapping_carries_provenance(inspector: Inspector, tmp_path: Path) -> None:
    # FR-24: a mapping with no recorded evidence is a defect.
    path = write(tmp_path, "MCP_TRD_20260828.csv", CLEAN_TRADE_FILE)
    r = inspector.classify("arr-4", path, "MCP_TRD_20260828.csv")[0]
    for m in r.mappings:
        assert m.evidence, f"{m.source_field} has no evidence"
        assert m.tier is not None


def test_unattributable_file_is_quarantined(inspector: Inspector, tmp_path: Path) -> None:
    body = "Alpha,Beta,Gamma\n1,2,3\n4,5,6\n"
    path = write(tmp_path, "mystery.csv", body)
    r = inspector.classify("arr-5", path, "mystery.csv")[0]
    assert r.client_id is None
    assert r.score.disposition in {confidence.QUARANTINED, confidence.REJECTED}
    assert any("client could not be determined" in reason for reason in r.score.reasons)


def test_multi_date_file_splits_into_sub_batches(inspector: Inspector, tmp_path: Path) -> None:
    body = CLEAN_TRADE_FILE + (
        "8842-00119,ESZ6,T4,2026-08-26,2026-08-27,7,5390.00,5388.25,37730.00,USD,B\n"
    )
    path = write(tmp_path, "MCP_TRD_20260828.csv", body)
    results = inspector.classify("arr-6", path, "MCP_TRD_20260828.csv")

    assert len(results) == 2
    assert {r.value_date.resolved_iso for r in results} == {"2026-08-27", "2026-08-28"}
    assert sum(r.row_count for r in results) == 4
    assert {r.sub_batch_total for r in results} == {2}
    assert sorted(r.sub_batch_index for r in results) == [0, 1]


def test_canonical_parquet_is_written(inspector: Inspector, tmp_path: Path) -> None:
    import polars as pl

    path = write(tmp_path, "MCP_TRD_20260828.csv", CLEAN_TRADE_FILE)
    r = inspector.classify("arr-7", path, "MCP_TRD_20260828.csv")[0]
    uri = inspector.write_canonical(r, tmp_path / "canonical")

    assert uri.startswith("fs://canonical/")
    frame = pl.read_parquet(tmp_path / "canonical" / "arr-7.parquet")
    assert frame.height == 3
    # Harbormaster-determined fields are stamped on every row.
    assert set(frame["value_date"].to_list()) == {"2026-08-28"}
    assert set(frame["client_id"].to_list()) == {"CLNT004"}
    # Account names come from the registry even though the file omits them.
    assert "Meridian Global Macro" in frame["account_name"].to_list()


def test_proto_round_trip_carries_the_reasoning(inspector: Inspector, tmp_path: Path) -> None:
    path = write(tmp_path, "MCP_TRD_20260831.csv", CLEAN_TRADE_FILE)
    r = inspector.classify("arr-8", path, "MCP_TRD_20260831.csv")[0]
    inspector.write_canonical(r, tmp_path / "canonical")
    msg = to_proto(r)

    assert msg.client_id == "CLNT004"
    assert msg.value_date.resolved == "2026-08-28"
    assert msg.value_date.from_filename == "2026-08-31"
    assert msg.value_date.mismatch_flagged is True
    assert msg.disposition == hm.ARRIVAL_DISPOSITION_DISPATCHED
    assert msg.format == hm.SOURCE_FORMAT_CSV
    assert msg.template_fingerprint.startswith("tf_")
    assert all(fm.evidence for fm in msg.field_mappings)


def test_quarantined_arrivals_go_to_the_review_queue() -> None:
    from inspector import bus

    assert topic_for(confidence.DISPATCHED) == bus.TOPIC_ARRIVALS_CLASSIFIED
    assert topic_for(confidence.QUARANTINED) == bus.TOPIC_ARRIVALS_QUARANTINE
    assert topic_for(confidence.REJECTED) == bus.TOPIC_ARRIVALS_QUARANTINE


def test_format_is_decided_by_content_not_extension(inspector: Inspector, tmp_path: Path) -> None:
    # A CSV named .txt must still classify (FR-17).
    path = write(tmp_path, "MCP_TRD_20260828.txt", CLEAN_TRADE_FILE)
    r = inspector.classify("arr-9", path, "MCP_TRD_20260828.txt")[0]
    assert r.source_format == "CSV"


def test_unparseable_file_raises_rather_than_guessing(inspector: Inspector, tmp_path: Path) -> None:
    path = tmp_path / "binary.dat"
    path.write_bytes(b"\x00\x01\x02\x03\xff\xfe")
    with pytest.raises(ParseError):
        inspector.classify("arr-10", path, "binary.dat")


def test_template_fingerprint_is_stable_and_layout_sensitive() -> None:
    # The cache key that keeps the model tier near the 2 percent target.
    a = template_fingerprint("CLNT004", ["Account ID", "Qty", "Price"])
    b = template_fingerprint("CLNT004", ["account_id", "QTY", "price"])
    c_ = template_fingerprint("CLNT004", ["Qty", "Account ID", "Price"])
    d = template_fingerprint("CLNT011", ["Account ID", "Qty", "Price"])

    assert a == b, "header cosmetics must not change the fingerprint"
    assert a != c_, "column order is part of a template"
    assert a != d, "the same layout for a different client is a different template"


def test_arithmetic_cross_check_is_recorded(inspector: Inspector, tmp_path: Path) -> None:
    path = write(tmp_path, "MCP_TRD_20260828.csv", CLEAN_TRADE_FILE)
    r = inspector.classify("arr-11", path, "MCP_TRD_20260828.csv")[0]
    assert "reconciles to amount" in r.cross_check
