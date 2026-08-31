"""Free-text email bodies.

Some counterparties send cash and collateral advices as prose. There is no
delimiter, no schema and no header row: just a person describing three
movements in a sentence each, differently each time.

The approach is conservative on purpose. Extraction is line-oriented and every
line must yield an amount and a currency to count as a movement; a line that
looks nearly right produces nothing rather than a half-populated record. The
per-line confidence is carried out as a column so the confidence layer can see
how much of this file was actually understood, and a body that yields only
partial matches should end up in the review queue rather than being dispatched.

An operator correcting one of these in the review screen is a better outcome
than a plausible-looking cash reconciliation built from a misread sentence.
"""

from __future__ import annotations

import re
from pathlib import Path

from inspector.parsers.base import ParsedTable, ParseError

# ISO 4217 codes seen across the venues in scope, plus their symbols.
_CURRENCIES = ("USD", "EUR", "GBP", "JPY", "CHF", "HKD", "AUD", "CAD", "SEK", "SGD")
_SYMBOL_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}

_AMOUNT = re.compile(
    r"(?P<symbol>[$€£¥])?\s*"
    r"(?P<number>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?!\d)"
)
_CURRENCY_CODE = re.compile(r"\b(" + "|".join(_CURRENCIES) + r")\b")

# Account references: alphanumeric groups separated by hyphens or underscores.
_ACCOUNT = re.compile(r"\b[A-Z0-9]{2,6}[-_][A-Z0-9]{2,6}(?:[-_][A-Z0-9]{2,6})?\b")

_DATE_PATTERNS = (
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})\b"),
    re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b"),
    re.compile(r"\b(\d{1,2}-[A-Za-z]{3}-\d{4})\b"),
)

_DEBIT_WORDS = ("debit", "withdrawal", "outgoing", "paid", "payment out", "sent")
_CREDIT_WORDS = ("credit", "deposit", "incoming", "received", "receipt")

# Headers this parser emits. Deliberately named so the Tier 1 alias dictionary
# resolves them without special-casing.
HEADERS = (
    "Account ID",
    "Net Amount",
    "Currency",
    "Value Date",
    "Direction",
    "Extraction Confidence",
    "Source Line",
)

_EMAIL_MARKERS = ("from:", "to:", "subject:", "sent:", "cc:", "date:")

# A movement line needs at least an amount and a currency to be recorded.
_MIN_LINE_CONFIDENCE = 0.5


