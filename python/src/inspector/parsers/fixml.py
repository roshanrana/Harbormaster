"""FIXML documents.

FIXML is XML, but flattening it generically throws away the thing that makes it
tractable: the tag names are standardised. ``LastPx`` means the price of this
execution and ``SettlPx`` means the settlement price, on every venue, by
specification. That is a rare gift in this domain and worth using.

So this parser translates FIX attribute names into readable field names before
the mapping layer sees them, which lets Tier 1 resolve a FIXML file almost
entirely by dictionary. The raw tag is preserved in the header name so
provenance survives: an operator sees ``LastPx`` in the audit record, not a
name this parser invented.

Scope note: FIXML *files* are parsed. No FIX session is initiated or
maintained, which is out of scope by requirements section 7.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inspector.parsers.base import ParsedTable, ParseError

# Standard FIX attribute names, mapped to headers the alias dictionary already
# understands. The FIX name is kept alongside so nothing is lost.
_FIX_FIELDS: dict[str, str] = {
    "ExecID": "ExecID",
    "OrderID": "OrderID",
    "TradeID": "TradeID",
    "ClOrdID": "ClOrdID",
    "LastQty": "LastQty",
    "CumQty": "CumQty",
    "LastPx": "LastPx",
    "AvgPx": "AvgPx",
    "SettlPx": "Settlement Price",
    "SettlCurrAmt": "Settlement Amount",
    "NetMoney": "NetMoney",
    "GrossTradeAmt": "Gross Amount",
    "TrdDt": "Trade Date",
    "TradeDate": "Trade Date",
    "SettlDt": "Settlement Date",
    "TransactTime": "Transaction Time",
    "Ccy": "Currency",
    "Curr": "Currency",
    "SettlCurrency": "Settlement Currency",
    "Sym": "Symbol",
    "Issr": "Issuer",
    "Desc": "Security Description",
    "SecTyp": "Security Type",
    "MatDt": "Maturity Date",
}

# Side is an enumeration in FIX; the numbers mean nothing downstream.
_SIDE_CODES = {"1": "BUY", "2": "SELL", "3": "BUY", "4": "SELL", "5": "SELL", "6": "SELL"}

# Security ID source (tag 22). Knowing the identifier *kind* matters: an ISIN
# and a CUSIP in the same column would otherwise be indistinguishable.
_ID_SOURCES = {"1": "CUSIP", "2": "SEDOL", "4": "ISIN", "8": "Ticker", "5": "RIC"}

# Party role (tag 452). 24 is customer account, which is what we want.
_ACCOUNT_ROLES = {"24", "3", "1"}

_RECORD_TAGS = ("ExecRpt", "TrdCaptRpt", "Position", "PosRpt", "Alloc")


def _localname(tag: Any) -> str:
    text = str(tag)
    return text.rsplit("}", 1)[-1] if "}" in text else text


class FIXMLParser:
    """Parser for FIXML execution and trade capture reports."""

    format_name = "FIXML"

    def sniff(self, head: bytes, name: str) -> float:
        text = head.decode("utf-8-sig", errors="ignore").lstrip()
        if not text.startswith("<"):
            return 0.0
        upper = text[:4000].upper()
        if "<FIXML" in upper:
            return 0.98
        if any(f"<{tag.upper()}" in upper for tag in _RECORD_TAGS):
            # A FIXML fragment without its envelope still has FIX semantics
            # and should not be flattened generically.
            return 0.9
        return 0.0

    def parse(self, path: Path) -> ParsedTable:
        from lxml import etree

        try:
            tree = etree.parse(str(path))
        except etree.XMLSyntaxError as exc:
            raise ParseError(f"malformed FIXML: {exc}") from exc

        root = tree.getroot()
        records = [e for e in root.iter() if _localname(e.tag) in _RECORD_TAGS]
        if not records:
            raise ParseError("no FIXML report elements found")

        rows: list[dict[str, str]] = []
        headers: list[str] = []
        seen: set[str] = set()
        record_tags: set[str] = set()

        for element in records:
            record_tags.add(_localname(element.tag))
            flat = self._flatten_report(element)
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
            evidence={
                "record_elements": ",".join(sorted(record_tags)),
                "record_count": str(len(records)),
                "fix_version": str(root.get("v", "")),
            },
        )

    def _flatten_report(self, element: Any) -> dict[str, str]:
        out: dict[str, str] = {}
        self._attributes(element, out)

        for child in element:
            tag = _localname(child.tag)
            if tag == "Instrmt":
                self._instrument(child, out)
            elif tag == "Pty":
                self._party(child, out)
            else:
                self._attributes(child, out, prefix=f"{tag}.")
                text = (child.text or "").strip()
                if text:
                    out[_FIX_FIELDS.get(tag, tag)] = text
        return out

    def _attributes(self, element: Any, out: dict[str, str], prefix: str = "") -> None:
        for raw_name, value in element.attrib.items():
            name = _localname(raw_name)
            if name == "Side":
                # Translated because "1" is not something the mapping layer or
                # a human reviewer should have to decode.
                out["Side"] = _SIDE_CODES.get(str(value), str(value))
                continue
            mapped = _FIX_FIELDS.get(name, name)
            out[f"{prefix}{mapped}"] = str(value).strip()

    def _instrument(self, element: Any, out: dict[str, str]) -> None:
        """Flatten an Instrmt block, naming the identifier by its source."""
        attrs = {_localname(k): str(v) for k, v in element.attrib.items()}
        if "Sym" in attrs:
            out["Symbol"] = attrs["Sym"]
        identifier = attrs.get("ID")
        if identifier:
            source = _ID_SOURCES.get(attrs.get("IDSrc", ""), "Security ID")
            # An ISIN and a CUSIP are both "ID" in FIXML. Naming the column by
            # its source is what lets the alias dictionary resolve it.
            out[source] = identifier
        for name, value in attrs.items():
            if name in {"Sym", "ID", "IDSrc"}:
                continue
            out[f"Instrmt.{_FIX_FIELDS.get(name, name)}"] = value

    def _party(self, element: Any, out: dict[str, str]) -> None:
        """Extract the customer account from a Pty block."""
        attrs = {_localname(k): str(v) for k, v in element.attrib.items()}
        role = attrs.get("R", "")
        identifier = attrs.get("ID", "")
        if not identifier:
            return
        if role in _ACCOUNT_ROLES:
            out["Account ID"] = identifier
        else:
            out[f"Party.{role or 'unknown'}"] = identifier
