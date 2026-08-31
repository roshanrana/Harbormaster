"""Confidence composition and disposition routing."""

from __future__ import annotations

from datetime import date

import pytest

from inspector import confidence as conf
from inspector.attribution import Attribution
from inspector.mapping import canonical as c
from inspector.mapping.tier1 import Mapping
from inspector.valuedate import METHOD_CONTENT_EXPLICIT, METHOD_FILENAME, Resolution


def good_attr(**kw: object) -> Attribution:
    base = {"client_id": "CLNT004", "confidence": 0.99, "account_ids": ["8842-00119"]}
    base.update(kw)
    return Attribution(**base)  # type: ignore[arg-type]


def good_date(**kw: object) -> Resolution:
    base = {
        "resolved": date(2026, 8, 28),
        "method": METHOD_CONTENT_EXPLICIT,
        "confidence": 0.97,
    }
    base.update(kw)
    return Resolution(**base)  # type: ignore[arg-type]


def full_trade_mappings(confidence: float = 1.0) -> list[Mapping]:
    return [
        Mapping(f"src_{f}", f, c.Tier.ALIAS, confidence, "alias")
        for f in c.REQUIRED_BY_DOMAIN[c.Domain.TRADE]
    ]


def test_clean_file_dispatches() -> None:
    s = conf.compose(
        attribution=good_attr(),
        value_date=good_date(),
        mappings=full_trade_mappings(),
        domain="TRADE",
    )
    assert s.disposition == conf.DISPATCHED
    assert s.overall > 0.95
    assert s.reasons == []


def test_missing_required_field_quarantines_regardless_of_score() -> None:
    # A file can look excellent on average and still be unusable.
    partial = [m for m in full_trade_mappings() if m.canonical_field != "net_amount"]
    s = conf.compose(
        attribution=good_attr(),
        value_date=good_date(),
        mappings=partial,
        domain="TRADE",
    )
    assert s.disposition == conf.QUARANTINED
    assert "net_amount" in s.unmapped_required
    assert any("net_amount" in r for r in s.reasons)


def test_unknown_client_never_dispatches() -> None:
    # Averaging a perfect mapping against a missing client is exactly how a
    # well-formed file gets sent to the wrong reconciliation.
    s = conf.compose(
        attribution=Attribution(
            client_id=None, confidence=0.0, evidence=["no filename pattern matched"]
        ),
        value_date=good_date(),
        mappings=full_trade_mappings(),
        domain="TRADE",
    )
    assert s.disposition in {conf.QUARANTINED, conf.REJECTED}
    assert any("client could not be determined" in r for r in s.reasons)


def test_conflicting_attribution_lands_in_review() -> None:
    s = conf.compose(
        attribution=good_attr(
            confidence=0.45,
            conflict=True,
            evidence=["filename says CLNT004 but account identifiers say CLNT011"],
        ),
        value_date=good_date(),
        mappings=full_trade_mappings(),
        domain="TRADE",
    )
    assert s.disposition == conf.QUARANTINED
    assert any("conflicting evidence" in r for r in s.reasons)


def test_value_date_disagreement_is_reported_even_when_dispatched() -> None:
    # The file routes fine, but an operator still needs to know the client's
    # batch schedule has drifted.
    s = conf.compose(
        attribution=good_attr(),
        value_date=good_date(
            mismatch_flagged=True,
            notes="filename says 2026-08-31 but the contents resolve to 2026-08-28",
        ),
        mappings=full_trade_mappings(),
        domain="TRADE",
    )
    assert s.disposition == conf.DISPATCHED
    assert any("value-date disagreement" in r for r in s.reasons)


def test_weak_value_date_evidence_lowers_the_score() -> None:
    strong = conf.compose(
        attribution=good_attr(),
        value_date=good_date(),
        mappings=full_trade_mappings(),
        domain="TRADE",
    )
    weak = conf.compose(
        attribution=good_attr(),
        value_date=good_date(method=METHOD_FILENAME, confidence=0.70),
        mappings=full_trade_mappings(),
        domain="TRADE",
    )
    assert weak.overall < strong.overall


def test_material_fields_outweigh_incidental_ones() -> None:
    # Losing the net amount must hurt more than losing the trade reference.
    without_amount = [m for m in full_trade_mappings() if m.canonical_field != "net_amount"]
    without_ref = [m for m in full_trade_mappings() if m.canonical_field != "trade_date"]
    a = conf.mapping_coverage(without_amount, "TRADE")[0]
    b = conf.mapping_coverage(without_ref, "TRADE")[0]
    assert a < b


def test_coverage_is_measured_against_the_domain(domain: str = "CASH") -> None:
    # A cash statement has no trade price, and must not be penalised for it.
    cash_mappings = [
        Mapping(f"src_{f}", f, c.Tier.ALIAS, 1.0, "alias")
        for f in c.REQUIRED_BY_DOMAIN[c.Domain.CASH]
    ]
    coverage, missing = conf.mapping_coverage(cash_mappings, domain)
    assert coverage == pytest.approx(1.0)
    assert missing == []


def test_unassigned_price_column_produces_a_specific_reason() -> None:
    surplus = Mapping(
        "Mark Price",
        None,
        c.Tier.UNRESOLVED,
        0.0,
        "additional price column, roles already assigned (ratio 0.00)",
    )
    mappings = [*full_trade_mappings(), surplus]
    s = conf.compose(
        attribution=good_attr(confidence=0.5, conflict=True),
        value_date=good_date(),
        mappings=mappings,
        domain="TRADE",
    )
    assert any("Mark Price" in r for r in s.reasons)


def test_reasons_are_specific_not_generic() -> None:
    # "Low confidence" trains reviewers to click through. Every reason must
    # name what was uncertain.
    partial = [m for m in full_trade_mappings() if m.canonical_field != "quantity"]
    s = conf.compose(
        attribution=good_attr(), value_date=good_date(), mappings=partial, domain="TRADE"
    )
    assert s.reasons
    for r in s.reasons:
        assert r.lower() != "low confidence"
        assert len(r) > 20


def test_thresholds_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HM_CONF_DISPATCH", "0.99")
    s = conf.compose(
        attribution=good_attr(confidence=0.9),
        value_date=good_date(),
        mappings=full_trade_mappings(0.9),
        domain="TRADE",
    )
    assert s.disposition == conf.QUARANTINED


def test_invalid_threshold_falls_back_to_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HM_CONF_DISPATCH", "not-a-number")
    assert conf.dispatch_threshold() == pytest.approx(0.85)
    monkeypatch.setenv("HM_CONF_DISPATCH", "3.5")
    assert conf.dispatch_threshold() == pytest.approx(0.85)
