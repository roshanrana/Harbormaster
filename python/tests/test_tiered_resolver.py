"""The three-tier escalation ladder."""

from __future__ import annotations

import pytest

from inspector.mapping import canonical as c
from inspector.mapping.resolver import TieredResolver
from inspector.mapping.tier2 import EmbeddingMatcher, Tier2Matcher
from inspector.mapping.tier3 import (
    AdjudicatedField,
    AdjudicationRequest,
    AdjudicationResult,
    DeterministicFake,
    InMemoryCache,
    promotable,
)
from inspector.parsers.base import ParsedTable


class NoEmbeddings(EmbeddingMatcher):
    """Forces the fuzzy-only degraded path."""

    @property
    def available(self) -> bool:
        return False

    def best(self, header: str) -> tuple[str | None, float]:
        return None, 0.0


class CountingAdjudicator:
    """Wraps the fake so calls can be counted."""

    name = "counting"

    def __init__(self) -> None:
        self.inner = DeterministicFake()
        self.calls = 0
        self.last_request: AdjudicationRequest | None = None

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationResult:
        self.calls += 1
        self.last_request = request
        result = self.inner.adjudicate(request)
        return AdjudicationResult(fields=result.fields, model=self.name)


def table(headers: list[str], rows: list[list[str]]) -> ParsedTable:
    return ParsedTable(headers=headers, rows=[dict(zip(headers, r, strict=True)) for r in rows])


def fuzzy_only_resolver(**kw: object) -> TieredResolver:
    return TieredResolver(tier2=Tier2Matcher(NoEmbeddings()), **kw)  # type: ignore[arg-type]


# --- Tier 2 ----------------------------------------------------------------


def test_tier2_catches_a_misspelled_alias() -> None:
    m = Tier2Matcher(NoEmbeddings()).match("Settlment Amt")
    assert m.canonical_field == "net_amount"
    assert m.confidence >= 0.72
    assert "fuzzy" in m.evidence


def test_tier2_declines_rather_than_guessing() -> None:
    # A wrong mapping is more expensive than an unresolved one: unresolved
    # becomes a review item, wrong becomes a silent break.
    m = Tier2Matcher(NoEmbeddings()).match("Zorblat Factor")
    assert m.canonical_field is None
    assert "threshold" in m.evidence or "no local match" in m.evidence


def test_tier2_confidence_never_reaches_alias_level() -> None:
    # Provenance must stay meaningful: a Tier 2 answer should not look as
    # certain as a dictionary hit.
    m = Tier2Matcher(NoEmbeddings()).match("Quantty")
    assert m.canonical_field == "quantity"
    assert m.confidence < 1.0


def test_tier2_records_when_the_semantic_signal_is_missing() -> None:
    # Silent degradation is worse than failure; nobody finds out until the
    # mappings quietly get worse.
    matcher = Tier2Matcher(NoEmbeddings())
    assert matcher.degraded is True
    m = matcher.match("Settlment Amt")
    assert m.degraded is True
    assert "unavailable" in m.evidence


def test_tier2_will_not_claim_a_field_already_taken() -> None:
    m = Tier2Matcher(NoEmbeddings()).match("Quantty", exclude={"quantity"})
    assert m.canonical_field != "quantity"


# --- Tier 3 fake -----------------------------------------------------------


def test_fake_adjudicator_is_deterministic() -> None:
    request = AdjudicationRequest(
        client_id="CLNT004",
        client_name="Meridian",
        source_hint="CME",
        domain="TRADE",
        template_fingerprint="tf_x",
        unresolved_headers=["Zz_Settl_Val"],
    )
    a = DeterministicFake().adjudicate(request)
    b = DeterministicFake().adjudicate(request)
    assert a.as_map()["Zz_Settl_Val"].canonical_field == b.as_map()["Zz_Settl_Val"].canonical_field


def test_fake_uses_sample_values_when_the_header_is_opaque() -> None:
    request = AdjudicationRequest(
        client_id="C",
        client_name="",
        source_hint="",
        domain="TRADE",
        template_fingerprint="tf",
        unresolved_headers=["Fld7"],
        samples={"Fld7": ["USD", "USD", "EUR"]},
    )
    result = DeterministicFake().adjudicate(request)
    assert result.as_map()["Fld7"].canonical_field == "currency"
    assert "three-letter" in result.as_map()["Fld7"].rationale


def test_fake_declines_when_nothing_applies() -> None:
    request = AdjudicationRequest(
        client_id="C",
        client_name="",
        source_hint="",
        domain="TRADE",
        template_fingerprint="tf",
        unresolved_headers=["Fld9"],
        samples={"Fld9": ["banana", "kiwi"]},
    )
    assert DeterministicFake().adjudicate(request).as_map()["Fld9"].canonical_field is None


def test_promotion_requires_confidence_and_is_never_automatic() -> None:
    result = AdjudicationResult(
        fields=[
            AdjudicatedField("A", "quantity", 0.9, "sure"),
            AdjudicatedField("B", "currency", 0.4, "unsure"),
            AdjudicatedField("C", None, 0.0, "declined"),
        ]
    )
    assert promotable(result) == {"A": "quantity"}


# --- escalation ------------------------------------------------------------


