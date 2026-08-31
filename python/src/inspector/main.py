"""The Inspector: everything between a raw arrival and a classified one.

The pipeline is deliberately linear and each stage records why it decided what
it did. When an operator asks in three months why a file reconciled against the
28th, the answer has to come out of the audit record rather than out of someone
re-reading this module.

Stages: sniff the format, parse, attribute the client, resolve the value date,
map the columns, score the confidence, split by value date if needed, write
canonical Parquet, publish.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from google.protobuf import timestamp_pb2

from harbormaster.v1 import harbormaster_pb2 as hm
from inspector import attribution as attribution_mod
from inspector import bus, confidence, emit, registry, valuedate
from inspector import logging as hmlog
from inspector.mapping import canonical as c
from inspector.mapping.resolver import TieredResolver
from inspector.mapping.tier1 import Mapping, cross_check_amount
from inspector.mapping.tier3 import MappingAdjudicator, TemplateCache
from inspector.parsers.base import ParsedTable, ParseError, Parser
from inspector.parsers.delimited import DelimitedParser
from inspector.parsers.email_text import EmailTextParser
from inspector.parsers.excel import ExcelParser
from inspector.parsers.fixml import FIXMLParser
from inspector.parsers.json_parser import JSONParser
from inspector.parsers.xml_parser import XMLParser

# Registration order is irrelevant: the parser with the highest sniff score
# wins, and every parser scores on content rather than on the filename (FR-17).
DEFAULT_PARSERS: tuple[type, ...] = (
    DelimitedParser,
    ExcelParser,
    XMLParser,
    FIXMLParser,
    JSONParser,
    EmailTextParser,
)

_TIER_ENUM = {
    c.Tier.ALIAS: hm.RESOLUTION_TIER_ALIAS,
    c.Tier.LOCAL: hm.RESOLUTION_TIER_LOCAL,
    c.Tier.LLM: hm.RESOLUTION_TIER_LLM,
    c.Tier.HUMAN: hm.RESOLUTION_TIER_HUMAN,
    c.Tier.UNRESOLVED: hm.RESOLUTION_TIER_UNRESOLVED,
}

_DISPOSITION_ENUM = {
    confidence.DISPATCHED: hm.ARRIVAL_DISPOSITION_DISPATCHED,
    confidence.QUARANTINED: hm.ARRIVAL_DISPOSITION_QUARANTINED,
    confidence.REJECTED: hm.ARRIVAL_DISPOSITION_REJECTED,
}

_FORMAT_ENUM = {
    "CSV": hm.SOURCE_FORMAT_CSV,
    "EXCEL": hm.SOURCE_FORMAT_EXCEL,
    "XML": hm.SOURCE_FORMAT_XML,
    "FIXML": hm.SOURCE_FORMAT_FIXML,
    "EMAIL_TEXT": hm.SOURCE_FORMAT_EMAIL_TEXT,
    "JSON": hm.SOURCE_FORMAT_JSON,
}

_DOMAIN_ENUM = {
    "TRADE": hm.PRODUCT_DOMAIN_TRADE,
    "POSITION": hm.PRODUCT_DOMAIN_POSITION,
    "CASH": hm.PRODUCT_DOMAIN_CASH,
    "COLLATERAL": hm.PRODUCT_DOMAIN_COLLATERAL,
    "UNKNOWN": hm.PRODUCT_DOMAIN_UNSPECIFIED,
}

# How many bytes to read when deciding the format. Enough to see structure,
# small enough that sniffing a 2 GB file costs nothing.
SNIFF_BYTES = 64 * 1024


@dataclass(slots=True)
class Classification:
    """Everything the Inspector concluded about one arrival."""

    arrival_id: str
    source_format: str
    client_id: str | None
    attribution: attribution_mod.Attribution
    value_date: valuedate.Resolution
    domain: str
    mappings: list[Mapping]
    score: confidence.Score
    table: ParsedTable
    template_fingerprint: str
    canonical_uri: str = ""
    row_count: int = 0
    sub_batch_index: int = 0
    sub_batch_total: int = 1
    cross_check: str = ""


def template_fingerprint(client_id: str | None, headers: list[str]) -> str:
    """Stable identity for a file layout.

    Ordered, because column order is part of a template and two files with the
    same columns in a different order are usually two different reports. This
    is the cache key that keeps the model tier at the 2 percent target: the
    second file with a given layout costs nothing (NFR-8).
    """
    import hashlib

    material = "|".join([client_id or "?", *(c.normalize_header(h) for h in headers)])
    return "tf_" + hashlib.blake2b(material.encode(), digest_size=8).hexdigest()


class Inspector:
    """Classifies raw arrivals."""

    def __init__(
        self,
        reg: registry.Registry,
        object_root: Path,
        parsers: list[Parser] | None = None,
        adjudicator: MappingAdjudicator | None = None,
        cache: TemplateCache | None = None,
    ) -> None:
        self.registry = reg
        self.object_root = object_root
        self.parsers: list[Parser] = parsers or [cls() for cls in DEFAULT_PARSERS]
        # The Tier 3 seam is unbound by default, so the pipeline runs with no
        # model at all. Binding it is a deployment decision, not a code one.
        self.adjudicator = adjudicator
        self.cache = cache

    # --- stages ------------------------------------------------------------

    def sniff(self, path: Path, name: str) -> tuple[Parser, float]:
        """Choose a parser by content, never by extension (FR-17)."""
        head = path.read_bytes()[:SNIFF_BYTES]
        scored = sorted(
            ((p, p.sniff(head, name)) for p in self.parsers),
            key=lambda pair: pair[1],
            reverse=True,
        )
        best, score = scored[0]
        if score <= 0.0:
            raise ParseError(f"no parser recognised {name!r}")
        return best, score

    def classify(self, arrival_id: str, path: Path, original_name: str) -> list[Classification]:
        """Run the full pipeline. Returns one Classification per value date."""
        parser, _ = self.sniff(path, original_name)
        table = parser.parse(path)

        attribution = attribution_mod.attribute(
            filename=original_name,
            headers=table.headers,
            rows=table.rows,
            registry=self.registry,
        )

        client = self.registry.client(attribution.client_id) if attribution.client_id else None
        calendar = (
            self.registry.calendar_for(attribution.client_id)
            if attribution.client_id
            else self.registry.calendar("US_EQUITY")
        )
        if calendar is None:  # pragma: no cover - guarded by registry validation
            raise registry.ConfigError("no calendar available for value-date resolution")

        hints = client.value_date_hints() if client else []
        overrides = client.field_overrides if client else {}
        domain = attribution.domain or c.Domain.UNKNOWN

        fingerprint = template_fingerprint(attribution.client_id, table.headers)
        resolver = TieredResolver(
            field_overrides=overrides, adjudicator=self.adjudicator, cache=self.cache
        )
        outcome = resolver.resolve(
            table,
            client_id=attribution.client_id or "",
            client_name=client.client_name if client else "",
            source_hint=attribution.source_hint,
            domain=domain,
            template_fingerprint=fingerprint,
        )
        mappings = outcome.mappings
        agrees, cross_check_note = cross_check_amount(table, mappings)
        if agrees is False:
            cross_check_note = "arithmetic cross-check FAILED: " + cross_check_note

        # A file spanning several value dates becomes several sub-batches, each
        # dispatched to its own reconciliation slot (FR-16).
        groups = valuedate.split_by_value_date(table.rows, table.headers, hints)

        if not groups:
            resolution = valuedate.resolve(
                headers=table.headers,
                rows=table.rows,
                filename=original_name,
                arrival_day=datetime.now(UTC).date(),
                calendar=calendar,
                hints=hints,
            )
            score = confidence.compose(
                attribution=attribution,
                value_date=resolution,
                mappings=mappings,
                domain=domain,
            )
            return [
                Classification(
                    arrival_id=arrival_id,
                    source_format=parser.format_name,
                    client_id=attribution.client_id,
                    attribution=attribution,
                    value_date=resolution,
                    domain=domain,
                    mappings=mappings,
                    score=score,
                    table=table,
                    template_fingerprint=fingerprint,
                    row_count=table.row_count,
                    cross_check=cross_check_note,
                )
            ]

        out: list[Classification] = []
        for index, (iso, rows) in enumerate(sorted(groups.items())):
            subset = ParsedTable(headers=table.headers, rows=rows, evidence=table.evidence)
            resolution = valuedate.resolve(
                headers=subset.headers,
                rows=subset.rows,
                filename=original_name,
                arrival_day=datetime.now(UTC).date(),
                calendar=calendar,
                hints=hints,
            )
            resolution.notes = (
                f"sub-batch {index + 1} of {len(groups)}; "
                f"file spans {len(groups)} value dates. " + resolution.notes
            )
            score = confidence.compose(
                attribution=attribution,
                value_date=resolution,
                mappings=mappings,
                domain=domain,
            )
            out.append(
                Classification(
                    arrival_id=arrival_id,
                    source_format=parser.format_name,
                    client_id=attribution.client_id,
                    attribution=attribution,
                    value_date=resolution,
                    domain=domain,
                    mappings=mappings,
                    score=score,
                    table=subset,
                    template_fingerprint=fingerprint,
                    row_count=subset.row_count,
                    sub_batch_index=index,
                    sub_batch_total=len(groups),
                    cross_check=cross_check_note,
                )
            )
            del iso
        return out

    def write_canonical(self, classification: Classification, canonical_root: Path) -> str:
        """Write the canonical Parquet for one classification."""
        client = (
            self.registry.client(classification.client_id) if classification.client_id else None
        )
        names = {a.id: a.name for a in client.accounts} if client else {}
        records = emit.build_records(
            table=classification.table,
            mappings=classification.mappings,
            arrival_id=classification.arrival_id,
            client_id=classification.client_id or "",
            value_date=classification.value_date.resolved_iso,
            domain=classification.domain,
            source_system=classification.attribution.source_hint,
            account_names=names,
        )
        suffix = f"_{classification.sub_batch_index}" if classification.sub_batch_total > 1 else ""
        filename = f"{classification.arrival_id}{suffix}.parquet"
        result = emit.write_parquet(records, canonical_root / filename)
        classification.canonical_uri = f"fs://canonical/{filename}"
        classification.row_count = result.row_count
        return classification.canonical_uri


def to_proto(classification: Classification) -> hm.ArrivalClassified:
    """Build the wire message for a classification."""
    now = timestamp_pb2.Timestamp()
    now.FromDatetime(datetime.now(UTC))

    vd = classification.value_date
    resolution = hm.ValueDateResolution(
        resolved=vd.resolved_iso,
        from_filename=vd.from_filename.isoformat() if vd.from_filename else "",
        from_content=[d.isoformat() for d in vd.from_content],
        from_arrival=vd.from_arrival.isoformat() if vd.from_arrival else "",
        method=vd.method,
        confidence=vd.confidence,
        mismatch_flagged=vd.mismatch_flagged,
        calendar_id=vd.calendar_id,
        notes=vd.notes,
    )

    reasons = list(classification.score.reasons)
    if classification.cross_check:
        reasons.append(classification.cross_check)

    return hm.ArrivalClassified(
        arrival_id=classification.arrival_id,
        classified_at=now,
        format=_FORMAT_ENUM.get(classification.source_format, hm.SOURCE_FORMAT_UNSPECIFIED),
        source_hint=classification.attribution.source_hint,
        client_id=classification.client_id or "",
        client_confidence=classification.attribution.confidence,
        account_ids=classification.attribution.account_ids,
        domain=_DOMAIN_ENUM.get(classification.domain, hm.PRODUCT_DOMAIN_UNSPECIFIED),
        recon_side=hm.RECON_SIDE_EXTERNAL_CLIENT,
        value_date=resolution,
        row_count=classification.row_count,
        field_mappings=[
            hm.FieldMapping(
                source_field=m.source_field,
                canonical_field=m.canonical_field or "",
                tier=_TIER_ENUM[m.tier],
                confidence=m.confidence,
                evidence=m.evidence,
            )
            for m in classification.mappings
        ],
        canonical_uri=classification.canonical_uri,
        overall_confidence=classification.score.overall,
        disposition=_DISPOSITION_ENUM[classification.score.disposition],
        review_reasons=reasons,
        template_fingerprint=classification.template_fingerprint,
        sub_batch_index=classification.sub_batch_index,
        sub_batch_total=classification.sub_batch_total,
    )


def topic_for(disposition: str) -> str:
    """Quarantined arrivals go to the review queue, not to Berthmaster."""
    return (
        bus.TOPIC_ARRIVALS_CLASSIFIED
        if disposition == confidence.DISPATCHED
        else bus.TOPIC_ARRIVALS_QUARANTINE
    )


def main() -> int:  # pragma: no cover - process entrypoint
    hmlog.configure("inspector")
    log = hmlog.get("inspector")

    config_dir = os.environ.get("HM_CONFIG_DIR", "/config")
    object_root = Path(os.environ.get("HM_OBJECT_STORE_ROOT", "/data/objects"))
    canonical_root = object_root / "canonical"

    reg = registry.load(config_dir)
    log.info("configuration loaded", clients=len(reg.clients))

    inspector = Inspector(reg, object_root)
    b = bus.MemoryBus()  # replaced by the Kafka bus in the container entrypoint

    def handle(message: bus.Message) -> None:
        raw = bus.decode(message.value, hm.ArrivalRaw())
        hmlog.bind_arrival(raw.arrival_id)
        try:
            path = object_root / raw.uri.removeprefix("fs://")
            for classification in inspector.classify(raw.arrival_id, path, raw.original_name):
                inspector.write_canonical(classification, canonical_root)
                proto = to_proto(classification)
                b.publish(
                    bus.Message(
                        topic=topic_for(classification.score.disposition),
                        key=bus.slot_key(
                            classification.client_id or "UNKNOWN",
                            classification.domain,
                            classification.value_date.resolved_iso,
                        ),
                        value=bus.encode(proto),
                    )
                )
                log.info(
                    "arrival classified",
                    client_id=classification.client_id,
                    value_date=classification.value_date.resolved_iso,
                    method=classification.value_date.method,
                    mismatch=classification.value_date.mismatch_flagged,
                    disposition=classification.score.disposition,
                    confidence=classification.score.overall,
                    rows=classification.row_count,
                )
        except ParseError as exc:
            # MALFORMED: no retry, and the arrival is recorded as rejected
            # rather than being redelivered forever.
            log.error("arrival could not be parsed", error=str(exc))
        finally:
            hmlog.clear_arrival()

    b.consume("inspector", [bus.TOPIC_ARRIVALS_RAW], handle)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
