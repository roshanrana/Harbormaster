"""Composing one confidence score, and deciding what to do with it.

Three independent judgements have been made by the time this runs: which client
the file belongs to, what business day it represents, and how the columns map.
Each carries its own confidence. This module combines them and routes the
arrival to dispatch, quarantine or rejection.

Two things are deliberate.

Weighting is by economic consequence, not by field count. A file where every
identifier mapped cleanly but the net amount did not is far more dangerous than
the reverse, because a mis-mapped amount produces a wrong reconciliation while a
mis-mapped trade reference produces a findable one. Material fields therefore
carry three times the weight of incidental ones.

Quarantine reasons are specific. "Low confidence" tells a reviewer nothing and
trains them to click through. Every reason produced here names what was
uncertain and what the alternatives were, because the reviewer's job is to
resolve exactly that question.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from inspector.attribution import Attribution
from inspector.mapping import canonical as c
from inspector.mapping.tier1 import Mapping
from inspector.valuedate import Resolution

# Disposition values, matching the proto enum.
DISPATCHED = "DISPATCHED"
QUARANTINED = "QUARANTINED"
REJECTED = "REJECTED"

# Component weights. Client and value date matter most because getting either
# wrong invalidates the whole reconciliation regardless of how well the columns
# were mapped.
W_CLIENT = 0.35
W_VALUE_DATE = 0.35
W_MAPPING = 0.30


def _threshold(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if 0.0 <= value <= 1.0 else default


def dispatch_threshold() -> float:
    return _threshold("HM_CONF_DISPATCH", 0.85)


def quarantine_threshold() -> float:
    return _threshold("HM_CONF_QUARANTINE", 0.60)


@dataclass(slots=True)
class Score:
    """The composed confidence and the routing decision it implies."""

    overall: float
    client: float
    value_date: float
    mapping_coverage: float
    disposition: str
    reasons: list[str] = field(default_factory=list)
    unmapped_required: list[str] = field(default_factory=list)


def mapping_coverage(mappings: list[Mapping], domain: str) -> tuple[float, list[str]]:
    """Weighted coverage of the fields this domain actually requires.

    Scoring a cash statement against trade-specific fields would quarantine
    every cash file ever sent, so the required set is per domain.
    """
    required = c.REQUIRED_BY_DOMAIN.get(c.Domain(domain), frozenset())
    if not required:
        return 1.0, []

    resolved = {m.canonical_field: m for m in mappings if m.canonical_field}
    total_weight = 0.0
    earned = 0.0
    missing: list[str] = []

    for field_name in sorted(required):
        weight = float(c.FIELD_WEIGHTS.get(field_name, c.DEFAULT_FIELD_WEIGHT))
        total_weight += weight
        m = resolved.get(field_name)
        if m is None:
            missing.append(field_name)
            continue
        earned += weight * m.confidence

    coverage = earned / total_weight if total_weight else 1.0
    return round(coverage, 4), missing


def compose(
    *,
    attribution: Attribution,
    value_date: Resolution,
    mappings: list[Mapping],
    domain: str,
) -> Score:
    """Combine the three judgements and decide the disposition."""
    coverage, missing = mapping_coverage(mappings, domain)
    client_conf = attribution.confidence
    date_conf = value_date.confidence if value_date.resolved else 0.0

    overall = W_CLIENT * client_conf + W_VALUE_DATE * date_conf + W_MAPPING * coverage
    overall = round(overall, 4)

    reasons: list[str] = []

    if not attribution.resolved:
        reasons.append("client could not be determined: " + "; ".join(attribution.evidence))
    elif attribution.conflict:
        reasons.append(
            f"conflicting evidence for client {attribution.client_id}: "
            + "; ".join(attribution.evidence)
        )

    if value_date.resolved is None:
        reasons.append("value date could not be determined")
    else:
        if value_date.mismatch_flagged:
            # Not on its own a reason to hold the file, but the reviewer needs
            # to see it, and it is what an operator will be asked about later.
            reasons.append(f"value-date disagreement: {value_date.notes}")
        if date_conf < 0.7:
            reasons.append(
                f"value date rests on weak evidence ({value_date.method}, "
                f"confidence {date_conf:.2f})"
            )

    for name in missing:
        reasons.append(f"required field {name!r} for domain {domain} was not mapped")

    weak = [
        m
        for m in mappings
        if m.canonical_field
        and m.canonical_field in c.REQUIRED_BY_DOMAIN.get(c.Domain(domain), frozenset())
        and m.confidence < 0.7
    ]
    for m in weak:
        reasons.append(
            f"{m.canonical_field} mapped from {m.source_field!r} on weak evidence: {m.evidence}"
        )

    ambiguous_prices = [
        m for m in mappings if m.canonical_field is None and "price" in m.evidence.lower()
    ]
    for m in ambiguous_prices:
        reasons.append(f"price column {m.source_field!r} left unassigned: {m.evidence}")

    disposition = _route(overall, attribution, value_date, missing)
    if disposition == DISPATCHED:
        # A dispatched arrival keeps its notes for the audit record but has no
        # outstanding questions, so nothing here is a review reason.
        reasons = [r for r in reasons if r.startswith("value-date disagreement")]

    return Score(
        overall=overall,
        client=client_conf,
        value_date=date_conf,
        mapping_coverage=coverage,
        disposition=disposition,
        reasons=reasons,
        unmapped_required=missing,
    )


def _route(
    overall: float, attribution: Attribution, value_date: Resolution, missing: list[str]
) -> str:
    """Decide the disposition.

    Some conditions are disqualifying regardless of the composite score. A file
    with no client cannot be routed anywhere no matter how cleanly its columns
    mapped, and averaging that away would be how a well-formed file for an
    unknown counterparty gets dispatched to the wrong reconciliation.
    """
    if not attribution.resolved or value_date.resolved is None:
        return QUARANTINED if overall >= quarantine_threshold() / 2 else REJECTED
    if missing:
        return QUARANTINED
    if overall >= dispatch_threshold():
        return DISPATCHED
    if overall >= quarantine_threshold():
        return QUARANTINED
    return REJECTED
