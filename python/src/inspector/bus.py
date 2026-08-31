"""Messaging seam for the Python services.

Mirrors ``go/internal/bus`` deliberately: same topic constants, same protojson
codec, same at-least-once semantics with the offset committed only after a
handler succeeds. Two implementations sit behind one Protocol so the Inspector's
logic is testable without a broker (ADR-017).

The wire format is protojson (ADR-003), which is why encode/decode here can be
thin: the contract lives in ``proto/``, not in this file.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Protocol

from google.protobuf import json_format
from google.protobuf.message import Message as ProtoMessage

# --- topics ----------------------------------------------------------------
# Same names as go/internal/bus/bus.go. Duplicated rather than generated
# because two constants that must agree is a smaller risk than a codegen step
# that exists to produce eight strings.

TOPIC_ARRIVALS_RAW = "hm.arrivals.raw"
TOPIC_ARRIVALS_CLASSIFIED = "hm.arrivals.classified"
TOPIC_ARRIVALS_QUARANTINE = "hm.arrivals.quarantined"
TOPIC_REVIEW_DECISIONS = "hm.review.decisions"
TOPIC_BERTH_ASSIGNED = "hm.berth.assigned"
TOPIC_BERTH_SUPERSEDED = "hm.berth.superseded"
TOPIC_ALERTS_MISSING = "hm.alerts.missing"
TOPIC_AUDIT_DECISIONS = "hm.audit.decisions"

ALL_TOPICS = (
    TOPIC_ARRIVALS_RAW,
    TOPIC_ARRIVALS_CLASSIFIED,
    TOPIC_ARRIVALS_QUARANTINE,
    TOPIC_REVIEW_DECISIONS,
    TOPIC_BERTH_ASSIGNED,
    TOPIC_BERTH_SUPERSEDED,
    TOPIC_ALERTS_MISSING,
    TOPIC_AUDIT_DECISIONS,
)


def slot_key(client_id: str, domain: str, value_date: str) -> str:
    """Partition key that guarantees ordering within one reconciliation slot.

    Must match ``bus.SlotKey`` in Go exactly; a divergence would silently split
    a slot across partitions and break supersession ordering (ADR-005).
    """
    return f"{client_id}:{domain}:{value_date}"


@dataclass(slots=True)
class Message:
    topic: str
    key: str
    value: bytes
    headers: dict[str, str] = field(default_factory=dict)
    partition: int = 0
    offset: int = 0


Handler = Callable[[Message], None]


def encode(msg: ProtoMessage) -> bytes:
    """Serialise a proto message to the wire format."""
    out: str = json_format.MessageToJson(msg, indent=0)
    return out.encode()


def decode[M: ProtoMessage](raw: bytes, msg: M) -> M:
    """Parse a wire payload into ``msg`` and return it.

    ``ignore_unknown_fields`` lets a consumer built against an older contract
    keep working when a producer adds a field, which is what makes additive
    contract changes deployable without lockstep releases.
    """
    json_format.Parse(raw.decode(), msg, ignore_unknown_fields=True)
    return msg


class Bus(Protocol):
    """Publish and subscribe."""

    def publish(self, *messages: Message) -> None: ...

    def consume(self, group: str, topics: Iterable[str], handler: Handler) -> None: ...

    def close(self) -> None: ...


class MemoryBus:
    """In-process bus for unit tests.

    Models per-key partition ordering the same way the Go fake does, and for
    the same reason: a fake that is globally ordered would let a real ordering
    bug pass the suite.
    """

    def __init__(self, partitions: int = 8) -> None:
        self._partitions = max(1, partitions)
        self._log: dict[str, dict[int, list[Message]]] = defaultdict(lambda: defaultdict(list))
        self._closed = False

    def partition_for(self, key: str) -> int:
        if not key:
            return 0
        digest = hashlib.blake2b(key.encode(), digest_size=4).digest()
        return int.from_bytes(digest, "big") % self._partitions

    def publish(self, *messages: Message) -> None:
        if self._closed:
            raise RuntimeError("bus: closed")
        for m in messages:
            p = self.partition_for(m.key)
            m.partition = p
            m.offset = len(self._log[m.topic][p])
            self._log[m.topic][p].append(m)

    def consume(self, group: str, topics: Iterable[str], handler: Handler) -> None:
        """Replay everything currently logged for the given topics.

        Synchronous and finite by design: tests want to publish, consume, and
        assert, not manage a background loop.
        """
        del group
        for m in self._drain(topics):
            handler(m)

    def _drain(self, topics: Iterable[str]) -> Iterator[Message]:
        for topic in topics:
            for p in range(self._partitions):
                yield from self._log[topic][p]

    def messages(self, topic: str) -> list[Message]:
        """Everything published to a topic, in partition then offset order."""
        out: list[Message] = []
        for p in range(self._partitions):
            out.extend(self._log[topic][p])
        return out

    def close(self) -> None:
        self._closed = True
