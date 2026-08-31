"""Client configuration and business calendars, for the Python services.

This reads the same YAML files under ``config/`` that the Go registry reads.
Both languages parse the configuration rather than one of them serving it to
the other: the alternative is a startup-time dependency between Inspector and
a control-plane API, which buys nothing and means neither service can start
alone. The configuration is a file on disk; two readers of a file is fine.

What is *not* duplicated is business-day arithmetic semantics. The rules here
match ``go/internal/registry`` deliberately, and
``tests/test_calendar_parity.py`` asserts the two agree on a shared table of
dates, because a value date that resolves differently in the two services is
the kind of bug that produces a reconciliation against the wrong day.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

_WEEKDAYS = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}

MAX_CALENDAR_STEP_DAYS = 30


class ConfigError(Exception):
    """Configuration could not be loaded. Maps to the CONFIG error class."""


@dataclass(slots=True)
class Account:
    id: str
    name: str
    venues: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FilenameHint:
    pattern: re.Pattern[str]
    domain_map: dict[str, str] = field(default_factory=dict)
    domain: str = ""
    source_hint: str = ""

    def match(self, name: str) -> tuple[str, str] | None:
        """Return (domain, date_text) if the filename matches."""
        m = self.pattern.match(name)
        if not m:
            return None
        groups = m.groupdict()
        domain = self.domain
        raw = groups.get("domain")
        if raw and raw in self.domain_map:
            domain = self.domain_map[raw]
        return domain, groups.get("date") or ""


@dataclass(slots=True)
class Expectation:
    id: str
    domain: str
    cadence: str
    cuts_per_day: int
    value_date_field_hints: list[str] = field(default_factory=list)
    external_source_hint: str = ""
    internal_source_hint: str = ""


@dataclass(slots=True)
class Client:
    client_id: str
    client_name: str
    calendar: str
    late_window_days: int
    accounts: list[Account]
    filename_hints: list[FilenameHint]
    expectations: list[Expectation]
    field_overrides: dict[str, str]

    def expectation_for(self, domain: str) -> Expectation | None:
        return next((e for e in self.expectations if e.domain == domain), None)

    def account(self, account_id: str) -> Account | None:
        return next((a for a in self.accounts if a.id == account_id), None)

    def value_date_hints(self) -> list[str]:
        """Every value-date column name this client is known to use."""
        seen: list[str] = []
        for e in self.expectations:
            for hint in e.value_date_field_hints:
                if hint not in seen:
                    seen.append(hint)
        return seen


@dataclass(slots=True)
class Calendar:
    calendar_id: str
    weekend: set[int]
    holidays: dict[date, str]

    def is_business_day(self, d: date) -> bool:
        return d.weekday() not in self.weekend and d not in self.holidays

    def holiday_name(self, d: date) -> str:
        return self.holidays.get(d, "")

    def previous_business_day(self, d: date) -> date:
        for _ in range(MAX_CALENDAR_STEP_DAYS):
            d -= timedelta(days=1)
            if self.is_business_day(d):
                return d
        return d

    def next_business_day(self, d: date) -> date:
        for _ in range(MAX_CALENDAR_STEP_DAYS):
            d += timedelta(days=1)
            if self.is_business_day(d):
                return d
        return d

    def add_business_days(self, d: date, n: int) -> date:
        if n == 0:
            return d
        step = self.next_business_day if n > 0 else self.previous_business_day
        for _ in range(abs(n)):
            d = step(d)
        return d

    def roll(self, d: date, convention: str = "PRECEDING") -> date:
        """Move a non-business day onto an adjacent business day.

        A resolved value date must always be a day the market was open. If a
        file's contents claim a Saturday, something upstream is wrong and the
        date needs adjusting rather than being passed through to a
        reconciliation that will never find a counterpart.
        """
        if self.is_business_day(d):
            return d
        return (
            self.previous_business_day(d)
            if convention == "PRECEDING"
            else self.next_business_day(d)
        )


class Registry:
    """Loaded clients and calendars."""

    def __init__(self, clients: dict[str, Client], calendars: dict[str, Calendar]) -> None:
        self._clients = clients
        self._calendars = calendars

    @property
    def clients(self) -> list[Client]:
        return [self._clients[k] for k in sorted(self._clients)]

    def client(self, client_id: str) -> Client | None:
        return self._clients.get(client_id)

    def calendar(self, calendar_id: str) -> Calendar | None:
        return self._calendars.get(calendar_id)

    def calendar_for(self, client_id: str) -> Calendar | None:
        c = self._clients.get(client_id)
        return self._calendars.get(c.calendar) if c else None

    def account_owner(self, account_id: str) -> tuple[Client, Account] | None:
        """Find which client owns an account id.

        This is how a file with an unhelpful filename still gets attributed:
        the account numbers in its contents are unambiguous even when the name
        on the file is not.
        """
        for c in self.clients:
            a = c.account(account_id)
            if a:
                return c, a
        return None

    def all_account_ids(self) -> dict[str, str]:
        """account id -> client id, across every client."""
        return {a.id: c.client_id for c in self.clients for a in c.accounts}


def load(config_dir: str | Path) -> Registry:
    """Load every client and calendar under ``config_dir``."""
    root = Path(config_dir)
    calendars = {c.calendar_id: c for c in _load_calendars(root / "calendars")}
    clients = {c.client_id: c for c in _load_clients(root / "clients")}
    if not clients:
        raise ConfigError(f"no client configuration found under {root}")
    for c in clients.values():
        if c.calendar not in calendars:
            raise ConfigError(f"client {c.client_id} references unknown calendar {c.calendar!r}")
    return Registry(clients, calendars)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: expected a mapping at the top level")
    return data


def _load_calendars(directory: Path) -> list[Calendar]:
    out: list[Calendar] = []
    for path in sorted(directory.glob("*.yaml")):
        data = _read_yaml(path)
        weekend: set[int] = set()
        for name in data.get("weekend", []):
            key = str(name).strip().upper()
            if key not in _WEEKDAYS:
                raise ConfigError(f"{path.name}: unknown weekend day {name!r}")
            weekend.add(_WEEKDAYS[key])
        holidays: dict[date, str] = {}
        for h in data.get("holidays") or []:
            try:
                holidays[date.fromisoformat(str(h["date"]))] = str(h.get("name", ""))
            except (KeyError, ValueError) as exc:
                raise ConfigError(f"{path.name}: bad holiday entry {h!r}") from exc
        out.append(
            Calendar(calendar_id=str(data["calendar_id"]), weekend=weekend, holidays=holidays)
        )
    return out


def _load_clients(directory: Path) -> list[Client]:
    out: list[Client] = []
    for path in sorted(directory.glob("*.yaml")):
        data = _read_yaml(path)
        try:
            hints = [
                FilenameHint(
                    pattern=re.compile(str(h["pattern"])),
                    domain_map={str(k): str(v) for k, v in (h.get("domain_map") or {}).items()},
                    domain=str(h.get("domain", "")),
                    source_hint=str(h.get("source_hint", "")),
                )
                for h in data.get("filename_hints") or []
            ]
        except re.error as exc:
            raise ConfigError(f"{path.name}: invalid filename_hints pattern: {exc}") from exc

        expectations = []
        for e in data.get("expectations") or []:
            sides = e.get("sides") or {}
            expectations.append(
                Expectation(
                    id=str(e["id"]),
                    domain=str(e["domain"]),
                    cadence=str(e.get("cadence", "DAILY")),
                    cuts_per_day=int(e.get("cuts_per_day", 1)),
                    value_date_field_hints=[str(v) for v in e.get("value_date_field_hints") or []],
                    external_source_hint=str(
                        (sides.get("external_client") or {}).get("source_hint", "")
                    ),
                    internal_source_hint=str(
                        (sides.get("internal_gl") or {}).get("source_hint", "")
                    ),
                )
            )

        out.append(
            Client(
                client_id=str(data["client_id"]),
                client_name=str(data.get("client_name", "")),
                calendar=str(data["calendar"]),
                late_window_days=int(data.get("late_window_days", 2)),
                accounts=[
                    Account(
                        id=str(a["id"]),
                        name=str(a.get("name", "")),
                        venues=[str(v) for v in a.get("venues") or []],
                    )
                    for a in data.get("accounts") or []
                ],
                filename_hints=hints,
                expectations=expectations,
                field_overrides={
                    str(k): str(v) for k, v in (data.get("field_overrides") or {}).items()
                },
            )
        )
    return out
