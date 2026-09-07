"""Replay a fixed source-file set through onboarding and publish what was observed.

The scenario suite in ``tests/scenarios`` already measures the things that
matter (which tier resolved each column, whether a file was held, whether the
audit chain catches an edit) and then throws the numbers away as pass/fail.
This harness runs the same pipeline over the same fixtures and keeps the
counts, writing them to ``metrics/headline.json`` for the README results card.

Three rules keep the numbers honest.

**Only observed values are emitted.** Every figure is a count taken from a
``Mapping``, a ``Score`` or a verifier exit code produced during this run.
Anything that needs a live model, a database or a running stack is listed in
the facts panel as ``pending`` with the reason, never estimated.

**The source set is fixed and pinned.** The files are regenerated from the
committed corpus generator at seed 20260831 and checked against the sha256 in
``bench/golden/onboarding.json`` before scoring. The golden labels were made by
reading those files' columns against the canonical schema; a file whose bytes
differ from what was labelled is a hard failure, not a warning.

**The run is offline and deterministic.** The Tier 3 seam is bound to the
repository's ``DeterministicFake``, so the model bar reports what fell through
to the model tier and what the stand-in answered, not a real model's accuracy,
and says so. Tier 2 runs however the environment allows and reports whether the
semantic matcher was present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "python" / "src"))

import headline_check  # noqa: E402

from corpus.generate import VENUES, CorpusGenerator  # noqa: E402
from corpus.scenarios import FRIDAY, ScenarioBuilder  # noqa: E402
from inspector import confidence, registry  # noqa: E402
from inspector.main import Classification, Inspector  # noqa: E402
from inspector.mapping import canonical as c  # noqa: E402
from inspector.mapping.tier1 import Mapping  # noqa: E402
from inspector.mapping.tier3 import (  # noqa: E402
    AdjudicationRequest,
    AdjudicationResult,
    DeterministicFake,
    InMemoryCache,
)

SEED = 20260831
GOLDEN = REPO / "bench" / "golden" / "onboarding.json"
AUDIT_FIXTURE = REPO / "bench" / "golden" / "audit_chain.json"
DEFAULT_OUT = REPO / "metrics" / "headline.json"

# A held arrival is anything that did not dispatch: both quarantine and
# rejection put the file in front of a human rather than the engine.
HELD = frozenset({confidence.QUARANTINED, confidence.REJECTED})

# Exit code the Go verifier uses for a broken chain, as distinct from an error.
AUDITCHECK_BROKEN = 2


class BenchError(Exception):
    """The bench could not produce an honest number."""


# --- the fixed source set --------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExtraFile:
    """A file the scenario suite does not cover, added for format breadth."""

    name: str
    venue: str
    accounts: tuple[str, ...]
    count: int
    writer: str


# Generated in this order from a fresh generator, after the scenarios, so the
# sha256 values in the golden file are reproducible.
EXTRA_FILES: tuple[ExtraFile, ...] = (
    ExtraFile("NGAM_20260828_TRADES.xml", "EUREX", ("DE-77120-004", "DE-77120-009"), 8, "xml"),
    ExtraFile("NGAM_20260828_TRADES.fixml", "EUREX", ("DE-77120-004", "DE-77120-009"), 8, "fixml"),
    ExtraFile("ardent-trades-2026-08-28.json", "NYSE", ("AGM-5590-01",), 6, "json"),
    ExtraFile("SABLE_20260828_OPT.csv", "CBOE", ("SRT-9902",), 7, "csv"),
    ExtraFile("PRS_pos_20260828.csv", "NASDAQ", ("US-4471-0088",), 6, "csv"),
)


def build_sources(root: Path) -> None:
    """Regenerate the fixed source set under ``root``."""
    ScenarioBuilder(root, SEED).build_all()
    gen = CorpusGenerator(SEED)
    ext = root / "ext"
    for spec in EXTRA_FILES:
        # The XML and FIXML pair share one trade list on purpose: they are the
        # same business in two dialects, which is what a client actually sends.
        if spec.writer == "fixml":
            continue
        trades = gen.trades(
            account_ids=list(spec.accounts), venue=spec.venue, value_date=FRIDAY, count=spec.count
        )
        profile = VENUES[spec.venue]
        if spec.writer == "xml":
            gen.write_xml(ext / spec.name, trades, profile)
            gen.write_fixml(ext / spec.name.replace(".xml", ".fixml"), trades)
        elif spec.writer == "json":
            gen.write_json(ext / spec.name, trades, profile)
        else:
            gen.write_delimited(ext / spec.name, trades, profile)


# --- observation -----------------------------------------------------------


class ObservedAdjudicator:
    """The deterministic fake, with the traffic that reaches it counted."""

    name = "deterministic-fake"

    def __init__(self) -> None:
        self.inner = DeterministicFake()
        self.requests = 0
        self.headers_sent = 0

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationResult:
        self.requests += 1
        self.headers_sent += len(request.unresolved_headers)
        return self.inner.adjudicate(request)


# How each recorded provenance is presented. The Tier 1 module records its
# structural price decision as LOCAL, so the evidence string separates that
# from a Tier 2 fuzzy match; a cache hit is a prior Tier 3 answer replayed.
BUCKET_ORDER = ("alias", "structural", "fuzzy", "override", "cache", "llm", "unresolved")
BUCKET_LABELS = {
    "alias": "Tier 1: alias dictionary",
    "structural": "Tier 1: structural price rule",
    "fuzzy": "Tier 2: fuzzy match",
    "override": "Client override (promoted)",
    "cache": "Template cache (prior Tier 3 answer)",
    "llm": "Tier 3: model (deterministic fake)",
    "unresolved": "Unresolved (declined)",
}
BUCKET_ACCENTS = {
    "alias": "teal",
    "structural": "teal",
    "fuzzy": "blue",
    "override": "blue",
    "cache": "violet",
    "llm": "violet",
    "unresolved": "amber",
}


def bucket_of(m: Mapping) -> str:
    if m.canonical_field is None:
        return "unresolved"
    if m.tier == c.Tier.HUMAN:
        return "override"
    if m.tier == c.Tier.ALIAS:
        return "alias"
    if m.tier == c.Tier.LOCAL:
        return "fuzzy" if "fuzzy" in m.evidence else "structural"
    if m.tier == c.Tier.LLM:
        return "cache" if m.evidence.startswith("cached") else "llm"
    return "unresolved"


@dataclass(slots=True)
class Observation:
    files: int = 0
    classifications: int = 0
    columns: int = 0
    correct: int = 0
    by_bucket: Counter[str] = field(default_factory=Counter)
    correct_by_bucket: Counter[str] = field(default_factory=Counter)
    misses: list[str] = field(default_factory=list)
    quarantine_tp: int = 0
    quarantine_fp: int = 0
    quarantine_fn: int = 0
    quarantine_tn: int = 0
    disposition_misses: list[str] = field(default_factory=list)
    tier3_requests: int = 0
    tier3_headers: int = 0
    cache_hits: int = 0
    tier2_degraded: bool = False


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_golden() -> dict[str, Any]:
    golden: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for layout, columns in golden["layouts"].items():
        for header, label in columns.items():
            if label is not None and label not in c.MAPPABLE_FIELDS:
                raise BenchError(f"golden layout {layout}: {header!r} -> {label!r} is not mappable")
    for layout, groups in golden.get("either", {}).items():
        for field_name, columns in groups.items():
            if field_name not in c.MAPPABLE_FIELDS or len(columns) < 2:
                raise BenchError(f"golden either-group {layout}/{field_name} is malformed")
            unknown = [col for col in columns if col not in golden["layouts"][layout]]
            if unknown:
                raise BenchError(f"golden either-group {layout}/{field_name} names {unknown}")
    return golden


def _expected_labels(
    layout: dict[str, str | None], either: dict[str, list[str]], mappings: list[Mapping]
) -> dict[str, str | None]:
    """Resolve the golden into one expected label per column.

    An ``either`` group names columns that are all legitimate carriers of one
    canonical field (Symbol and ISIN for instrument_id). Exactly one of them
    must take the field and the others must stay unassigned; the group is
    scored on that shape rather than on which carrier the mapper preferred.
    If none took it, the first-listed carrier is the one marked wrong.
    """
    expected = dict(layout)
    assigned = {m.source_field: m.canonical_field for m in mappings}
    for field_name, columns in either.items():
        holders = [col for col in columns if assigned.get(col) == field_name]
        holder = holders[0] if len(holders) == 1 else columns[0]
        for col in columns:
            expected[col] = field_name if col == holder else None
    return expected


def _score_mappings(
    entry: dict[str, Any], golden: dict[str, Any], first: Classification, obs: Observation
) -> None:
    layout = golden["layouts"][entry["layout"]]
    headers = [m.source_field for m in first.mappings]
    if set(headers) != set(layout):
        raise BenchError(
            f"{entry['path']}: parsed headers {sorted(headers)} do not match the golden "
            f"layout {entry['layout']} {sorted(layout)}; relabel before scoring"
        )
    either = golden.get("either", {}).get(entry["layout"], {})
    labels = _expected_labels(layout, either, first.mappings)
    for m in first.mappings:
        expected = labels[m.source_field]
        bucket = bucket_of(m)
        obs.columns += 1
        obs.by_bucket[bucket] += 1
        if m.canonical_field == expected:
            obs.correct += 1
            obs.correct_by_bucket[bucket] += 1
        else:
            obs.misses.append(
                f"{entry['path']}: {m.source_field!r} -> {m.canonical_field} "
                f"(expected {expected}; {m.tier}: {m.evidence})"
            )
        if m.evidence.startswith("cached"):
            obs.cache_hits += 1


def _score_disposition(
    entry: dict[str, Any], results: list[Classification], obs: Observation
) -> None:
    expected_held = bool(entry["expected_quarantine"])
    for r in results:
        obs.classifications += 1
        held = r.score.disposition in HELD
        if held and expected_held:
            obs.quarantine_tp += 1
        elif held and not expected_held:
            obs.quarantine_fp += 1
        elif not held and expected_held:
            obs.quarantine_fn += 1
        else:
            obs.quarantine_tn += 1
        if held != expected_held:
            obs.disposition_misses.append(
                f"{entry['path']}: {r.score.disposition} (expected "
                f"{'held' if expected_held else 'dispatched'}); {'; '.join(r.score.reasons)}"
            )


def replay(root: Path, golden: dict[str, Any]) -> Observation:
    """Run every golden file through the Inspector and count what happened."""
    reg = registry.load(REPO / "config")
    adjudicator = ObservedAdjudicator()
    inspector = Inspector(reg, root, adjudicator=adjudicator, cache=InMemoryCache())
    obs = Observation()

    for index, entry in enumerate(golden["files"]):
        path = root / entry["path"]
        if not path.exists():
            raise BenchError(f"{entry['path']}: not generated")
        pinned = entry["sha256"]
        if pinned is not None and _sha256(path) != pinned:
            raise BenchError(f"{entry['path']}: bytes differ from the labelled fixture")

        results = inspector.classify(f"bench-{index:03d}", path, path.name)
        obs.files += 1
        _score_mappings(entry, golden, results[0], obs)
        _score_disposition(entry, results, obs)

    obs.tier3_requests = adjudicator.requests
    obs.tier3_headers = adjudicator.headers_sent
    # The resolver is built per file inside classify; ask a fresh matcher the
    # same question it would have been asked.
    from inspector.mapping.tier2 import Tier2Matcher

    obs.tier2_degraded = Tier2Matcher().degraded
    return obs


# --- hash-chain tamper check -----------------------------------------------


@dataclass(slots=True)
class TamperResult:
    status: str
    value: str
    detail: str


def _build_auditcheck(tmp: Path) -> Path | None:
    """Compile the verifier once. ``go run`` would hide its exit code."""
    binary = tmp / ("auditcheck.exe" if os.name == "nt" else "auditcheck")
    proc = subprocess.run(
        ["go", "build", "-o", str(binary), "./cmd/auditcheck"],
        cwd=REPO / "go",
        env={**os.environ, "GOWORK": "off"},
        capture_output=True,
        text=True,
        check=False,
    )
    return binary if proc.returncode == 0 and binary.exists() else None


def _auditcheck(binary: Path, args: list[str]) -> tuple[int, dict[str, Any] | None, str]:
    proc = subprocess.run(
        [str(binary), *args],
        cwd=REPO / "go",
        capture_output=True,
        text=True,
        check=False,
    )
    verdict: dict[str, Any] | None = None
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    if last.startswith("{"):
        verdict = json.loads(last)
    return proc.returncode, verdict, proc.stderr.strip()


def tamper_check(tmp: Path) -> TamperResult:
    """Verify the recorded chain, then prove an edit and a deletion are caught.

    Fails closed: any step that does not behave exactly as a tamper-evident
    log must is reported as blocked, never as a pass.
    """
    if shutil.which("go") is None:
        return TamperResult("blocked", "not run", "go toolchain not on PATH")
    if not AUDIT_FIXTURE.exists():
        return TamperResult("blocked", "not run", f"{AUDIT_FIXTURE.name} is missing")
    binary = _build_auditcheck(tmp)
    if binary is None:
        return TamperResult("blocked", "not run", "cmd/auditcheck did not build")

    code, verdict, err = _auditcheck(binary, ["-verify", str(AUDIT_FIXTURE)])
    if code != 0 or verdict is None or not verdict.get("ok"):
        return TamperResult(
            "blocked", "not run", f"recorded chain failed before tampering: {err or verdict}"
        )

    records = json.loads(AUDIT_FIXTURE.read_text(encoding="utf-8"))
    edited = tmp / "chain_edited.json"
    edited_records = [dict(r) for r in records]
    edited_records[1]["OutcomeJSON"] = '{"disposition":"DISPATCHED","value_date":"2026-08-31"}'
    edited.write_text(json.dumps(edited_records), encoding="utf-8")

    deleted = tmp / "chain_deleted.json"
    deleted.write_text(json.dumps(records[:1] + records[2:]), encoding="utf-8")

    outcomes: list[str] = []
    for label, path, want_position in (
        ("edited outcome", edited, 1),
        ("deleted record", deleted, 1),
    ):
        code, verdict, err = _auditcheck(binary, ["-verify", str(path)])
        if code != AUDITCHECK_BROKEN or verdict is None or verdict.get("ok") is not False:
            return TamperResult(
                "blocked",
                "NOT detected",
                f"{label} left the chain looking valid (exit {code}; {err or verdict})",
            )
        if verdict.get("position") != want_position:
            return TamperResult(
                "blocked",
                "detected at wrong record",
                f"{label}: break at {verdict.get('position')}",
            )
        outcomes.append(f"{label} caught at record {want_position + 1}")
    return TamperResult("ok", "detected, fail-closed", "; ".join(outcomes))


# --- headline --------------------------------------------------------------


def _pct(numerator: int, denominator: int) -> str:
    return "n/a" if denominator == 0 else f"{100.0 * numerator / denominator:.1f}%"


def _ratio_pct(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator} ({_pct(numerator, denominator)})"


def headline(obs: Observation, tamper: TamperResult) -> dict[str, Any]:
    tp, fp, fn = obs.quarantine_tp, obs.quarantine_fp, obs.quarantine_fn
    without_model = sum(obs.by_bucket[b] for b in ("alias", "structural", "fuzzy", "override"))
    model_resolved = obs.by_bucket["llm"] + obs.by_bucket["cache"]

    kpis = {
        "mapping_accuracy": {
            "label": "Field-mapping accuracy",
            "value": _pct(obs.correct, obs.columns),
            "note": (
                f"{obs.correct}/{obs.columns} labelled columns across {obs.files} files, "
                "against bench/golden"
            ),
            "accent": "teal",
        },
        "no_model_share": {
            "label": "Resolved without a model",
            "value": _pct(without_model, obs.columns),
            "note": (
                "alias, structural, fuzzy and promoted overrides: "
                f"{without_model}/{obs.columns} columns"
            ),
            "accent": "blue",
        },
        "tier3_escalations": {
            "label": "Columns escalated to Tier 3",
            "value": str(obs.tier3_headers),
            "note": (
                f"{obs.tier3_requests} adjudication calls; stand-in answered "
                f"{obs.by_bucket['llm']}, cache replayed {obs.by_bucket['cache']}; "
                "not a live-model accuracy"
            ),
            "accent": "violet",
        },
        "quarantine_precision": {
            "label": "Quarantine precision",
            "value": _pct(tp, tp + fp),
            "note": (
                f"{tp} held correctly, {fp} held needlessly, "
                f"of {obs.classifications} classifications"
            ),
            "accent": "amber",
        },
        "quarantine_recall": {
            "label": "Quarantine recall",
            "value": _pct(tp, tp + fn),
            "note": f"{tp} of {tp + fn} files that should be held were held; {fn} slipped through",
            "accent": "amber",
        },
        "tamper_check": {
            "label": "Hash-chain tamper check",
            "value": tamper.value,
            "note": tamper.detail,
            "accent": "teal" if tamper.status == "ok" else "red",
        },
    }

    bars = {
        "title": "Columns resolved per ladder tier",
        "rows": [
            {
                "label": BUCKET_LABELS[b],
                "value": obs.by_bucket[b],
                "max": obs.columns,
                "display": _ratio_pct(obs.by_bucket[b], obs.columns),
                "accent": BUCKET_ACCENTS[b],
            }
            for b in BUCKET_ORDER
            if obs.by_bucket[b] or b in ("alias", "fuzzy", "llm")
        ],
    }

    facts_rows: list[dict[str, str]] = [
        {
            "label": "Fixed source set",
            "value": (
                f"{obs.files} files, {obs.classifications} classifications, "
                f"seed {SEED}, sha256-pinned"
            ),
            "status": "ok",
        },
        {
            "label": "Golden labels",
            "value": (
                f"{obs.columns} column labels, {obs.classifications} disposition labels, "
                "hand-derived"
            ),
            "status": "ok",
        },
        {
            "label": "Per-tier accuracy",
            "value": ", ".join(
                f"{b} {_ratio_pct(obs.correct_by_bucket[b], obs.by_bucket[b])}"
                for b in BUCKET_ORDER
                if obs.by_bucket[b]
            ),
            "status": "ok",
        },
        {
            "label": "Model-resolved columns",
            "value": (
                f"{model_resolved} by the deterministic fake or its cache; "
                f"{obs.cache_hits} cache replays"
            ),
            "status": "ok",
        },
        {
            "label": "Hash-chain tamper check",
            "value": f"{tamper.value}: {tamper.detail}",
            "status": tamper.status,
        },
        {
            "label": "Tier 2 semantic matcher",
            "value": (
                "fuzzy-only; fastembed not installed, so the embedding path did not run"
                if obs.tier2_degraded
                else "embeddings active"
            ),
            "status": "pending" if obs.tier2_degraded else "ok",
        },
        {
            "label": "Live model (Claude) mapping accuracy",
            "value": "not measured offline; needs ANTHROPIC_API_KEY and HM_LIVE=1 make test-live",
            "status": "pending",
        },
        {
            "label": "Duplicate and redelivery suppression",
            "value": (
                "not measured here; Portwatch dedupe is asserted against Postgres (make test-store)"
            ),
            "status": "pending",
        },
        {
            "label": "Throughput and p95 latency (NFR-2)",
            "value": "not measured; needs the running stack (make up)",
            "status": "pending",
        },
    ]
    return {
        "kpis": kpis,
        "bars": bars,
        "facts": {"title": "Observed and pending", "rows": facts_rows},
    }


def build_headline(workdir: Path) -> tuple[dict[str, Any], Observation]:
    """Generate, replay, tamper-check, and return the validated document."""
    golden = load_golden()
    sources = workdir / "sources"
    build_sources(sources)
    obs = replay(sources, golden)
    tamper = tamper_check(workdir)
    doc = headline(obs, tamper)
    headline_check.assert_valid(doc)
    return doc, obs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="where to write headline.json"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="list every mapping and disposition miss"
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="hm-bench-") as tmp:
        try:
            doc, obs = build_headline(Path(tmp))
        except BenchError as exc:
            print(f"bench: {exc}", file=sys.stderr)
            return 1

    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")

    for key, tile in doc["kpis"].items():
        print(f"{key:22s} {tile['value']:>22s}  {tile['note']}")
    for row in doc["bars"]["rows"]:
        print(f"  {row['label']:40s} {row['display']}")
    if args.verbose:
        for miss in obs.misses + obs.disposition_misses:
            print("  miss:", miss)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
