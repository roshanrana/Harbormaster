"""JSON payloads.

These arrive on the queue ingress rather than the landing directory, but the
parsing problem is the same: find the records inside an arbitrary envelope and
flatten each into a row.

Real payloads nest. Economics sit under ``economics``, dates under ``dates``,
the account under ``account``. Flattening to dotted paths keeps provenance
(``economics.netAmount`` is visibly where the amount came from) while giving the
mapping layer a flat namespace to work in. The alias dictionary matches on the
leaf name, so nesting costs nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from inspector.parsers.base import ParsedTable, ParseError

# Envelope keys that commonly hold the record array.
_RECORD_KEYS = (
    "records",
    "rows",
    "data",
    "items",
    "trades",
    "positions",
    "entries",
    "messages",
    "results",
    "payload",
    "transactions",
    "movements",
)

_MAX_DEPTH = 8


class JSONParser:
    """Parser for JSON documents and queue payloads."""

    format_name = "JSON"

    def sniff(self, head: bytes, name: str) -> float:
        text = head.decode("utf-8-sig", errors="ignore").lstrip()
        if not text or text[0] not in "{[":
            return 0.0
        score = 0.85
        if name.lower().endswith(".json"):
            score = 0.95
        return score

    def parse(self, path: Path) -> ParsedTable:
        raw = path.read_bytes()
        try:
            document = json.loads(raw.decode("utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ParseError(f"malformed JSON: {exc}") from exc

        records, envelope, source = self._find_records(document)
        if not records:
            raise ParseError("no record array or object could be identified")

        rows: list[dict[str, str]] = []
        headers: list[str] = []
        seen: set[str] = set()

        for record in records:
            flat = flatten(record)
            # Envelope fields (venue, messageType) are real evidence about the
            # file and belong on every row rather than being discarded.
            for key, value in envelope.items():
                flat.setdefault(key, value)
            for key in flat:
                if key not in seen:
                    seen.add(key)
                    headers.append(key)
            rows.append(flat)

        for row in rows:
            for key in headers:
                row.setdefault(key, "")

        return ParsedTable(
            headers=headers,
            rows=rows,
            evidence={"records_at": source, "record_count": str(len(records))},
        )

    def _find_records(self, document: Any) -> tuple[list[dict[str, Any]], dict[str, str], str]:
        """Locate the records and any scalar envelope fields around them."""
        if isinstance(document, list):
            return [r for r in document if isinstance(r, dict)], {}, "$"

        if not isinstance(document, dict):
            return [], {}, ""

        envelope = {
            k: str(v)
            for k, v in document.items()
            if not isinstance(v, (dict, list)) and v is not None
        }

        # A named record array is the common shape.
        for key in _RECORD_KEYS:
            value = document.get(key)
            if isinstance(value, list) and value and all(isinstance(r, dict) for r in value):
                return value, envelope, key

        # Otherwise the longest list of objects anywhere shallow in the
        # document is the records.
        best_key = ""
        best: list[dict[str, Any]] = []
        for key, value in document.items():
            is_records = (
                isinstance(value, list) and value and all(isinstance(r, dict) for r in value)
            )
            if is_records and len(value) > len(best):
                best_key, best = key, value
        if best:
            return best, envelope, best_key

        # A single-record document is legitimate.
        nested = {k: v for k, v in document.items() if isinstance(v, dict)}
        if nested or envelope:
            return [document], {}, "$ (single record)"
        return [], {}, ""


def flatten(value: Any, prefix: str = "", depth: int = 0) -> dict[str, str]:
    """Flatten nested JSON into dotted paths.

    Depth is bounded. A pathological or cyclic-looking document should degrade
    to a truncated row rather than exhausting the stack, because an arrival
    that crashes the consumer blocks its whole partition.
    """
    out: dict[str, str] = {}
    if depth > _MAX_DEPTH:
        if prefix:
            out[prefix.rstrip(".")] = json.dumps(value)[:512]
        return out

    if isinstance(value, dict):
        for key, item in value.items():
            out.update(flatten(item, prefix=f"{prefix}{key}.", depth=depth + 1))
        return out

    if isinstance(value, list):
        if all(not isinstance(i, (dict, list)) for i in value):
            # A list of scalars is one cell, not many columns.
            out[prefix.rstrip(".")] = ", ".join(str(i) for i in value)
            return out
        for index, item in enumerate(value):
            out.update(flatten(item, prefix=f"{prefix}[{index}].", depth=depth + 1))
        return out

    name = prefix.rstrip(".")
    if name:
        out[name] = "" if value is None else str(value)
    return out
