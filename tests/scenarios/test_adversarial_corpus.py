"""The twelve adversarial scenarios from requirements section 8.

Each test is named for the case it covers and asserts the specific behaviour
that case exists to check. They run the real Inspector pipeline over the real
generated corpus, so a regression in parsing, attribution, value-date
resolution or mapping fails here with a name that says what broke.

These are the tests that matter. Any system can parse a tidy CSV; what these
assert is what happens with the ninth file on a Friday afternoon.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from corpus.scenarios import FRIDAY, MONDAY, THURSDAY, ScenarioBuilder
from inspector import confidence, registry
from inspector.main import Inspector
from inspector.mapping.tier3 import DeterministicFake, InMemoryCache
from inspector.parsers.email_text import EmailTextParser
from inspector.parsers.excel import ExcelParser

CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture(scope="module")
def reg() -> registry.Registry:
    return registry.load(CONFIG)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[Path]]:
    """Generate the adversarial corpus once for the whole module."""
    out = tmp_path_factory.mktemp("corpus")
    scenarios = ScenarioBuilder(out).build_all()
    return {s.name: s.files for s in scenarios}


@pytest.fixture
def inspector(reg: registry.Registry, tmp_path: Path) -> Inspector:
    # The deterministic fake is bound rather than a live model, so the whole
    # suite runs offline with no API key (NFR-12, C-3).
    return Inspector(
        reg, tmp_path, adjudicator=DeterministicFake(), cache=InMemoryCache()
    )


def classify(inspector: Inspector, path: Path, arrival_id: str = "arr-test") -> list:
    return inspector.classify(arrival_id, path, path.name)


# 1 ---------------------------------------------------------------------------


def test_late_arrival_binds_to_its_historical_value_date(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """A file landing Monday whose contents belong to Friday.

    The reason the project exists. Reconciling these rows against Monday's
    ledger would break on every line, and an analyst would spend a morning
    discovering that nothing was wrong except the date.
    """
    path = corpus["late_arrival"][0]
    assert "20260831" in path.name

    result = classify(inspector, path)[0]

    assert result.value_date.resolved == FRIDAY
    assert result.value_date.method == "CONTENT_EXPLICIT"
    assert result.client_id == "CLNT004"
    assert result.score.disposition == confidence.DISPATCHED


# 2 ---------------------------------------------------------------------------


def test_filename_content_disagreement_is_always_flagged(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """Filename says Thursday, contents say Friday.

    Content wins, and the disagreement is surfaced rather than silently
    resolved: a recurring mismatch means the client's batch schedule drifted.
    """
    path = corpus["filename_content_disagreement"][0]
    result = classify(inspector, path)[0]

    assert result.value_date.resolved == FRIDAY
    assert result.value_date.from_filename == THURSDAY
    assert result.value_date.mismatch_flagged is True
    assert "2026-08-27" in result.value_date.notes
    assert "2026-08-28" in result.value_date.notes
    # Flagged, but still usable, so it dispatches with the caveat attached.
    assert result.score.disposition == confidence.DISPATCHED
    assert any("disagreement" in r for r in result.score.reasons)


# 3 and 4 ---------------------------------------------------------------------


def test_exact_duplicate_has_identical_content_hash(
    corpus: dict[str, list[Path]]
) -> None:
    """The identical file delivered twice.

    Suppression itself is Portwatch's job and is tested in Go against the
    database constraint. What this asserts is the precondition: the two files
    really are byte-identical, so the content hash will collide.
    """
    import hashlib

    first, second = corpus["exact_duplicate"]
    digest = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (first, second)]
    assert digest[0] == digest[1]
    assert first.name == second.name


def test_redelivery_under_a_new_name_still_collides(
    corpus: dict[str, list[Path]]
) -> None:
    """Identical content, different filename.

    Must be recognised by content, not by name, or a client with a broken
    scheduler double-counts every reconciliation they resend.
    """
    import hashlib

    first, second = corpus["redelivery_under_new_name"]
    assert first.name != second.name
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(
        second.read_bytes()
    ).hexdigest()


# 5 ---------------------------------------------------------------------------


def test_correction_differs_in_content_but_targets_the_same_slot(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """An amended file for a slot that already dispatched.

    The correction must classify to the same client, domain and value date as
    the original, because that identity is what routes it onto the same
    partition and lets the void be ordered before its replacement.
    """
    import hashlib

    original, corrected = corpus["correction_after_dispatch"]
    assert hashlib.sha256(original.read_bytes()).hexdigest() != hashlib.sha256(
        corrected.read_bytes()
    ).hexdigest()

    a = classify(inspector, original, "arr-original")[0]
    b = classify(inspector, corrected, "arr-corrected")[0]

    assert (a.client_id, a.domain, a.value_date.resolved_iso) == (
        b.client_id, b.domain, b.value_date.resolved_iso
    )


# 6 ---------------------------------------------------------------------------


def test_multi_date_file_splits_into_sub_batches(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """One file spanning three value dates.

    Forcing it onto a single date would reconcile two thirds of the rows
    against the wrong day.
    """
    path = corpus["multi_date_file"][0]
    results = classify(inspector, path)

    assert len(results) == 3
    assert {r.value_date.resolved for r in results} == {THURSDAY, FRIDAY, MONDAY}
    assert {r.sub_batch_total for r in results} == {3}
    assert sorted(r.sub_batch_index for r in results) == [0, 1, 2]
    assert sum(r.row_count for r in results) == 12


# 7 ---------------------------------------------------------------------------


def test_four_price_columns_resolve_correctly(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """An ICE extract carrying four price-like columns.

    Conflating the traded price with the mark or the prior settle produces a
    reconciliation that runs, returns a number, and is wrong.
    """
    path = corpus["four_price_columns"][0]
    result = classify(inspector, path)[0]
    by_field = {m.canonical_field: m.source_field for m in result.mappings if m.canonical_field}

    assert by_field["trade_price"] == "Price"
    assert by_field["settlement_price"] == "Settle Px"

    # The surplus price columns are left unassigned rather than guessed at,
    # and each says why.
    unassigned = [m for m in result.mappings if m.canonical_field is None]
    assert any("Mark Price" == m.source_field for m in unassigned)
    assert all(m.evidence for m in unassigned)


# 8 ---------------------------------------------------------------------------


def test_bare_price_headers_resolve_structurally(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """Two price columns labelled only Price and Px.

    No amount of string similarity separates these. What does is structure: a
    settlement price is a property of an instrument on a day so it repeats,
    while a trade price is a property of an execution so it varies.
    """
    path = corpus["bare_price_header"][0]
    result = classify(inspector, path)[0]
    mappings = {m.canonical_field: m for m in result.mappings if m.canonical_field}

    assert mappings["trade_price"].source_field == "Price"
    assert mappings["settlement_price"].source_field == "Px"
    assert "varies" in mappings["trade_price"].evidence
    assert "constant" in mappings["settlement_price"].evidence


# 9 ---------------------------------------------------------------------------


def test_email_cash_advice_yields_structured_movements(
    corpus: dict[str, list[Path]]
) -> None:
    """A cash movement described in prose.

    Assuming every arrival is tabular loses this file entirely.
    """
    path = corpus["email_cash_advice"][0]
    table = EmailTextParser().parse(path)

    assert table.row_count == 3
    assert set(table.column("Currency")) == {"USD", "EUR"}
    assert set(table.column("Direction")) == {"CREDIT", "DEBIT"}
    assert set(table.column("Value Date")) == {FRIDAY.isoformat()}
    # Debits are signed, so the reconciliation does not have to infer sign.
    assert any(a.startswith("-") for a in table.column("Net Amount"))


# 10 --------------------------------------------------------------------------


def test_unattributable_file_is_held_for_review(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """Nothing identifies the owner.

    Guessing a client here would route a real reconciliation to the wrong
    counterparty. Holding it costs an operator two minutes.
    """
    path = corpus["unattributable_file"][0]
    result = classify(inspector, path)[0]

    assert result.client_id is None
    assert result.score.disposition in {confidence.QUARANTINED, confidence.REJECTED}
    assert any("client could not be determined" in r for r in result.score.reasons)
    # The reason has to be specific enough to act on.
    assert all(len(r) > 20 for r in result.score.reasons)


# 11 --------------------------------------------------------------------------


def test_awkward_workbook_finds_the_data(corpus: dict[str, list[Path]]) -> None:
    """A custody workbook with a cover sheet, a banner and a totals row.

    Reading sheet zero, row zero yields a confidentiality notice parsed as
    data; counting the last row inflates the reconciliation by one holding.
    """
    path = corpus["awkward_workbook"][0]
    table = ExcelParser().parse(path)

    assert table.evidence["sheet"] == "Holdings"
    assert table.evidence["header_row_index"] == "3"
    assert table.row_count == 9
    assert "Custody Account" in table.headers
    assert any("summary row" in w for w in table.warnings)


# 12 --------------------------------------------------------------------------


def test_preamble_and_totals_row_are_excluded(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """A pipe-delimited CSV wrapped in a title banner and closed with a total."""
    path = corpus["totals_row_and_preamble"][0]
    result = classify(inspector, path)[0]

    assert result.row_count == 7
    assert result.client_id == "CLNT023"
    assert result.table.evidence["delimiter"] == "pipe"


# --- aggregate correctness targets ------------------------------------------


def test_correctness_targets_across_the_corpus(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """Measure NFR-4, NFR-5 and NFR-7 against the reference corpus.

    Two of the twelve fixtures are deliberately unroutable (the unattributable
    file, and the email advice which is a cash movement for a client whose
    filename pattern does not match). Everything else must attribute and
    resolve correctly.
    """
    attributable = {
        "late_arrival": "CLNT004",
        "filename_content_disagreement": "CLNT004",
        "exact_duplicate": "CLNT004",
        "redelivery_under_new_name": "CLNT004",
        "correction_after_dispatch": "CLNT004",
        "multi_date_file": "CLNT004",
        "four_price_columns": "CLNT004",
        "bare_price_header": "CLNT004",
        "totals_row_and_preamble": "CLNT023",
    }

    correct_client = 0
    business_days = 0
    total = 0

    for name, expected_client in attributable.items():
        path = corpus[name][0]
        for result in classify(inspector, path, f"arr-{name}"):
            total += 1
            if result.client_id == expected_client:
                correct_client += 1
            resolved = result.value_date.resolved
            assert resolved is not None
            calendar = inspector.registry.calendar_for(expected_client)
            assert calendar is not None
            if calendar.is_business_day(resolved):
                business_days += 1

    assert total >= 9
    # NFR-4: client attribution at or above 99 percent on the reference corpus.
    assert correct_client == total, f"attributed {correct_client}/{total}"
    # NFR-5: every resolved value date is a day the market was open.
    assert business_days == total


def test_unattributable_files_are_the_only_quarantines(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """NFR-7: quarantine rate stays low on well-formed files.

    A system that quarantines liberally is easy to make correct and useless in
    practice, so the rate is asserted rather than merely hoped for.
    """
    routable = [
        "late_arrival", "filename_content_disagreement", "four_price_columns",
        "bare_price_header", "multi_date_file", "totals_row_and_preamble",
    ]
    dispositions = []
    for name in routable:
        for result in classify(inspector, corpus[name][0], f"arr-{name}"):
            dispositions.append(result.score.disposition)

    quarantined = sum(1 for d in dispositions if d != confidence.DISPATCHED)
    assert quarantined == 0, f"{quarantined}/{len(dispositions)} well-formed files were held"


def test_every_dispatched_file_has_full_provenance(
    inspector: Inspector, corpus: dict[str, list[Path]]
) -> None:
    """NFR-6: no dispatched record carries a mapping without recorded evidence."""
    for name in ("late_arrival", "four_price_columns", "bare_price_header"):
        for result in classify(inspector, corpus[name][0], f"arr-{name}"):
            if result.score.disposition != confidence.DISPATCHED:
                continue
            for m in result.mappings:
                assert m.evidence, f"{name}: {m.source_field} has no evidence"
                assert m.tier is not None


def test_corpus_generation_is_reproducible(tmp_path: Path) -> None:
    """The same seed produces identical bytes.

    Without this a golden test failure is ambiguous: did the code change, or
    did the data?
    """
    a = ScenarioBuilder(tmp_path / "a", seed=99).build_all()
    b = ScenarioBuilder(tmp_path / "b", seed=99).build_all()

    assert [s.name for s in a] == [s.name for s in b]
    for sa, sb in zip(a, b, strict=True):
        for fa, fb in zip(sa.files, sb.files, strict=True):
            if fa.suffix == ".xlsx":
                continue  # workbooks embed a creation timestamp
            assert fa.read_bytes() == fb.read_bytes(), f"{sa.name}: {fa.name} differs"


def test_every_scenario_documents_what_it_breaks(tmp_path: Path) -> None:
    """A fixture nobody can explain is a fixture nobody will maintain."""
    for scenario in ScenarioBuilder(tmp_path).build_all():
        assert scenario.designed_to_break
        assert scenario.expected
        assert scenario.files
        assert all(p.exists() for p in scenario.files)
