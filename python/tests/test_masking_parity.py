"""Cross-language parity for the masking rule.

The Go suite writes its answers for a shared case table; this asserts the
Python implementation produces the same string for every case. Without this,
the two implementations drift and an account number eventually leaks from
whichever service was not updated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inspector import masking

TABLE = (
    Path(__file__).resolve().parents[2]
    / "go"
    / "internal"
    / "masking"
    / "testdata"
    / "masking_parity.json"
)


@pytest.fixture(autouse=True)
def _enabled() -> None:
    masking.set_enabled(True)


def test_parity_table_exists() -> None:
    assert TABLE.exists(), "run `go test ./internal/masking/` first"


@pytest.mark.parametrize("case", json.loads(TABLE.read_text()).items() if TABLE.exists() else [])
def test_python_matches_go(case: tuple[str, str]) -> None:
    raw, expected = case
    assert masking.account_number(raw) == expected


def test_short_identifiers_are_fully_masked() -> None:
    assert masking.account_number("8842") == "****"
    assert not any(ch.isdigit() for ch in masking.account_number("8842"))


def test_names_are_never_masked() -> None:
    assert masking.account_name("Meridian Global Macro") == "Meridian Global Macro"


def test_disabled_passes_through() -> None:
    masking.set_enabled(False)
    try:
        assert masking.account_number("8842-00119") == "8842-00119"
    finally:
        masking.set_enabled(True)
