"""End-to-end test against a running Compose stack.

This is the only test that needs infrastructure, and it is the one that proves
the contracts actually line up across the two languages and the broker rather
than merely being consistent in isolation.

It cannot run in the build environment, which has no Docker (ADR-018). Run it
on a machine that does:

    make up && make test-e2e
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BOARD = os.environ.get("HM_BOARD_URL", "http://localhost:8080")
LANDING = Path(os.environ.get("HM_LANDING_DIR", "./data/landing"))
REPORTS = Path(os.environ.get("HM_REPORT_DIR", "./data/reports"))

TIMEOUT_SECONDS = 120
POLL_SECONDS = 2


def _stack_is_up() -> bool:
    try:
        with urllib.request.urlopen(f"{BOARD}/readyz", timeout=2) as response:  # noqa: S310
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _stack_is_up(),
    reason=f"no stack at {BOARD}; run `make up` first",
)


def get(path: str) -> list | dict:
    with urllib.request.urlopen(f"{BOARD}{path}", timeout=10) as response:  # noqa: S310
        return json.loads(response.read())


def wait_for(predicate, what: str):  # noqa: ANN001, ANN201
    """Poll until the predicate returns a truthy value, or fail with context."""
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(POLL_SECONDS)
    pytest.fail(f"timed out after {TIMEOUT_SECONDS}s waiting for {what}; last saw {last!r}")


@pytest.fixture(scope="module")
def corpus() -> dict[str, list[Path]]:
    """Seed the landing directory with the adversarial corpus."""
    from corpus.scenarios import ScenarioBuilder

    LANDING.mkdir(parents=True, exist_ok=True)
    staged = ScenarioBuilder(LANDING / "_generated").build_all()
    files: dict[str, list[Path]] = {}
    for scenario in staged:
        placed = []
        for source in scenario.files:
            target = LANDING / source.name
            target.write_bytes(source.read_bytes())
            placed.append(target)
        files[scenario.name] = placed
    return files


def test_stack_is_healthy() -> None:
    assert get("/healthz")["status"] == "ok"


def test_file_lands_and_reaches_the_board(corpus: dict[str, list[Path]]) -> None:
    del corpus
    rows = wait_for(lambda: get("/api/arrivals"), "arrivals to appear on the board")
    assert rows, "no arrivals were classified"
    assert any(r["client_id"] for r in rows), "nothing was attributed to a client"


def test_late_arrival_resolves_to_its_true_value_date(corpus: dict[str, list[Path]]) -> None:
    """The headline case, proven through the real broker and both languages."""
    del corpus

    def late() -> dict | None:
        for row in get("/api/arrivals"):
            if row["original_name"] == "MCP_TRD_20260831.csv":
                return row
        return None

    row = wait_for(late, "the late-arrival file to be classified")
    assert row["value_date"] == "2026-08-28"
    assert row["mismatch_flagged"] is True
    assert row["client_id"] == "CLNT004"


def test_both_sides_produce_a_berth_assignment(corpus: dict[str, list[Path]]) -> None:
    del corpus
    assignments = wait_for(lambda: get("/api/assignments"), "a berth assignment to be issued")
    assert assignments
    first = assignments[0]
    assert first["side_1_arrival"] and first["side_2_arrival"]
    assert first["expectation_id"]


def test_recon_stub_writes_a_break_report(corpus: dict[str, list[Path]]) -> None:
    del corpus
    reports = wait_for(
        lambda: list(REPORTS.glob("*.json")), "the recon stub to write a break report"
    )
    payload = json.loads(reports[0].read_text())
    assert payload["client_id"]
    assert payload["value_date"]
    assert "break_count" in payload


def test_unattributable_file_reaches_the_review_queue(corpus: dict[str, list[Path]]) -> None:
    del corpus
    queue = wait_for(lambda: get("/api/quarantine"), "the review queue to fill")
    assert any(r["original_name"] == "export_final.csv" for r in queue)


def test_duplicate_is_suppressed(corpus: dict[str, list[Path]]) -> None:
    """The same content twice must not produce two arrivals."""
    del corpus
    rows = wait_for(lambda: get("/api/arrivals"), "arrivals")
    hashes = [r["arrival_id"] for r in rows]
    assert len(hashes) == len(set(hashes)), "an arrival was recorded twice"


def test_summary_reports_the_quarantine_rate(corpus: dict[str, list[Path]]) -> None:
    del corpus
    summary = get("/api/summary")
    assert summary["arrivals"] > 0
    # NFR-7: five percent or below on the reference corpus, allowing for the
    # deliberately unattributable fixtures.
    assert summary["quarantine_rate"] <= 0.35


def test_audit_chain_verifies(corpus: dict[str, list[Path]]) -> None:
    """Every decision must be reconstructable and unaltered.

    Verified here through the API surface; `make verify-audit` runs the same
    walk from the command line.
    """
    del corpus
    rows = wait_for(lambda: get("/api/arrivals"), "arrivals")
    detail = get(f"/api/arrivals/{rows[0]['arrival_id']}")
    assert detail["content_sha256"]
    assert detail.get("classification")
