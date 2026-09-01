"""Cross-language contract test (ADR-003).

The Go suite writes a protojson fixture from generated Go types; this reads it
back with generated Python types and asserts field-for-field agreement. If the
two languages ever drift, this fails in CI rather than silently mismatching a
field in production.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from google.protobuf import json_format

from harbormaster.v1 import harbormaster_pb2 as hm

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "go"
    / "internal"
    / "contract"
    / "fixture_arrival_classified.json"
)


@pytest.fixture(scope="module")
def msg() -> hm.ArrivalClassified:
    if not FIXTURE.exists():
        pytest.skip("run `go test ./internal/contract/` first to emit the fixture")
    return json_format.Parse(FIXTURE.read_text(encoding="utf-8"), hm.ArrivalClassified())


def test_scalars_survive(msg: hm.ArrivalClassified) -> None:
    assert msg.arrival_id == "01JCTESTARRIVAL0000000001"
    assert msg.client_id == "CLNT004"
    assert msg.source_hint == "CME"
    assert msg.row_count == 1421
    assert msg.client_confidence == pytest.approx(0.94)


def test_enums_agree_across_languages(msg: hm.ArrivalClassified) -> None:
    assert msg.format == hm.SOURCE_FORMAT_CSV
    assert msg.domain == hm.PRODUCT_DOMAIN_TRADE
    assert msg.recon_side == hm.RECON_SIDE_EXTERNAL_CLIENT
    assert msg.disposition == hm.ARRIVAL_DISPOSITION_DISPATCHED


def test_value_date_disagreement_is_preserved(msg: hm.ArrivalClassified) -> None:
    # The whole project exists to get this right, so it gets its own assertion.
    vd = msg.value_date
    assert vd.resolved == "2026-08-28"
    assert vd.from_filename == "2026-08-31"
    assert list(vd.from_content) == ["2026-08-28"]
    assert vd.mismatch_flagged is True
    assert vd.method == "CONTENT_EXPLICIT"


def test_field_mapping_provenance_survives(msg: hm.ArrivalClassified) -> None:
    by_source = {m.source_field: m for m in msg.field_mappings}
    assert by_source["Px_Sett"].canonical_field == "settlement_price"
    assert by_source["Px_Sett"].tier == hm.RESOLUTION_TIER_ALIAS
    # The bare "Price" column resolved structurally, not by name.
    assert by_source["Price"].canonical_field == "trade_price"
    assert by_source["Price"].tier == hm.RESOLUTION_TIER_LOCAL
    assert by_source["Price"].evidence  # never blank (FR-24)


def test_reserialises_to_equivalent_json(msg: hm.ArrivalClassified) -> None:
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reserialised = json.loads(json_format.MessageToJson(msg))
    assert reserialised == original
