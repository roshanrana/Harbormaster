"""Working out which client a file belongs to.

Three independent kinds of evidence are available, and they differ sharply in
how much they prove:

- **Account identifiers in the contents.** Near-conclusive. An account number
  belongs to exactly one client, and it is written by the client's own system.
- **A configured filename pattern.** Good evidence, and usually right, but
  filenames are set by whatever produced the batch and are the first thing to
  go wrong when a client changes vendors.
- **Venue and format shape.** Weak on its own. Useful for confirming or
  contradicting the other two, not for deciding alone.

The design rule is that agreement raises confidence and disagreement lowers it,
rather than a priority list where the strongest available signal simply wins.
A file whose name says one client and whose account numbers say another is not
a file we should route confidently in either direction; it is a file a human
should look at, and the score needs to say so.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from inspector.mapping.canonical import Domain
from inspector.registry import Client, Registry

# Account identifiers are distinctive enough to scan for directly. The pattern
# is intentionally loose because formats vary across venues (8842-00119,
# DE-77120-004, HK-4471-0021), and the registry does the actual validation.
_ACCOUNT_CANDIDATE = re.compile(
    r"\b[A-Z0-9]{2,6}[-_][A-Z0-9]{3,6}(?:[-_][A-Z0-9]{2,6})?\b", re.IGNORECASE
)

CONF_ACCOUNT_MATCH = 0.95
CONF_FILENAME_MATCH = 0.80
CONF_BOTH_AGREE = 0.99
CONF_CONFLICT = 0.45
CONF_NONE = 0.0

# Columns most likely to carry an account identifier, checked before falling
# back to scanning every cell.
_ACCOUNT_COLUMN_HINTS = (
    "accountid",
    "account",
    "acctno",
    "acctnum",
    "accountnumber",
    "acctid",
    "accountno",
    "clientaccount",
    "custodyaccount",
    "safekeepingaccount",
    "portfolioid",
    "book",
    "bookid",
    "subaccount",
    "clearingaccount",
    "acct",
)


@dataclass(slots=True)
class Attribution:
    """Which client a file belongs to, and why we think so."""

    client_id: str | None
    confidence: float
    account_ids: list[str] = field(default_factory=list)
    domain: str = Domain.UNKNOWN
    source_hint: str = ""
    filename_date_text: str = ""
    evidence: list[str] = field(default_factory=list)
    conflict: bool = False

    @property
    def resolved(self) -> bool:
        return self.client_id is not None


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def find_account_ids(
    headers: list[str], rows: list[dict[str, str]], known: dict[str, str], limit: int = 500
) -> list[str]:
    """Extract account identifiers that the registry recognises.

    Only known accounts are returned. An unrecognised identifier is not
    evidence of anything: it might be a new account, or a trade reference that
    happens to look like one.
    """
    found: list[str] = []
    seen: set[str] = set()

    account_columns = [h for h in headers if _norm(h) in _ACCOUNT_COLUMN_HINTS]
    scan_columns = account_columns or headers

    for row in rows[:limit]:
        for header in scan_columns:
            value = (row.get(header) or "").strip()
            if not value:
                continue
            if value in known and value not in seen:
                seen.add(value)
                found.append(value)
                continue
            # Only fall back to pattern scanning outside the obvious columns.
            if not account_columns:
                for candidate in _ACCOUNT_CANDIDATE.findall(value):
                    if candidate in known and candidate not in seen:
                        seen.add(candidate)
                        found.append(candidate)
    return found


def attribute(
    *,
    filename: str,
    headers: list[str],
    rows: list[dict[str, str]],
    registry: Registry,
) -> Attribution:
    """Identify the owning client."""
    evidence: list[str] = []

    filename_client, domain, source_hint, date_text = _match_filename(filename, registry)
    if filename_client:
        evidence.append(f"filename matches {filename_client.client_id} pattern")

    known = registry.all_account_ids()
    account_ids = find_account_ids(headers, rows, known)
    account_clients = Counter(known[a] for a in account_ids)

    account_client_id: str | None = None
    if account_clients:
        account_client_id, hits = account_clients.most_common(1)[0]
        evidence.append(
            f"{len(account_ids)} known account identifier(s) resolving to {account_client_id}"
        )
        if len(account_clients) > 1:
            # One file carrying accounts from two clients is not something to
            # route on a majority vote.
            evidence.append(
                f"contents reference {len(account_clients)} different clients: "
                + ", ".join(sorted(account_clients))
            )
            return Attribution(
                client_id=None,
                confidence=CONF_CONFLICT,
                account_ids=account_ids,
                domain=domain or Domain.UNKNOWN,
                source_hint=source_hint,
                filename_date_text=date_text,
                evidence=evidence,
                conflict=True,
            )
        del hits

    filename_client_id = filename_client.client_id if filename_client else None

    if account_client_id and filename_client_id:
        if account_client_id == filename_client_id:
            evidence.append("filename and contents agree")
            return _build(
                account_client_id,
                CONF_BOTH_AGREE,
                account_ids,
                domain,
                source_hint,
                date_text,
                evidence,
                registry,
                conflict=False,
            )
        # Disagreement. Contents are stronger evidence, but a conflict is a
        # review case rather than a confident routing decision (FR-30).
        evidence.append(
            f"filename says {filename_client_id} but account identifiers say {account_client_id}"
        )
        return _build(
            account_client_id,
            CONF_CONFLICT,
            account_ids,
            domain,
            source_hint,
            date_text,
            evidence,
            registry,
            conflict=True,
        )

    if account_client_id:
        return _build(
            account_client_id,
            CONF_ACCOUNT_MATCH,
            account_ids,
            domain,
            source_hint,
            date_text,
            evidence,
            registry,
            conflict=False,
        )

    if filename_client_id:
        return _build(
            filename_client_id,
            CONF_FILENAME_MATCH,
            account_ids,
            domain,
            source_hint,
            date_text,
            evidence,
            registry,
            conflict=False,
        )

    evidence.append("no filename pattern matched and no known account identifiers were found")
    return Attribution(
        client_id=None,
        confidence=CONF_NONE,
        account_ids=[],
        domain=Domain.UNKNOWN,
        evidence=evidence,
    )


def _match_filename(filename: str, registry: Registry) -> tuple[Client | None, str, str, str]:
    for client in registry.clients:
        for hint in client.filename_hints:
            hit = hint.match(filename)
            if hit is not None:
                domain, date_text = hit
                return client, domain or Domain.UNKNOWN, hint.source_hint, date_text
    return None, "", "", ""


def _build(
    client_id: str,
    confidence: float,
    account_ids: list[str],
    domain: str,
    source_hint: str,
    date_text: str,
    evidence: list[str],
    registry: Registry,
    *,
    conflict: bool,
) -> Attribution:
    # If the filename gave no domain, fall back to the client's sole
    # expectation when there is only one. Guessing between several would be
    # worse than leaving it unknown for the domain classifier to decide.
    if not domain or domain == Domain.UNKNOWN:
        client = registry.client(client_id)
        if client and len(client.expectations) == 1:
            domain = client.expectations[0].domain
            evidence.append(f"client has a single expectation; domain taken as {domain}")
    return Attribution(
        client_id=client_id,
        confidence=confidence,
        account_ids=account_ids,
        domain=domain or Domain.UNKNOWN,
        source_hint=source_hint,
        filename_date_text=date_text,
        evidence=evidence,
        conflict=conflict,
    )
