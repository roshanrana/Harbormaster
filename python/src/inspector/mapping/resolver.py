"""The escalation ladder.

Tier 1 resolves what it can, Tier 2 takes the residue, Tier 3 takes what is
left after that. This module is the only place that knows the order, so the
policy lives in one readable function rather than being spread across three
matchers.

The invariant worth stating: escalation is one-way and each tier only ever sees
columns the previous tier declined. A column resolved by the dictionary is
never re-litigated by a model, which is what keeps the cost bounded and the
behaviour reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

from inspector.mapping import canonical as c
from inspector.mapping.tier1 import Mapping, Tier1Mapper
from inspector.mapping.tier2 import Tier2Matcher
from inspector.mapping.tier3 import (
    AdjudicationRequest,
    InMemoryCache,
    MappingAdjudicator,
    TemplateCache,
)
from inspector.parsers.base import ParsedTable

# How many sample values to show the adjudicator per column. Enough to reveal
# whether a column is a date, a code or an amount; few enough to keep the
# prompt small and the cost predictable.
SAMPLE_ROWS = 5


@dataclass(slots=True)
class ResolutionOutcome:
    mappings: list[Mapping]
    tier2_used: int = 0
    tier3_used: int = 0
    cache_hit: bool = False
    degraded: bool = False
    promotable: dict[str, str] | None = None


class TieredResolver:
    """Runs the full escalation for one table."""

    def __init__(
        self,
        *,
        field_overrides: dict[str, str] | None = None,
        tier2: Tier2Matcher | None = None,
        adjudicator: MappingAdjudicator | None = None,
        cache: TemplateCache | None = None,
    ) -> None:
        self.tier1 = Tier1Mapper(field_overrides)
        self.tier2 = tier2 if tier2 is not None else Tier2Matcher()
        self.adjudicator = adjudicator
        self.cache = cache if cache is not None else InMemoryCache()

    def resolve(
        self,
        table: ParsedTable,
        *,
        client_id: str,
        client_name: str = "",
        source_hint: str = "",
        domain: str = "UNKNOWN",
        template_fingerprint: str = "",
    ) -> ResolutionOutcome:
        mappings = self.tier1.map_table(table)
        outcome = ResolutionOutcome(mappings=mappings)

        cached = (
            self.cache.get(template_fingerprint, client_id)
            if template_fingerprint and client_id
            else None
        )
        if cached:
            # A previously adjudicated layout costs nothing the second time.
            outcome.cache_hit = True
            self._apply(mappings, cached, c.Tier.LLM, 0.80, "cached adjudication for this template")

        unresolved = self._unresolved(mappings)
        if unresolved:
            self._run_tier2(mappings, unresolved, outcome)

        unresolved = self._unresolved(mappings)
        if unresolved and self.adjudicator is not None and not outcome.cache_hit:
            self._run_tier3(
                mappings,
                unresolved,
                table,
                outcome,
                client_id=client_id,
                client_name=client_name,
                source_hint=source_hint,
                domain=domain,
                template_fingerprint=template_fingerprint,
            )

        outcome.degraded = self.tier2.degraded
        return outcome

    # --- stages ------------------------------------------------------------

    def _run_tier2(
        self, mappings: list[Mapping], unresolved: list[Mapping], outcome: ResolutionOutcome
    ) -> None:
        for m in unresolved:
            taken = self._claimed(mappings)
            match = self.tier2.match(m.source_field, exclude=taken)
            if match.canonical_field is None:
                # Keep the Tier 2 reasoning even on a decline: it is what tells
                # a reviewer why the column escalated.
                m.evidence = f"{m.evidence}; tier2: {match.evidence}"
                continue
            m.canonical_field = match.canonical_field
            m.tier = c.Tier.LOCAL
            m.confidence = match.confidence
            m.evidence = match.evidence
            outcome.tier2_used += 1

    def _run_tier3(
        self,
        mappings: list[Mapping],
        unresolved: list[Mapping],
        table: ParsedTable,
        outcome: ResolutionOutcome,
        *,
        client_id: str,
        client_name: str,
        source_hint: str,
        domain: str,
        template_fingerprint: str,
    ) -> None:
        assert self.adjudicator is not None
        resolved = {
            m.source_field: m.canonical_field for m in mappings if m.canonical_field is not None
        }
        request = AdjudicationRequest(
            client_id=client_id,
            client_name=client_name,
            source_hint=source_hint,
            domain=domain,
            template_fingerprint=template_fingerprint,
            unresolved_headers=[m.source_field for m in unresolved],
            resolved=resolved,
            samples={
                m.source_field: table.column(m.source_field)[:SAMPLE_ROWS] for m in unresolved
            },
        )
        result = self.adjudicator.adjudicate(request)
        answers = result.as_map()

        for m in unresolved:
            answer = answers.get(m.source_field)
            if answer is None or answer.canonical_field is None:
                m.evidence = f"{m.evidence}; tier3 declined"
                continue
            if answer.canonical_field in self._claimed(mappings):
                m.evidence = (
                    f"{m.evidence}; tier3 proposed {answer.canonical_field} "
                    "but it was already assigned"
                )
                continue
            m.canonical_field = answer.canonical_field
            m.tier = c.Tier.LLM
            m.confidence = answer.confidence
            m.evidence = f"{result.model}: {answer.rationale}"
            outcome.tier3_used += 1

        if outcome.tier3_used and template_fingerprint and client_id:
            learned = {
                m.source_field: m.canonical_field
                for m in mappings
                if m.tier == c.Tier.LLM and m.canonical_field
            }
            # Cached so the next file with this layout skips Tier 3 entirely.
            # Promotion into client configuration still requires a human.
            self.cache.put(template_fingerprint, client_id, learned, tier="LLM")
            outcome.promotable = learned

    # --- helpers -----------------------------------------------------------

    def _unresolved(self, mappings: list[Mapping]) -> list[Mapping]:
        return [m for m in mappings if m.canonical_field is None]

    def _claimed(self, mappings: list[Mapping]) -> set[str]:
        return {m.canonical_field for m in mappings if m.canonical_field}

    def _apply(
        self,
        mappings: list[Mapping],
        learned: dict[str, str],
        tier: c.Tier,
        confidence: float,
        evidence: str,
    ) -> None:
        taken = self._claimed(mappings)
        for m in mappings:
            if m.canonical_field is not None:
                continue
            candidate = learned.get(m.source_field)
            if candidate and candidate not in taken:
                m.canonical_field = candidate
                m.tier = tier
                m.confidence = confidence
                m.evidence = evidence
                taken.add(candidate)
