"""The bench harness and the headline.json it emits.

The results card renders whatever ``metrics/headline.json`` says, so the
schema check has to be a test, not a convention; and the harness itself has
to run in the default gate, or the committed numbers go stale silently.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bench"))

import headline_check  # noqa: E402
import onboard  # noqa: E402

from inspector.mapping import canonical as c  # noqa: E402


def minimal_doc() -> dict[str, Any]:
    return {
        "kpis": {"k_one": {"label": "L", "value": "1", "note": "n", "accent": "teal"}},
        "bars": {
            "title": "T",
            "rows": [{"label": "a", "value": 1, "max": 2, "display": "1/2", "accent": "blue"}],
        },
        "facts": {"title": "F", "rows": [{"label": "f", "value": "v", "status": "pending"}]},
    }


def test_schema_check_accepts_a_minimal_document() -> None:
    assert headline_check.problems_in(minimal_doc()) == []


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda d: d["kpis"]["k_one"].update(accent="green"), "accent"),
        (lambda d: d["facts"]["rows"][0].update(status="done"), "status"),
        (lambda d: d["bars"]["rows"][0].update(value=3), "outside"),
        (lambda d: d["bars"]["rows"][0].update(value=True), "numbers"),
        (lambda d: d.update(generated_at="now"), "unexpected keys"),
        (lambda d: d["kpis"].update({"Bad Key": d["kpis"]["k_one"]}), "snake_case"),
        (lambda d: d["kpis"]["k_one"].pop("note"), "missing keys"),
    ],
)
def test_schema_check_rejects_each_kind_of_defect(mutate: Any, fragment: str) -> None:
    doc = copy.deepcopy(minimal_doc())
    mutate(doc)
    problems = headline_check.problems_in(doc)
    assert problems, "defect was not detected"
    assert any(fragment in p for p in problems), problems
    with pytest.raises(headline_check.HeadlineError):
        headline_check.assert_valid(doc)


def test_golden_labels_only_name_mappable_canonical_fields() -> None:
    golden = onboard.load_golden()
    for layout in golden["layouts"].values():
        for label in layout.values():
            assert label is None or label in c.MAPPABLE_FIELDS
    assert all(f["layout"] in golden["layouts"] for f in golden["files"])


def test_committed_headline_matches_the_schema() -> None:
    path = REPO / "metrics" / "headline.json"
    if not path.exists():
        pytest.skip("metrics/headline.json not generated yet; run make bench")
    headline_check.assert_valid(json.loads(path.read_text(encoding="utf-8")))


def test_bench_replays_the_fixed_set_and_emits_only_observed_values(tmp_path: Path) -> None:
    doc, obs = onboard.build_headline(tmp_path)

    headline_check.assert_valid(doc)
    assert obs.files == len(onboard.load_golden()["files"])
    # Every bar is a count over the same labelled column set.
    for row in doc["bars"]["rows"]:
        assert row["max"] == obs.columns
        assert 0 <= row["value"] <= row["max"]
    assert sum(obs.by_bucket.values()) == obs.columns
    # Dispositions are exhaustively bucketed, so precision and recall are over
    # every classification and none is silently dropped.
    assert (
        obs.quarantine_tp + obs.quarantine_fp + obs.quarantine_fn + obs.quarantine_tn
        == obs.classifications
    )
    # The tamper check never reports a pass it did not observe.
    tamper = doc["kpis"]["tamper_check"]
    assert tamper["value"] in {
        "detected, fail-closed",
        "not run",
        "NOT detected",
        "detected at wrong record",
    }
    assert (tamper["accent"] == "teal") == (tamper["value"] == "detected, fail-closed")
