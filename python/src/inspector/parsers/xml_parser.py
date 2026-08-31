"""Generic XML extracts.

There is no single XML schema for trade and position reports; every venue has
its own. Rather than carry a schema per counterparty, this parser finds the
repeating element that constitutes a record and flattens each one into a flat
row of dotted paths.

Finding the record element is the whole problem. The naive answer, "take the
children of the root", is wrong for the common shape where records sit under a
wrapper (``<TradeExtract><Trades><Trade/>...``). The answer used here is that
the record element is the one that repeats most, weighted by how much content
each instance carries, which is stable across the layouts actually seen.

Source field names are the dotted paths, so provenance survives into the audit
record: an operator can see that ``net_amount`` came from
``Trade.SettlementAmount`` rather than from a column that happened to be
nearby.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from inspector.parsers.base import ParsedTable, ParseError

# Attributes are prefixed so a flattened attribute cannot silently collide
# with a child element of the same name.
ATTR_PREFIX = "@"

_MIN_RECORDS = 2


def _localname(tag: Any) -> str:
    """Strip any XML namespace. Namespaces vary between a client's test and
    production endpoints and carry no mapping signal."""
    text = str(tag)
    return text.rsplit("}", 1)[-1] if "}" in text else text


class XMLParser:
    """Parser for generic XML extracts."""

    format_name = "XML"

    def sniff(self, head: bytes, name: str) -> float:
        try:
            text = head.decode("utf-8-sig", errors="ignore").lstrip()
        except (UnicodeDecodeError, AttributeError):
            return 0.0
        if not text.startswith("<"):
            return 0.0
        # FIXML is XML, but it has a dedicated parser that understands its tag
        # semantics, so defer to it rather than flattening it generically.
        head_upper = text[:2000].upper()
        if "<FIXML" in head_upper or "<EXECRPT" in head_upper:
            return 0.3
        score = 0.85
        if name.lower().endswith(".xml"):
            score = 0.92
        return score

    def parse(self, path: Path) -> ParsedTable:
        from lxml import etree

        try:
            tree = etree.parse(str(path))
        except etree.XMLSyntaxError as exc:
            raise ParseError(f"malformed XML: {exc}") from exc

        root = tree.getroot()
        if root is None:
            raise ParseError("XML document has no root element")

        record_tag, records = self._find_records(root)
        if not records:
            raise ParseError("no repeating record element could be identified")

        rows: list[dict[str, str]] = []
        headers: list[str] = []
        seen: set[str] = set()

        for element in records:
            flat = self._flatten(element)
            for key in flat:
                if key not in seen:
                    seen.add(key)
                    headers.append(key)
            rows.append(flat)

        # Elements absent from some records must still exist as empty cells,
        # or a downstream lookup silently returns nothing for a real column.
        for row in rows:
            for key in headers:
                row.setdefault(key, "")

        return ParsedTable(
            headers=headers,
            rows=rows,
            evidence={
                "root": _localname(root.tag),
                "record_element": record_tag,
                "record_count": str(len(records)),
            },
        )

    def _find_records(self, root: Any) -> tuple[str, list[Any]]:
        """Locate the element that repeats to form the records.

        Scored by how many instances exist and how much content each carries,
        so a repeated ``<Currency>`` inside every record loses to the record
        element itself.
        """
        by_tag: dict[str, list[Any]] = defaultdict(list)
        for element in root.iter():
            if element is root:
                continue
            by_tag[_localname(element.tag)].append(element)

        best_tag, best_elements, best_score = "", [], float("-inf")
        for tag, elements in by_tag.items():
            if len(elements) < _MIN_RECORDS:
                continue
            avg_children = sum(len(list(e)) for e in elements) / len(elements)
            avg_attrs = sum(len(e.attrib) for e in elements) / len(elements)
            content = avg_children + avg_attrs
            if content < 1:
                # A repeated leaf is a field, not a record.
                continue
            score = content * 10.0 + min(len(elements), 100)
            if score > best_score:
                best_tag, best_elements, best_score = tag, elements, score

        if not best_elements:
            # A single record is legitimate; fall back to the most substantial
            # direct child of the root.
            children = list(root)
            if children:
                richest = max(children, key=lambda e: len(list(e)) + len(e.attrib))
                if len(list(richest)) + len(richest.attrib) > 0:
                    return _localname(richest.tag), [richest]
        return best_tag, best_elements

    def _flatten(self, element: Any, prefix: str = "") -> dict[str, str]:
        """Flatten one record into dotted paths."""
        out: dict[str, str] = {}

        for key, value in element.attrib.items():
            name = f"{prefix}{ATTR_PREFIX}{_localname(key)}"
            out[name] = str(value).strip()

        children = list(element)
        if not children:
            text = (element.text or "").strip()
            if text and prefix:
                out[prefix.rstrip(".")] = text
            return out

        counts: dict[str, int] = defaultdict(int)
        for child in children:
            tag = _localname(child.tag)
            counts[tag] += 1

        occurrences: dict[str, int] = defaultdict(int)
        for child in children:
            tag = _localname(child.tag)
            # A repeating group inside a record is suffixed rather than
            # overwritten, so a two-leg trade keeps both legs.
            if counts[tag] > 1:
                index = occurrences[tag]
                occurrences[tag] += 1
                name = f"{prefix}{tag}[{index}]"
            else:
                name = f"{prefix}{tag}"

            grandchildren = list(child)
            if grandchildren or child.attrib:
                out.update(self._flatten(child, prefix=f"{name}."))
                text = (child.text or "").strip()
                if text:
                    out[name] = text
            else:
                out[name] = (child.text or "").strip()
        return out
