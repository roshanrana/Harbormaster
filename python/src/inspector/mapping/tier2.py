"""Tier 2: local matching for headers the dictionary did not recognise.

Tier 1 resolves the columns the industry already has a name for. What is left
is the long tail: abbreviations nobody standardised, a client's internal
shorthand, a vendor's export that renamed everything slightly.

Two signals are combined here, because each fails differently:

- **Fuzzy string similarity** catches near-misses and typos. ``Settlment Amt``
  is one transposition away from a known alias, and rapidfuzz sees that.
  It is useless when the wording is different but the meaning is the same.
- **Semantic similarity** over sentence embeddings catches exactly that case.
  ``Consideration`` shares no characters with ``net amount`` but sits near it
  in embedding space.

Neither alone is sufficient and combining them is cheap, so both run and the
higher-confidence answer wins, with agreement between them treated as
corroboration.

The embedding model is optional (ADR-013). If ``fastembed`` is not installed the
tier degrades to fuzzy-only and *records that it did*. A system that silently
becomes less capable when a dependency is missing is worse than one that fails,
because nobody finds out until the mappings quietly get worse.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz, process

from inspector.mapping import canonical as c

# What each canonical field means, in words. These are the targets Tier 2
# scores against: the semantic matcher needs a description, not a label.
FIELD_DESCRIPTIONS: dict[str, str] = {
    "account_id": "the client account or portfolio identifier the record belongs to",
    "account_name": "the human readable name of the account or fund",
    "trade_id": "the unique reference identifying this trade or transaction",
    "instrument_id": "the security identifier, ticker, ISIN, CUSIP or contract code",
    "instrument_type": "the asset class or product type of the security",
    "trade_date": "the date the trade was executed or booked",
    "quantity": "the number of shares, units, contracts or nominal amount",
    "trade_price": "the price at which the trade was executed",
    "settlement_price": "the official closing, settlement or mark to market price",
    "gross_amount": "the gross consideration or principal before fees",
    "net_amount": "the net cash amount, proceeds or settlement value",
    "market_value": "the current market or fair value of the position",
    "currency": "the ISO currency code the amounts are denominated in",
    "side": "whether the transaction is a buy or a sell, long or short",
    "source_system": "the venue, exchange or system the record originated from",
}

# Below this, escalate rather than guess. Set deliberately high: a wrong
# mapping is more expensive than an unresolved one, because an unresolved
# column becomes a review item while a wrong one becomes a silent break.
MIN_ACCEPT = 0.72

# Fuzzy scores are capped below the alias tier so provenance stays meaningful:
# a Tier 2 answer should never look as certain as a dictionary hit.
_MAX_CONFIDENCE = 0.88

_FUZZY_WEIGHT = 0.55
_SEMANTIC_WEIGHT = 0.45

# Agreement between the two signals is genuine corroboration and earns a bonus.
_AGREEMENT_BONUS = 0.06


@dataclass(slots=True)
class LocalMatch:
    canonical_field: str | None
    confidence: float
    evidence: str
    degraded: bool = False


def _readable(header: str) -> str:
    """Turn a header into something a semantic model can work with.

    ``Px_Sett`` and ``NetSettlValue`` are not sentences. Splitting on case
    boundaries and separators gives the embedding something to grip.
    """
    out: list[str] = []
    buffer = ""
    for ch in header:
        if ch in "_-./\\|":
            if buffer:
                out.append(buffer)
                buffer = ""
            continue
        if ch.isupper() and buffer and not buffer[-1].isupper():
            out.append(buffer)
            buffer = ch
            continue
        buffer += ch
    if buffer:
        out.append(buffer)
    return " ".join(part.lower() for part in out if part).strip() or header.lower()


class EmbeddingMatcher:
    """Semantic similarity over ONNX MiniLM embeddings.

    Loaded lazily and never required. ``available`` tells the caller whether
    this signal is present so the degradation is visible rather than implied.
    """

    def __init__(self) -> None:
        # Typed as Any because fastembed is an optional dependency and must
        # not be importable at type-check time (ADR-013).
        self._model: Any = None
        self._vectors: dict[str, list[float]] = {}
        self._failed = False

    @property
    def available(self) -> bool:
        if self._failed:
            return False
        if self._model is not None:
            return True
        return self._load()

    def _load(self) -> bool:
        try:
            from fastembed import TextEmbedding  # type: ignore[import-not-found]
        except ImportError:
            self._failed = True
            return False
        try:
            self._model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            texts = list(FIELD_DESCRIPTIONS.values())
            fields = list(FIELD_DESCRIPTIONS.keys())
            embeddings = list(self._model.embed(texts))
            self._vectors = {
                field: list(vector) for field, vector in zip(fields, embeddings, strict=True)
            }
        except Exception:
            self._failed = True
            self._model = None
            return False
        return True

    def best(self, header: str) -> tuple[str | None, float]:
        if not self.available or self._model is None:
            return None, 0.0
        try:
            vector = list(next(iter(self._model.embed([_readable(header)]))))
        except Exception:
            self._failed = True
            return None, 0.0

        best_field, best_score = None, -1.0
        for field, candidate in self._vectors.items():
            score = _cosine(vector, candidate)
            if score > best_score:
                best_field, best_score = field, score
        return best_field, max(0.0, best_score)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


@functools.lru_cache(maxsize=1)
def _alias_corpus() -> list[tuple[str, str]]:
    """Every known alias paired with its canonical field, for fuzzy search."""
    pairs: list[tuple[str, str]] = []
    for field, aliases in c.FIELD_ALIASES.items():
        if field not in c.MAPPABLE_FIELDS:
            continue
        pairs.append((field, field))
        pairs.extend((alias, field) for alias in aliases)
    return pairs


class Tier2Matcher:
    """Fuzzy plus semantic matching for unresolved headers."""

    def __init__(self, embeddings: EmbeddingMatcher | None = None) -> None:
        self.embeddings = embeddings if embeddings is not None else EmbeddingMatcher()

    @property
    def degraded(self) -> bool:
        """True when the semantic signal is unavailable."""
        return not self.embeddings.available

    def match(self, header: str, *, exclude: set[str] | None = None) -> LocalMatch:
        """Resolve one header, or decline."""
        taken = exclude or set()
        fuzzy_field, fuzzy_score = self._fuzzy(header, taken)
        semantic_field, semantic_score = self.embeddings.best(header)
        if semantic_field in taken:
            semantic_field, semantic_score = None, 0.0

        degraded = self.degraded

        if semantic_field is None:
            # Fuzzy-only. Discounted, because one signal corroborating nothing
            # is weaker evidence than two agreeing.
            confidence = min(fuzzy_score * 0.92, _MAX_CONFIDENCE)
            if fuzzy_field is None or confidence < MIN_ACCEPT:
                return LocalMatch(
                    None,
                    0.0,
                    f"no local match above {MIN_ACCEPT:.2f} "
                    f"(best fuzzy {fuzzy_score:.2f}"
                    + (", semantic matcher unavailable" if degraded else "")
                    + ")",
                    degraded=degraded,
                )
            return LocalMatch(
                fuzzy_field,
                round(confidence, 3),
                f"fuzzy match to alias vocabulary at {fuzzy_score:.2f}"
                + (" (semantic matcher unavailable)" if degraded else ""),
                degraded=degraded,
            )

        if fuzzy_field == semantic_field:
            combined = _FUZZY_WEIGHT * fuzzy_score + _SEMANTIC_WEIGHT * semantic_score
            combined = min(combined + _AGREEMENT_BONUS, _MAX_CONFIDENCE)
            evidence = (
                f"fuzzy and semantic agree on {semantic_field} "
                f"(fuzzy {fuzzy_score:.2f}, semantic {semantic_score:.2f})"
            )
        elif fuzzy_score >= semantic_score:
            combined = min(fuzzy_score * 0.92, _MAX_CONFIDENCE)
            field = fuzzy_field
            evidence = (
                f"fuzzy match at {fuzzy_score:.2f}; semantic preferred "
                f"{semantic_field} at {semantic_score:.2f}"
            )
            if field is None or combined < MIN_ACCEPT:
                return LocalMatch(
                    None, 0.0, "fuzzy and semantic disagree below threshold", degraded=degraded
                )
            return LocalMatch(field, round(combined, 3), evidence, degraded=degraded)
        else:
            combined = min(semantic_score * 0.92, _MAX_CONFIDENCE)
            evidence = (
                f"semantic match at {semantic_score:.2f}; fuzzy preferred "
                f"{fuzzy_field} at {fuzzy_score:.2f}"
            )

        if combined < MIN_ACCEPT:
            return LocalMatch(
                None,
                0.0,
                f"best local candidate {semantic_field} scored {combined:.2f}, "
                f"below the {MIN_ACCEPT:.2f} threshold",
                degraded=degraded,
            )
        return LocalMatch(semantic_field, round(combined, 3), evidence, degraded=degraded)

    def _fuzzy(self, header: str, taken: set[str]) -> tuple[str | None, float]:
        normalized = c.normalize_header(header)
        if not normalized:
            return None, 0.0
        candidates = [(alias, field) for alias, field in _alias_corpus() if field not in taken]
        if not candidates:
            return None, 0.0
        result: Any = process.extractOne(
            normalized,
            [alias for alias, _ in candidates],
            scorer=fuzz.token_set_ratio,
        )
        if result is None:
            return None, 0.0
        score = float(result[1])
        index = int(result[2])
        return candidates[index][1], score / 100.0
