"""What every parser produces, regardless of source format.

Six formats arrive (CSV, Excel, XML, FIXML, email text, JSON). Downstream
classification, mapping and value-date resolution should not care which. So
each parser's job ends at ``ParsedTable``: a header list, rows as strings, and
whatever structural evidence the format happened to reveal.

Rows stay as strings here on purpose. Type coercion needs to know what a column
*means* — whether "1,234" is a quantity with a thousands separator or a price
in a locale using comma decimals — and that is not known until after mapping.
Parsing that guesses types early destroys the information needed to guess well.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class ParsedTable:
    """Normalised output of any parser."""

    headers: list[str]
    rows: list[dict[str, str]]
    #: Free-form evidence the parser gathered: sheet name, XML root tag, the
    #: detected header row index, FIX message types seen. Carried into the
    #: audit record so a classification decision can be explained later.
    evidence: dict[str, str] = field(default_factory=dict)
    #: Non-fatal problems worth surfacing without failing the parse, e.g. a
    #: dropped totals row or a ragged line.
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(set(self.headers)) != len(self.headers):
            # Duplicate headers make a dict-based row ambiguous, and silently
            # keeping the last wins is exactly the kind of quiet data loss this
            # system is supposed to prevent.
            dupes = sorted({h for h in self.headers if self.headers.count(h) > 1})
            raise ParseError(f"duplicate column headers: {dupes}")

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def column(self, header: str) -> list[str]:
        """All values for one column, in row order."""
        return [r.get(header, "") for r in self.rows]


class ParseError(Exception):
    """The payload could not be parsed. Maps to the MALFORMED error class."""


@runtime_checkable
class Parser(Protocol):
    """One format's reader."""

    #: Value of SourceFormat this parser produces, e.g. "CSV".
    format_name: str

    def sniff(self, head: bytes, name: str) -> float:
        """Confidence in [0, 1] that this parser should handle the payload.

        Called with the first few kilobytes only. The filename is available but
        should be weak evidence at most: format is decided by content (FR-17),
        because a CSV named ``.txt`` and an xlsx named ``.csv`` both happen.
        """
        ...

    def parse(self, path: Path) -> ParsedTable:
        """Read the payload into a ParsedTable, or raise ParseError."""
        ...
