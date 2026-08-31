"""Tier 3: the model seam, and the cache that keeps it rarely used.

Escalation reaches here only for headers that the dictionary did not know and
local matching could not resolve with confidence. That should be a small
minority of columns, and after the cache warms it should be a small minority of
*files* (NFR-8 targets two percent).

Three things make that true.

**The interface, not the implementation, is what the pipeline depends on.**
``MappingAdjudicator`` has two implementations: a deterministic fake used by the
entire test suite, and the real Claude adapter. ``make check`` binds the fake,
so the suite runs offline with no API key. A system whose tests require a live
model is a system whose tests get skipped.

**Results are cached by template fingerprint.** The fingerprint is an ordered
hash of the header set plus the client, so the second file with a given layout
costs nothing. Most counterparty files are the same report every day; paying a
model for that repeatedly would be indefensible.

**Confirmed answers are promoted.** A reviewer approving a Tier 3 mapping writes
it into the client's ``field_overrides``, after which it resolves at Tier 1
forever. Model dependence therefore decreases as the system runs, rather than
growing with volume.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from inspector.mapping import canonical as c


@dataclass(slots=True)
class AdjudicationRequest:
    """Everything the adjudicator is given about an unresolved column set."""

    client_id: str
    client_name: str
    source_hint: str
    domain: str
    template_fingerprint: str
    unresolved_headers: list[str]
    #: Headers already resolved, so the adjudicator can reason about what is
    #: left rather than re-deciding settled questions.
    resolved: dict[str, str] = field(default_factory=dict)
    #: A few sample rows keyed by header. Values are far more informative than
    #: names when a header is opaque.
    samples: dict[str, list[str]] = field(default_factory=dict)
    candidate_fields: list[str] = field(default_factory=lambda: sorted(c.MAPPABLE_FIELDS))


@dataclass(slots=True)
class AdjudicatedField:
    source_field: str
    canonical_field: str | None
    confidence: float
    rationale: str


@dataclass(slots=True)
class AdjudicationResult:
    fields: list[AdjudicatedField]
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    def as_map(self) -> dict[str, AdjudicatedField]:
        return {f.source_field: f for f in self.fields}


class MappingAdjudicator(Protocol):
    """The Tier 3 seam."""

    name: str

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationResult: ...


class DeterministicFake:
    """A stand-in adjudicator for offline runs.

    It does not pretend to be clever. It applies a small set of substring rules
    over the header and, failing that, looks at the sample values to decide
    whether a column is a date, a currency code or a number. That is enough to
    exercise every downstream path — caching, promotion, confidence, review —
    without a network call, and its determinism means golden tests stay stable.

    It deliberately declines rather than guessing when nothing matches, because
    the behaviour under test is what happens when Tier 3 *cannot* answer.
    """

    name = "deterministic-fake"

    _RULES: tuple[tuple[tuple[str, ...], str], ...] = (
        (("settl", "close", "mtm", "mark", "official", "eod"), "settlement_price"),
        (("exec", "fill", "deal", "traded", "lastpx", "avgpx"), "trade_price"),
        (("qty", "quantity", "unit", "share", "contract", "nominal", "volume"), "quantity"),
        (("net", "proceed", "consider", "cash", "amount", "money"), "net_amount"),
        (("gross", "principal"), "gross_amount"),
        (("mkt", "market", "valuation", "fair"), "market_value"),
        (("ccy", "curr"), "currency"),
        (("acct", "account", "portfolio", "custody", "book"), "account_id"),
        (("isin", "cusip", "sedol", "symbol", "ticker", "instrument", "security"), "instrument_id"),
        (("side", "buysell", "direction", "longshort"), "side"),
        (("trddt", "tradedate", "dealdate", "execdate"), "trade_date"),
    )

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationResult:
        taken = set(request.resolved.values())
        out: list[AdjudicatedField] = []

        for header in request.unresolved_headers:
            normalized = c.normalize_header(header)
            decided: str | None = None
            rationale = ""

            for tokens, canonical_field in self._RULES:
                if canonical_field in taken:
                    continue
                hit = next((t for t in tokens if t in normalized), None)
                if hit:
                    decided, rationale = canonical_field, f"header contains {hit!r}"
                    break

            if decided is None:
                decided, rationale = self._from_samples(request.samples.get(header, []), taken)

            if decided is None:
                out.append(
                    AdjudicatedField(header, None, 0.0, "no rule or sample evidence applied")
                )
                continue

            taken.add(decided)
            out.append(AdjudicatedField(header, decided, 0.80, rationale))

        return AdjudicationResult(fields=out, model=self.name)

    def _from_samples(self, samples: list[str], taken: set[str]) -> tuple[str | None, str]:
        values = [s.strip() for s in samples if s and s.strip()]
        if not values:
            return None, ""
        if (
            all(len(v) == 3 and v.isalpha() and v.isupper() for v in values)
            and "currency" not in taken
        ):
            return "currency", "sample values are three-letter uppercase codes"
        if all(_looks_like_date(v) for v in values) and "trade_date" not in taken:
            return "trade_date", "sample values parse as dates"
        return None, ""


def _looks_like_date(value: str) -> bool:
    from inspector.valuedate import parse_date

    return parse_date(value) is not None


# --- cache -----------------------------------------------------------------


class TemplateCache(Protocol):
    """Stores adjudicated mappings by template fingerprint."""

    def get(self, fingerprint: str, client_id: str) -> dict[str, str] | None: ...

    def put(
        self,
        fingerprint: str,
        client_id: str,
        mappings: dict[str, str],
        tier: str,
        confirmed_by: str | None = None,
    ) -> None: ...


class InMemoryCache:
    """Process-local cache. Used by tests and as a fallback."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict[str, str]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, fingerprint: str, client_id: str) -> dict[str, str] | None:
        value = self._store.get((fingerprint, client_id))
        if value is None:
            self.misses += 1
            return None
        self.hits += 1
        return dict(value)

    def put(
        self,
        fingerprint: str,
        client_id: str,
        mappings: dict[str, str],
        tier: str,
        confirmed_by: str | None = None,
    ) -> None:
        del tier, confirmed_by
        self._store[(fingerprint, client_id)] = dict(mappings)