class EmailTextParser:
    """Parser for free-text cash and collateral advices."""

    format_name = "EMAIL_TEXT"

    def sniff(self, head: bytes, name: str) -> float:
        text = head.decode("utf-8-sig", errors="ignore")
        stripped = text.lstrip()
        if not stripped or stripped[0] in "<{[":
            return 0.0

        lowered = text[:4000].lower()
        header_hits = sum(1 for marker in _EMAIL_MARKERS if marker in lowered)
        if header_hits >= 2:
            return 0.93

        # Prose without email headers: prefer this parser only if the text does
        # not look tabular, so a CSV never lands here.
        lines = [ln for ln in text.splitlines() if ln.strip()][:20]
        if len(lines) < 2:
            return 0.0
        delimited = sum(1 for ln in lines if ln.count(",") >= 3 or ln.count("|") >= 3)
        if delimited > len(lines) / 2:
            return 0.0
        money = sum(
            1 for ln in lines if _CURRENCY_CODE.search(ln) or any(s in ln for s in _SYMBOL_CURRENCY)
        )
        if money >= 2 and name.lower().endswith((".txt", ".eml", ".msg")):
            return 0.6
        return 0.0

    def parse(self, path: Path) -> ParsedTable:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")

        if not text.strip():
            raise ParseError("email body is empty")

        subject = self._subject(text)
        # A date in the subject line is a reasonable default for lines that
        # do not carry one of their own.
        default_date = self._first_date(subject) or self._first_date(text)

        rows: list[dict[str, str]] = []
        warnings: list[str] = []
        near_misses = 0

        for line in text.splitlines():
            candidate = line.strip()
            if not candidate or self._is_header_line(candidate):
                continue
            movement = self._extract(candidate, default_date)
            if movement is None:
                if self._looks_like_a_movement(candidate):
                    near_misses += 1
                continue
            rows.append(movement)

        if not rows:
            raise ParseError("no cash movements could be extracted from the body")

        if near_misses:
            # Surfaced rather than swallowed: a line that looked like a
            # movement but did not parse is exactly what a reviewer needs to
            # see, because it may be a movement the reconciliation is missing.
            warnings.append(
                f"{near_misses} line(s) resembled a movement but could not be extracted"
            )

        return ParsedTable(
            headers=list(HEADERS),
            rows=rows,
            evidence={
                "subject": subject[:200],
                "movements_found": str(len(rows)),
                "near_misses": str(near_misses),
            },
            warnings=warnings,
        )

    # --- extraction --------------------------------------------------------

    def _extract(self, line: str, default_date: str | None) -> dict[str, str] | None:
        currency = self._currency(line)
        amount = self._amount(line)
        if currency is None or amount is None:
            return None

        direction = self._direction(line)
        signed = amount if direction != "DEBIT" else f"-{amount}"
        account_match = _ACCOUNT.search(line)
        value_date = self._first_date(line) or default_date or ""

        # Confidence reflects how much of the record was actually found, and
        # travels downstream so a thinly-understood advice is quarantined.
        confidence = 0.5
        if account_match:
            confidence += 0.2
        if value_date:
            confidence += 0.2
        if direction != "UNKNOWN":
            confidence += 0.1

        if confidence < _MIN_LINE_CONFIDENCE:
            return None

        return {
            "Account ID": account_match.group(0) if account_match else "",
            "Net Amount": signed,
            "Currency": currency,
            "Value Date": value_date,
            "Direction": direction,
            "Extraction Confidence": f"{min(confidence, 1.0):.2f}",
            "Source Line": line[:300],
        }

    def _currency(self, line: str) -> str | None:
        code = _CURRENCY_CODE.search(line)
        if code:
            return code.group(1)
        for symbol, iso in _SYMBOL_CURRENCY.items():
            if symbol in line:
                return iso
        return None

    def _amount(self, line: str) -> str | None:
        """Pick the monetary amount, not an account number or a date part."""
        best: str | None = None
        best_value = -1.0
        for match in _AMOUNT.finditer(line):
            number = match.group("number")
            if "," not in number and "." not in number and len(number) >= 5:
                # A long bare integer is more likely an identifier than money.
                continue
            try:
                value = float(number.replace(",", ""))
            except ValueError:
                continue
            if 1900 <= value <= 2100 and "." not in number and "," not in number:
                continue  # a year
            has_marker = bool(match.group("symbol")) or "," in number or "." in number
            if not has_marker:
                continue
            if value > best_value:
                best, best_value = number.replace(",", ""), value
        return best

    def _direction(self, line: str) -> str:
        lowered = line.lower()
        if any(word in lowered for word in _DEBIT_WORDS):
            return "DEBIT"
        if any(word in lowered for word in _CREDIT_WORDS):
            return "CREDIT"
        if "(" in line and ")" in line and any(ch.isdigit() for ch in line):
            return "DEBIT"  # accounting parentheses
        return "UNKNOWN"

    def _looks_like_a_movement(self, line: str) -> bool:
        return bool(_ACCOUNT.search(line)) or self._currency(line) is not None

    def _is_header_line(self, line: str) -> bool:
        lowered = line.lower()
        return any(lowered.startswith(marker) for marker in _EMAIL_MARKERS)

    def _subject(self, text: str) -> str:
        for line in text.splitlines()[:20]:
            if line.lower().startswith("subject:"):
                return line.split(":", 1)[1].strip()
        return ""

    def _first_date(self, text: str) -> str | None:
        from inspector.valuedate import parse_date

        for pattern in _DATE_PATTERNS:
            match = pattern.search(text)
            if match:
                parsed = parse_date(match.group(1))
                if parsed:
                    return parsed.isoformat()
                # "28 August 2026" is not in the numeric formats; try directly.
                try:
                    from datetime import datetime

                    return datetime.strptime(match.group(1), "%d %B %Y").date().isoformat()
                except ValueError:
                    continue
        return None
