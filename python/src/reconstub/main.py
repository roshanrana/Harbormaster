"""The reconciliation engine, stubbed.

This is deliberately unintelligent, and that is the point of the whole project.
It is told which two files to compare and which value date they represent. It
does not infer any of that, cannot recover if it is told wrong, and has no
opinion about which column is a settlement price.

Everything that makes reconciliation hard in practice has already happened by
the time a message reaches this consumer. Keeping the stub this dumb is what
demonstrates that the intelligence lives in Harbormaster rather than being
quietly smuggled into the engine.

What it does: joins two canonical Parquet files on a natural key, compares the
economically material fields, and writes a break report.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# The join key. Fixed, because a configurable one would be a form of
# intelligence and this component is not allowed any.
JOIN_KEYS = ("account_id", "instrument_id", "trade_id")

# Fields compared once rows are matched.
COMPARED_FIELDS = (
    "quantity",
    "trade_price",
    "settlement_price",
    "gross_amount",
    "net_amount",
    "market_value",
    "currency",
)

# Anything at or below this is a rounding artefact, not a break.
TOLERANCE = Decimal("0.01")


@dataclass(slots=True)
class Break:
    kind: str  # MISSING_SIDE_1 | MISSING_SIDE_2 | VALUE_MISMATCH
    join_key: str
    field_name: str = ""
    side_1_value: str = ""
    side_2_value: str = ""


@dataclass(slots=True)
class Report:
    assignment_id: str
    client_id: str
    domain: str
    value_date: str
    side_1_rows: int
    side_2_rows: int
    matched: int
    breaks: list[Break] = field(default_factory=list)
    superseded: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "client_id": self.client_id,
            "domain": self.domain,
            "value_date": self.value_date,
            "generated_at": datetime.now(UTC).isoformat(),
            "side_1_rows": self.side_1_rows,
            "side_2_rows": self.side_2_rows,
            "matched": self.matched,
            "break_count": len(self.breaks),
            "supersedes": self.superseded,
            "breaks": [
                {
                    "kind": b.kind,
                    "key": b.join_key,
                    "field": b.field_name,
                    "side_1": b.side_1_value,
                    "side_2": b.side_2_value,
                }
                for b in self.breaks[:500]
            ],
        }


def _key(row: dict[str, Any]) -> str:
    return "|".join(str(row.get(k) or "") for k in JOIN_KEYS)


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def reconcile(side_1: list[dict[str, Any]], side_2: list[dict[str, Any]]) -> list[Break]:
    """Compare two sets of canonical rows.

    A missing settlement price is not treated as zero. That distinction is why
    the canonical output is typed Parquet rather than CSV (ADR-006): a null
    that silently became 0.00 here would produce a break against every row.
    """
    left = {_key(r): r for r in side_1}
    right = {_key(r): r for r in side_2}
    breaks: list[Break] = []

    for key in sorted(left.keys() - right.keys()):
        breaks.append(Break(kind="MISSING_SIDE_2", join_key=key))
    for key in sorted(right.keys() - left.keys()):
        breaks.append(Break(kind="MISSING_SIDE_1", join_key=key))

    for key in sorted(left.keys() & right.keys()):
        a, b = left[key], right[key]
        for name in COMPARED_FIELDS:
            av, bv = a.get(name), b.get(name)
            if av is None and bv is None:
                continue
            da, db_ = _as_decimal(av), _as_decimal(bv)
            if da is not None and db_ is not None:
                if abs(da - db_) > TOLERANCE:
                    breaks.append(
                        Break(
                            kind="VALUE_MISMATCH",
                            join_key=key,
                            field_name=name,
                            side_1_value=str(av),
                            side_2_value=str(bv),
                        )
                    )
                continue
            # Explicit None checks, not truthiness: Decimal("0") is falsy, and
            # collapsing it to "" here would make a genuine zero amount
            # indistinguishable from a missing one.
            left_text = "" if av is None else str(av)
            right_text = "" if bv is None else str(bv)
            if left_text != right_text:
                breaks.append(
                    Break(
                        kind="VALUE_MISMATCH",
                        join_key=key,
                        field_name=name,
                        side_1_value=left_text,
                        side_2_value=right_text,
                    )
                )
    return breaks


def load_canonical(uri: str, object_root: Path) -> list[dict[str, Any]]:
    """Read a canonical Parquet file referenced by an object-store URI."""
    import polars as pl

    if not uri.startswith("fs://"):
        raise ValueError(f"reconstub: unsupported object store uri: {uri}")
    path = object_root / uri.removeprefix("fs://")
    if not path.exists():
        raise FileNotFoundError(f"reconstub: canonical file not found: {path}")
    rows: list[dict[str, Any]] = pl.read_parquet(path).to_dicts()
    return rows


def run_assignment(message: dict[str, Any], object_root: Path, report_dir: Path) -> Report:
    """Execute one berth assignment and write its report."""
    side_1 = load_canonical(message["side1"]["canonicalUri"], object_root)
    side_2 = load_canonical(message["side2"]["canonicalUri"], object_root)

    report = Report(
        assignment_id=message["assignmentId"],
        client_id=message["clientId"],
        domain=message.get("domain", ""),
        value_date=message["valueDate"],
        side_1_rows=len(side_1),
        side_2_rows=len(side_2),
        matched=0,
        superseded=message.get("supersedes", ""),
    )
    report.breaks = reconcile(side_1, side_2)
    report.matched = len({_key(r) for r in side_1} & {_key(r) for r in side_2})

    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / f"{report.client_id}_{report.domain}_{report.value_date}.json"
    out.write_text(json.dumps(report.to_dict(), indent=2))
    return report


def main() -> int:  # pragma: no cover - process entrypoint
    from inspector import bus
    from inspector import logging as hmlog

    hmlog.configure("reconstub")
    log = hmlog.get("reconstub")

    object_root = Path(os.environ.get("HM_OBJECT_STORE_ROOT", "/data/objects"))
    report_dir = Path(os.environ.get("HM_REPORT_DIR", "/data/reports"))
    voided: set[str] = set()

    def handle(m: bus.Message) -> None:
        payload = json.loads(m.value.decode())
        if m.topic == bus.TOPIC_BERTH_SUPERSEDED:
            # The void always arrives before its replacement, because both
            # share the slot partition key (ADR-005). Recording it is enough.
            voided.add(payload["assignmentId"])
            log.info("assignment voided", assignment_id=payload["assignmentId"])
            return
        if payload["assignmentId"] in voided:
            log.info("skipping voided assignment", assignment_id=payload["assignmentId"])
            return
        report = run_assignment(payload, object_root, report_dir)
        log.info(
            "reconciliation complete",
            assignment_id=report.assignment_id,
            client_id=report.client_id,
            value_date=report.value_date,
            matched=report.matched,
            breaks=len(report.breaks),
        )

    b = bus.MemoryBus()  # replaced by the Kafka bus in the container entrypoint
    b.consume("reconstub", [bus.TOPIC_BERTH_ASSIGNED, bus.TOPIC_BERTH_SUPERSEDED], handle)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
