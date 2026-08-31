"""Bus semantics that the rest of the system depends on."""

from __future__ import annotations

import pytest

from harbormaster.v1 import harbormaster_pb2 as hm
from inspector import bus


def test_slot_key_format_matches_go() -> None:
    # Must be byte-identical to bus.SlotKey in Go, or a slot silently splits
    # across partitions and supersession ordering breaks (ADR-005).
    assert bus.slot_key("CLNT004", "TRADE", "2026-08-28") == "CLNT004:TRADE:2026-08-28"


def test_per_key_ordering_preserved() -> None:
    b = bus.MemoryBus(partitions=8)
    key = bus.slot_key("CLNT004", "TRADE", "2026-08-28")
    for i in range(200):
        b.publish(bus.Message(topic=bus.TOPIC_BERTH_ASSIGNED, key=key, value=str(i).encode()))
    got = [m.value.decode() for m in b.messages(bus.TOPIC_BERTH_ASSIGNED)]
    assert got == [str(i) for i in range(200)]


def test_same_key_always_same_partition() -> None:
    b = bus.MemoryBus(partitions=8)
    key = bus.slot_key("CLNT004", "TRADE", "2026-08-28")
    assert len({b.partition_for(key) for _ in range(100)}) == 1


def test_keys_spread_across_partitions() -> None:
    # A fake that collapsed everything into one partition would hide ordering
    # bugs a real broker would expose.
    b = bus.MemoryBus(partitions=8)
    seen = {b.partition_for(bus.slot_key("C", "TRADE", f"2026-01-{d:02d}")) for d in range(1, 29)}
    assert len(seen) > 1


def test_encode_decode_round_trip() -> None:
    msg = hm.BerthAssigned(
        assignment_id="asg-1",
        client_id="CLNT004",
        value_date="2026-08-28",
        domain=hm.PRODUCT_DOMAIN_TRADE,
        confidence=0.93,
    )
    out = bus.decode(bus.encode(msg), hm.BerthAssigned())
    assert out.assignment_id == "asg-1"
    assert out.value_date == "2026-08-28"
    assert out.domain == hm.PRODUCT_DOMAIN_TRADE


def test_decode_tolerates_unknown_fields() -> None:
    out = bus.decode(b'{"assignmentId":"a","brandNewField":42}', hm.BerthAssigned())
    assert out.assignment_id == "a"


def test_consume_delivers_history() -> None:
    b = bus.MemoryBus(partitions=4)
    b.publish(bus.Message(topic=bus.TOPIC_ARRIVALS_RAW, key="k", value=b"early"))
    seen: list[str] = []
    b.consume("g", [bus.TOPIC_ARRIVALS_RAW], lambda m: seen.append(m.value.decode()))
    assert seen == ["early"]


def test_publish_after_close_raises() -> None:
    b = bus.MemoryBus()
    b.close()
    with pytest.raises(RuntimeError):
        b.publish(bus.Message(topic=bus.TOPIC_ARRIVALS_RAW, key="k", value=b"x"))
