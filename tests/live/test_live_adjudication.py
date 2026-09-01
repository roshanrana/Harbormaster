"""Opt-in test against the real Anthropic API.

Skipped unless both HM_LIVE=1 and ANTHROPIC_API_KEY are set, so `make check`
never touches the network. This is the last thing exercised in the build for a
reason: everything else must be correct before a model is introduced, or a
model failure and a logic failure become indistinguishable.

Run with:  HM_LIVE=1 make test-live
"""

from __future__ import annotations

import os

import pytest

from inspector.mapping.tier3 import AdjudicationRequest
from inspector.mapping.tier3_llm import ClaudeAdjudicator

pytestmark = pytest.mark.skipif(
    os.environ.get("HM_LIVE") != "1" or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="set HM_LIVE=1 and ANTHROPIC_API_KEY to run live tests",
)


@pytest.fixture(scope="module")
def adjudicator() -> ClaudeAdjudicator:
    return ClaudeAdjudicator()


def test_genuinely_novel_headers_are_mapped(adjudicator: ClaudeAdjudicator) -> None:
    """Headers no dictionary would have and no fuzzy match would reach.

    This is the case Tier 3 exists for: a client's internal shorthand that
    means something obvious to a human and nothing to a string matcher.
    """
    request = AdjudicationRequest(
        client_id="CLNT004",
        client_name="Meridian Capital Partners",
        source_hint="CME",
        domain="TRADE",
        template_fingerprint="tf_live",
        unresolved_headers=["Fld_A7", "Fld_B2", "Fld_C9"],
        resolved={"Account ID": "account_id", "Symbol": "instrument_id"},
        samples={
            # Varies per row, four decimal places: an execution price.
            "Fld_A7": ["5401.2500", "5402.7500", "5400.1250", "5403.5000"],
            # Repeats for the instrument: a settlement price.
            "Fld_B2": ["5399.5000", "5399.5000", "5399.5000", "5399.5000"],
            # Three-letter uppercase codes: a currency.
            "Fld_C9": ["USD", "USD", "USD", "USD"],
        },
    )
    result = adjudicator.adjudicate(request)
    answers = result.as_map()

    assert answers["Fld_C9"].canonical_field == "currency"
    assert answers["Fld_A7"].canonical_field == "trade_price"
    assert answers["Fld_B2"].canonical_field == "settlement_price"
    for field in answers.values():
        assert field.rationale, "every decision must carry a rationale"
        assert field.confidence <= 0.85


def test_no_canonical_field_is_used_twice(adjudicator: ClaudeAdjudicator) -> None:
    request = AdjudicationRequest(
        client_id="CLNT004", client_name="Meridian", source_hint="CME", domain="TRADE",
        template_fingerprint="tf_live2",
        unresolved_headers=["Amt_1", "Amt_2", "Amt_3"],
        samples={
            "Amt_1": ["54012.50", "27013.75"],
            "Amt_2": ["54000.00", "27000.00"],
            "Amt_3": ["54100.00", "27100.00"],
        },
    )
    assigned = [
        f.canonical_field for f in adjudicator.adjudicate(request).fields if f.canonical_field
    ]
    assert len(assigned) == len(set(assigned)), f"duplicate assignment: {assigned}"


def test_unmappable_column_is_declined(adjudicator: ClaudeAdjudicator) -> None:
    """Declining is a correct answer, and a wrong mapping is far worse."""
    request = AdjudicationRequest(
        client_id="CLNT004", client_name="Meridian", source_hint="CME", domain="TRADE",
        template_fingerprint="tf_live3",
        unresolved_headers=["Internal_Batch_Seq"],
        samples={"Internal_Batch_Seq": ["1", "2", "3", "4", "5"]},
    )
    field = adjudicator.adjudicate(request).as_map()["Internal_Batch_Seq"]
    assert field.canonical_field is None, f"invented a mapping: {field.canonical_field}"


def test_cost_is_recorded(adjudicator: ClaudeAdjudicator) -> None:
    """NFR-8's escalation budget is measured, not asserted."""
    request = AdjudicationRequest(
        client_id="CLNT004", client_name="Meridian", source_hint="CME", domain="TRADE",
        template_fingerprint="tf_live4", unresolved_headers=["Fld_X"],
        samples={"Fld_X": ["GBP", "GBP"]},
    )
    adjudicator.adjudicate(request)
    assert adjudicator.usage.calls >= 1
    assert adjudicator.usage.input_tokens > 0
    print(
        f"\nlive usage: {adjudicator.usage.calls} calls, "
        f"{adjudicator.usage.input_tokens} in / {adjudicator.usage.output_tokens} out, "
        f"{adjudicator.usage.cache_read_tokens} cached, "
        f"mean {adjudicator.usage.mean_latency_ms:.0f}ms"
    )
