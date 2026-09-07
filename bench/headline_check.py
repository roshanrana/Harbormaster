"""Schema check for metrics/headline.json.

The headline file feeds a results card. A tile with a misspelt accent or a bar
whose value exceeds its maximum renders as a blank or a lie, and neither is
noticed until someone looks at the card. So the producer validates what it
wrote before it exits, and a test validates the committed file, against the
one schema below.

The schema is deliberately closed: unknown keys are rejected rather than
ignored, because a renderer that silently drops a key is how a metric quietly
disappears from the card.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ACCENTS = frozenset({"teal", "blue", "amber", "violet", "red"})
STATUSES = frozenset({"ok", "pending", "blocked"})

TOP_LEVEL_KEYS = frozenset({"kpis", "bars", "facts"})
KPI_KEYS = frozenset({"label", "value", "note", "accent"})
BAR_ROW_KEYS = frozenset({"label", "value", "max", "display", "accent"})
FACT_ROW_KEYS = frozenset({"label", "value", "status"})

# KPI keys are consumed by a card configuration (kpi_order), so they must be
# stable identifiers rather than free text.
_KPI_KEY = re.compile(r"^[a-z][a-z0-9_]*$")


class HeadlineError(Exception):
    """The document does not match the headline schema."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_keys(problems: list[str], where: str, obj: Any, expected: frozenset[str]) -> bool:
    if not isinstance(obj, dict):
        problems.append(f"{where}: expected an object")
        return False
    missing = sorted(expected - obj.keys())
    extra = sorted(obj.keys() - expected)
    if missing:
        problems.append(f"{where}: missing keys {missing}")
    if extra:
        problems.append(f"{where}: unexpected keys {extra}")
    return not missing and not extra


def _check_strings(
    problems: list[str], where: str, obj: dict[str, Any], names: tuple[str, ...]
) -> None:
    for name in names:
        if name in obj and not isinstance(obj[name], str):
            problems.append(f"{where}.{name}: expected a string")


def _check_kpis(problems: list[str], kpis: Any) -> None:
    if not isinstance(kpis, dict) or not kpis:
        problems.append("kpis: expected a non-empty object")
        return
    for key, tile in kpis.items():
        where = f"kpis.{key}"
        if not _KPI_KEY.match(key):
            problems.append(f"{where}: key must be snake_case")
        if not _check_keys(problems, where, tile, KPI_KEYS):
            continue
        _check_strings(problems, where, tile, ("label", "value", "note", "accent"))
        if tile.get("accent") not in ACCENTS:
            problems.append(
                f"{where}.accent: {tile.get('accent')!r} is not one of {sorted(ACCENTS)}"
            )


def _check_bars(problems: list[str], bars: Any) -> None:
    if not _check_keys(problems, "bars", bars, frozenset({"title", "rows"})):
        return
    _check_strings(problems, "bars", bars, ("title",))
    rows = bars.get("rows")
    if not isinstance(rows, list) or not rows:
        problems.append("bars.rows: expected a non-empty list")
        return
    for i, row in enumerate(rows):
        where = f"bars.rows[{i}]"
        if not _check_keys(problems, where, row, BAR_ROW_KEYS):
            continue
        _check_strings(problems, where, row, ("label", "display", "accent"))
        if row.get("accent") not in ACCENTS:
            problems.append(
                f"{where}.accent: {row.get('accent')!r} is not one of {sorted(ACCENTS)}"
            )
        value, maximum = row.get("value"), row.get("max")
        if not _is_number(value) or not _is_number(maximum):
            problems.append(f"{where}: value and max must be numbers")
            continue
        if maximum <= 0:
            problems.append(f"{where}.max: must be positive")
        if value < 0 or value > maximum:
            problems.append(f"{where}: value {value} is outside [0, {maximum}]")


def _check_facts(problems: list[str], facts: Any) -> None:
    if not _check_keys(problems, "facts", facts, frozenset({"title", "rows"})):
        return
    _check_strings(problems, "facts", facts, ("title",))
    rows = facts.get("rows")
    if not isinstance(rows, list) or not rows:
        problems.append("facts.rows: expected a non-empty list")
        return
    for i, row in enumerate(rows):
        where = f"facts.rows[{i}]"
        if not _check_keys(problems, where, row, FACT_ROW_KEYS):
            continue
        _check_strings(problems, where, row, ("label", "value", "status"))
        if row.get("status") not in STATUSES:
            problems.append(
                f"{where}.status: {row.get('status')!r} is not one of {sorted(STATUSES)}"
            )


def problems_in(doc: Any) -> list[str]:
    """Return every schema violation found, or an empty list."""
    problems: list[str] = []
    if not _check_keys(problems, "headline", doc, TOP_LEVEL_KEYS):
        return problems
    _check_kpis(problems, doc["kpis"])
    _check_bars(problems, doc["bars"])
    _check_facts(problems, doc["facts"])
    return problems


def assert_valid(doc: Any) -> None:
    """Raise HeadlineError listing every violation, or return silently."""
    found = problems_in(doc)
    if found:
        raise HeadlineError("headline.json does not match the schema:\n  " + "\n  ".join(found))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: headline_check.py <path/to/headline.json>", file=sys.stderr)
        return 1
    path = Path(argv[1])
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 1
    found = problems_in(doc)
    for problem in found:
        print(problem, file=sys.stderr)
    if found:
        return 1
    print(f"{path}: valid headline ({len(doc['kpis'])} kpis, {len(doc['bars']['rows'])} bars)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
