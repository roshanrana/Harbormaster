"""Delimited text (CSV, TSV, pipe-delimited).

The naive version of this file is four lines of ``csv.DictReader``. Real
counterparty extracts are not that tidy: they carry title banners above the
header row, blank spacer lines, a trailing "Total" row that is not a trade, and
occasionally a pipe delimiter because someone's mainframe emitted it that way.
Each of those produces a plausible-looking but wrong parse if ignored, so each
is handled explicitly here.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from inspector.parsers.base import ParsedTable, ParseError

# Rows whose first non-empty cell looks like one of these are summary lines
# appended below the data, not records.
_TOTAL_MARKERS = frozenset(
    {"total", "totals", "grandtotal", "subtotal", "sum", "count", "endofreport", "eof", "end"}
)

_CANDIDATE_DELIMITERS = (",", "\t", "|", ";")

# A header row should look like labels, not data. These are the signals.
_MAX_HEADER_SEARCH_ROWS = 25


def _norm(cell: str) -> str:
    return "".join(ch for ch in cell.lower() if ch.isalnum())


def _looks_numeric(cell: str) -> bool:
    stripped = cell.strip().replace(",", "").replace("$", "").replace("%", "")
    if stripped.startswith("(") and stripped.endswith(")"):
        stripped = stripped[1:-1]
    if not stripped:
        return False
    try:
        float(stripped)
    except ValueError:
        return False
    return True


class DelimitedParser:
    """Parser for comma, tab, pipe and semicolon separated text."""

    format_name = "CSV"

    def sniff(self, head: bytes, name: str) -> float:
        try:
            text = head.decode("utf-8-sig")
        except UnicodeDecodeError:
            return 0.0
        stripped = text.lstrip()
        if not stripped:
            return 0.0
        # Anything that is obviously another format defers, even if it happens
        # to contain commas.
        if stripped[0] in "<{[":
            return 0.0

        lines = [ln for ln in text.splitlines() if ln.strip()][:20]
        if len(lines) < 2:
            return 0.0

        delim, consistency = self._best_delimiter(lines)
        if delim is None:
            return 0.0

        score = 0.35 + 0.5 * consistency
        if name.lower().endswith((".csv", ".tsv", ".txt", ".psv")):
            score += 0.1
        return min(score, 0.97)

    def _best_delimiter(self, lines: list[str]) -> tuple[str | None, float]:
        """Pick the delimiter that splits lines into the most consistent shape.

        Consistency beats frequency: a description column full of commas can
        make ',' the most *common* character while '|' is the real delimiter,
        and only column-count agreement across lines reveals that.

        Lines where the delimiter does not appear at all are excluded from the
        modal calculation. A title banner above the header contains no commas,
        and letting those zero counts win the vote makes a perfectly ordinary
        CSV look delimiter-less.
        """
        best_delim: str | None = None
        best_score = 0.0
        best_agreement = 0.0

        for delim in _CANDIDATE_DELIMITERS:
            counts = [ln.count(delim) for ln in lines if ln.count(delim) > 0]
            if len(counts) < max(2, len(lines) // 3):
                continue
            modal = max(set(counts), key=counts.count)
            agreement = counts.count(modal) / len(counts)
            # Weight by column count so a two-column accidental match loses to
            # a twelve-column real one at equal agreement.
            score = agreement * min(1.0, modal / 6)
            if score > best_score:
                best_delim, best_score, best_agreement = delim, score, agreement
        return best_delim, best_agreement

    def parse(self, path: Path) -> ParsedTable:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Counterparty files from older systems are frequently latin-1.
            # Failing the whole arrival over one accented account name would
            # be a poor trade.
            text = raw.decode("latin-1")

        lines = text.splitlines()
        if not any(ln.strip() for ln in lines):
            raise ParseError("file is empty")

        sample = [ln for ln in lines if ln.strip()][:20]
        delim, _ = self._best_delimiter(sample)
        if delim is None:
            raise ParseError("no delimiter could be determined")

        grid = list(csv.reader(io.StringIO(text), delimiter=delim))
        grid = [row for row in grid if any(cell.strip() for cell in row)]
        if not grid:
            raise ParseError("file contains no non-empty rows")

        header_idx = self._find_header_row(grid)
        headers = self._dedupe(grid[header_idx])
        warnings: list[str] = []
        if header_idx > 0:
            warnings.append(f"skipped {header_idx} preamble row(s) above the header")

        rows: list[dict[str, str]] = []
        dropped_totals = 0
        for raw_row in grid[header_idx + 1 :]:
            if self._is_total_row(raw_row):
                dropped_totals += 1
                continue
            if len(raw_row) > len(headers):
                warnings.append("row had more cells than headers; extra cells ignored")
                raw_row = raw_row[: len(headers)]
            row = {
                h: (raw_row[i].strip() if i < len(raw_row) else "") for i, h in enumerate(headers)
            }
            rows.append(row)

        if dropped_totals:
            warnings.append(f"excluded {dropped_totals} summary row(s)")

        return ParsedTable(
            headers=headers,
            rows=rows,
            evidence={
                "delimiter": {",": "comma", "\t": "tab", "|": "pipe", ";": "semicolon"}[delim],
                "header_row_index": str(header_idx),
                "encoding": "utf-8" if raw[:3] != b"\xef\xbb\xbf" else "utf-8-bom",
            },
            warnings=warnings,
        )

    def _find_header_row(self, grid: list[list[str]]) -> int:
        """Locate the header among any title and spacer rows above it.

        Scored, not guessed: a header row has mostly non-empty, mostly
        non-numeric cells, and its width matches the rows beneath it. A title
        banner fails the width test; a data row fails the numeric test.
        """
        best_idx, best_score = 0, float("-inf")
        limit = min(len(grid), _MAX_HEADER_SEARCH_ROWS)
        widths = [len(r) for r in grid]
        # Ties break toward the wider row. A file with two title lines and two
        # data lines has an even split, and the wide shape is the data shape;
        # picking the narrow one makes the title banner look like the header.
        modal_width = max(set(widths), key=lambda w: (widths.count(w), w))

        for idx in range(limit):
            row = grid[idx]
            filled = [c for c in row if c.strip()]
            if not filled:
                continue
            non_numeric = sum(1 for c in filled if not _looks_numeric(c))
            score = 0.0
            score += 2.0 * (non_numeric / len(filled))
            score += 1.5 if len(row) == modal_width else 0.0
            score += 1.0 * (len(filled) / max(len(row), 1))
            # Later rows are less likely to be the header; a mild prior keeps
            # a stray text row deep in the file from winning.
            score -= 0.15 * idx
            if score > best_score:
                best_idx, best_score = idx, score
        return best_idx

    def _is_total_row(self, row: list[str]) -> bool:
        """A trailing summary line is not a record.

        Counting one as a trade inflates the reconciliation by a row and
        produces a break that looks like a genuine discrepancy, which is worse
        than an obvious failure because someone will investigate it.
        """
        first = next((cell for cell in row if cell.strip()), "")
        return _norm(first) in _TOTAL_MARKERS

    def _dedupe(self, headers: list[str]) -> list[str]:
        """Make headers unique, preserving the original text where possible.

        Wide extracts sometimes repeat a header ("Price", "Price"). Silently
        keeping the last would drop a column, so they are suffixed and both
        survive into mapping, where the price disambiguator can tell them apart.
        """
        seen: dict[str, int] = {}
        out: list[str] = []
        for i, h in enumerate(headers):
            name = h.strip() or f"column_{i + 1}"
            if name in seen:
                seen[name] += 1
                name = f"{name}__{seen[name]}"
            else:
                seen[name] = 0
            out.append(name)
        return out
