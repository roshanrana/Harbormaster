"""Account-number masking, kept identical to ``go/internal/masking``.

The rule (ADR-011): mask account *numbers* to their last four characters, never
mask account *names*. Short identifiers are masked entirely, because revealing
"the last four" of a four-character value reveals all of it.

Two implementations of one rule is a risk, so ``tests/test_masking_parity.py``
asserts the Python output matches the Go output character for character on a
shared case table.
"""

from __future__ import annotations

import os

MIN_REVEALED = 4

_enabled = os.environ.get("HM_MASK_ACCOUNTS", "").lower() != "false"


def set_enabled(value: bool) -> None:
    """Override the environment. Intended for tests."""
    global _enabled
    _enabled = value


def enabled() -> bool:
    return _enabled


def account_number(value: str) -> str:
    """Mask all but the trailing four characters."""
    if not _enabled or not value:
        return value
    if len(value) <= MIN_REVEALED:
        return "*" * len(value)
    return "*" * (len(value) - MIN_REVEALED) + value[-MIN_REVEALED:]


def account_numbers(values: list[str]) -> list[str]:
    return [account_number(v) for v in values]


def account_name(value: str) -> str:
    """Deliberately a no-op, so the decision not to mask names is visible."""
    return value
