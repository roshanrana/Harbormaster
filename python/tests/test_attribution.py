"""Client attribution: agreement raises confidence, conflict lowers it."""

from __future__ import annotations

from pathlib import Path

import pytest

from inspector import attribution as attr
from inspector import registry

CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture(scope="module")
def reg() -> registry.Registry:
    return registry.load(CONFIG)


def rows_with_account(account: str, n: int = 3) -> list[dict[str, str]]:
    return [{"Account ID": account, "TradeID": f"T{i}", "Qty": "10"} for i in range(n)]


HEADERS = ["Account ID", "TradeID", "Qty"]


def test_filename_and_contents_agreeing_gives_highest_confidence(reg: registry.Registry) -> None:
    a = attr.attribute(
        filename="MCP_TRD_20260828.csv",
        headers=HEADERS,
        rows=rows_with_account("8842-00119"),
        registry=reg,
    )
    assert a.client_id == "CLNT004"
    assert a.confidence == pytest.approx(attr.CONF_BOTH_AGREE)
    assert a.domain == "TRADE"
    assert a.conflict is False
    assert "agree" in " ".join(a.evidence)


def test_account_identifiers_alone_are_strong_evidence(reg: registry.Registry) -> None:
    # An unhelpful filename is routine; the account numbers still decide it.
    a = attr.attribute(
        filename="export_final_v2.csv",
        headers=HEADERS,
        rows=rows_with_account("DE-77120-004"),
        registry=reg,
    )
    assert a.client_id == "CLNT011"
    assert a.confidence == pytest.approx(attr.CONF_ACCOUNT_MATCH)
    assert a.account_ids == ["DE-77120-004"]


def test_filename_alone_is_weaker(reg: registry.Registry) -> None:
    a = attr.attribute(
        filename="MCP_TRD_20260828.csv",
        headers=["TradeID", "Qty"],
        rows=[{"TradeID": "T1", "Qty": "10"}],
        registry=reg,
    )
    assert a.client_id == "CLNT004"
    assert a.confidence == pytest.approx(attr.CONF_FILENAME_MATCH)


def test_disagreement_drops_confidence_into_the_review_band(reg: registry.Registry) -> None:
    # Filename says Meridian, account numbers say Northgate. Contents are the
    # stronger signal, but this is a file a human should look at.
    a = attr.attribute(
        filename="MCP_TRD_20260828.csv",
        headers=HEADERS,
        rows=rows_with_account("DE-77120-004"),
        registry=reg,
    )
    assert a.client_id == "CLNT011"
    assert a.conflict is True
    assert 0.30 < a.confidence < 0.60
    assert any("but account identifiers say" in e for e in a.evidence)


def test_accounts_from_two_clients_resolve_to_nobody(reg: registry.Registry) -> None:
    # Never routed on a majority vote.
    mixed = [{"Account ID": "8842-00119"}, {"Account ID": "DE-77120-004"}]
    a = attr.attribute(filename="mystery.csv", headers=["Account ID"], rows=mixed, registry=reg)
    assert a.client_id is None
    assert a.conflict is True
    assert a.resolved is False


def test_unattributable_file_scores_zero(reg: registry.Registry) -> None:
    # Exercises the quarantine path: nothing identifies this file at all.
    a = attr.attribute(
        filename="data.csv",
        headers=["Col1", "Col2"],
        rows=[{"Col1": "x", "Col2": "y"}],
        registry=reg,
    )
    assert a.client_id is None
    assert a.confidence == 0.0
    assert a.resolved is False


def test_unknown_account_numbers_are_not_evidence(reg: registry.Registry) -> None:
    a = attr.attribute(
        filename="data.csv",
        headers=HEADERS,
        rows=rows_with_account("ZZ-99999-000"),
        registry=reg,
    )
    assert a.client_id is None
    assert a.account_ids == []


def test_filename_hint_carries_domain_and_source(reg: registry.Registry) -> None:
    a = attr.attribute(
        filename="NGAM_20260828_COLL.xml",
        headers=["Col"],
        rows=[{"Col": "x"}],
        registry=reg,
    )
    assert a.client_id == "CLNT011"
    assert a.domain == "COLLATERAL"
    assert a.source_hint == "EUREX"
    assert a.filename_date_text == "20260828"


def test_single_expectation_client_gets_its_domain_inferred(reg: registry.Registry) -> None:
    # CLNT023 has one expectation, so a filename without a domain group is
    # still unambiguous.
    a = attr.attribute(
        filename="unknown_name.csv",
        headers=HEADERS,
        rows=rows_with_account("HK-4471-0021"),
        registry=reg,
    )
    assert a.client_id == "CLNT023"
    assert a.domain == "TRADE"


def test_multiple_accounts_for_one_client_are_all_captured(reg: registry.Registry) -> None:
    both = [{"Account ID": "8842-00119"}, {"Account ID": "8842-00204"}]
    a = attr.attribute(
        filename="MCP_TRD_20260828.csv", headers=["Account ID"], rows=both, registry=reg
    )
    assert a.client_id == "CLNT004"
    assert set(a.account_ids) == {"8842-00119", "8842-00204"}
    assert a.conflict is False


def test_account_scan_prefers_account_columns(reg: registry.Registry) -> None:
    # A trade reference that happens to look like an account must not be
    # picked up when a real account column exists.
    data = [{"Account ID": "8842-00119", "Ref": "DE-77120-004"}]
    a = attr.attribute(filename="x.csv", headers=["Account ID", "Ref"], rows=data, registry=reg)
    assert a.client_id == "CLNT004"
    assert a.account_ids == ["8842-00119"]