def test_tier1_resolves_without_escalating() -> None:
    adjudicator = CountingAdjudicator()
    t = table(
        ["Account ID", "Symbol", "Qty", "Exec Price", "Net Amount", "CCY"],
        [["8842-00119", "ESZ6", "10", "5401.25", "54012.50", "USD"]],
    )
    outcome = fuzzy_only_resolver(adjudicator=adjudicator).resolve(
        t, client_id="CLNT004", template_fingerprint="tf_1"
    )
    assert adjudicator.calls == 0
    assert outcome.tier3_used == 0
    resolved = {m.canonical_field for m in outcome.mappings if m.canonical_field}
    assert {
        "account_id",
        "instrument_id",
        "quantity",
        "trade_price",
        "net_amount",
        "currency",
    } <= resolved


def test_escalation_is_one_way() -> None:
    # A column the dictionary resolved must never be re-litigated by a model.
    adjudicator = CountingAdjudicator()
    t = table(
        ["Account ID", "Qty", "Zzz_Unknown_Column"],
        [["8842-00119", "10", "banana"], ["8842-00119", "20", "kiwi"]],
    )
    fuzzy_only_resolver(adjudicator=adjudicator).resolve(
        t, client_id="CLNT004", template_fingerprint="tf_2"
    )
    assert adjudicator.last_request is not None
    assert "Account ID" not in adjudicator.last_request.unresolved_headers
    assert "Qty" not in adjudicator.last_request.unresolved_headers


def test_tier3_receives_samples_and_already_resolved_context() -> None:
    adjudicator = CountingAdjudicator()
    t = table(
        ["Account ID", "Xy_9"],
        [["8842-00119", "banana"], ["8842-00119", "kiwi"]],
    )
    fuzzy_only_resolver(adjudicator=adjudicator).resolve(
        t, client_id="CLNT004", template_fingerprint="tf_3"
    )
    req = adjudicator.last_request
    assert req is not None
    assert req.samples["Xy_9"] == ["banana", "kiwi"]
    assert req.resolved["Account ID"] == "account_id"


def test_second_file_with_the_same_layout_costs_nothing() -> None:
    # The cache is what makes the 2 percent target achievable (NFR-8).
    adjudicator = CountingAdjudicator()
    cache = InMemoryCache()
    # "Fld7" is opaque to both the dictionary and fuzzy matching; only the
    # sample values reveal it, so this genuinely reaches Tier 3.
    t = table(["Account ID", "Fld7"], [["8842-00119", "USD"], ["8842-00119", "EUR"]])

    first = fuzzy_only_resolver(adjudicator=adjudicator, cache=cache)
    first.resolve(t, client_id="CLNT004", template_fingerprint="tf_shared")
    calls_after_first = adjudicator.calls

    second = fuzzy_only_resolver(adjudicator=adjudicator, cache=cache)
    outcome = second.resolve(t, client_id="CLNT004", template_fingerprint="tf_shared")

    assert calls_after_first == 1
    assert adjudicator.calls == 1, "the cached layout should not be adjudicated again"
    assert outcome.cache_hit is True
    assert cache.hits == 1


def test_cache_is_scoped_per_client() -> None:
    adjudicator = CountingAdjudicator()
    cache = InMemoryCache()
    t = table(["Account ID", "Fld7"], [["8842-00119", "USD"], ["8842-00119", "EUR"]])
    r = fuzzy_only_resolver(adjudicator=adjudicator, cache=cache)
    r.resolve(t, client_id="CLNT004", template_fingerprint="tf_same")
    r.resolve(t, client_id="CLNT011", template_fingerprint="tf_same")
    assert adjudicator.calls == 2


def test_tier3_cannot_claim_a_field_another_tier_already_took() -> None:
    class GreedyAdjudicator:
        name = "greedy"

        def adjudicate(self, request: AdjudicationRequest) -> AdjudicationResult:
            return AdjudicationResult(
                fields=[
                    AdjudicatedField(h, "quantity", 0.9, "everything is quantity")
                    for h in request.unresolved_headers
                ]
            )

    t = table(["Qty", "Zzz_One", "Zzz_Two"], [["10", "a", "b"], ["20", "c", "d"]])
    outcome = fuzzy_only_resolver(adjudicator=GreedyAdjudicator()).resolve(
        t, client_id="CLNT004", template_fingerprint="tf_4"
    )
    assigned = [m for m in outcome.mappings if m.canonical_field == "quantity"]
    assert len(assigned) == 1
    assert any("already assigned" in m.evidence for m in outcome.mappings if not m.canonical_field)


def test_no_adjudicator_means_no_tier3() -> None:
    # The pipeline must run with the seam unbound.
    t = table(["Account ID", "Zzz"], [["8842-00119", "x"], ["8842-00119", "y"]])
    outcome = fuzzy_only_resolver().resolve(t, client_id="CLNT004", template_fingerprint="tf_5")
    assert outcome.tier3_used == 0
    unresolved = [m for m in outcome.mappings if m.canonical_field is None]
    assert unresolved and all(m.tier == c.Tier.UNRESOLVED for m in unresolved)


def test_declined_columns_keep_their_reasoning() -> None:
    t = table(["Account ID", "Zorblat"], [["8842-00119", "x"], ["8842-00119", "y"]])
    outcome = fuzzy_only_resolver().resolve(t, client_id="CLNT004", template_fingerprint="tf_6")
    declined = next(m for m in outcome.mappings if m.source_field == "Zorblat")
    assert "tier2:" in declined.evidence


@pytest.mark.parametrize("header", ["Px_Sett", "NetSettlValue", "trade-price"])
def test_readable_expansion_helps_opaque_headers(header: str) -> None:
    from inspector.mapping.tier2 import _readable

    expanded = _readable(header)
    assert " " in expanded or expanded.islower()
    assert expanded == expanded.lower()