class PostgresCache:
    """Durable cache in the ``template_mapping`` table.

    Shared across Inspector instances on purpose. A per-process cache would
    mean the model cost scales with how many consumers happen to be running,
    which is exactly the wrong dependency.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.hits = 0
        self.misses = 0

    def _connect(self) -> Any:
        import psycopg

        return psycopg.connect(self.dsn)

    def get(self, fingerprint: str, client_id: str) -> dict[str, str] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT mappings FROM template_mapping "
                "WHERE template_fingerprint = %s AND client_id = %s",
                (fingerprint, client_id),
            )
            row = cur.fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        payload = row[0]
        return json.loads(payload) if isinstance(payload, str) else dict(payload)

    def put(
        self,
        fingerprint: str,
        client_id: str,
        mappings: dict[str, str],
        tier: str,
        confirmed_by: str | None = None,
    ) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO template_mapping "
                "(template_fingerprint, client_id, mappings, tier, confirmed_by) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (template_fingerprint, client_id) DO UPDATE SET "
                "mappings = EXCLUDED.mappings, tier = EXCLUDED.tier, "
                "confirmed_by = EXCLUDED.confirmed_by",
                (fingerprint, client_id, json.dumps(mappings), tier, confirmed_by),
            )
            conn.commit()


def promotable(result: AdjudicationResult, min_confidence: float = 0.75) -> dict[str, str]:
    """Mappings a reviewer could promote into a client's field_overrides.

    Promotion is never automatic (FR-28). A model answer that nobody checked
    becoming permanent configuration is how a single bad inference outlives
    everyone who could explain it.
    """
    return {
        f.source_field: f.canonical_field
        for f in result.fields
        if f.canonical_field and f.confidence >= min_confidence
    }
