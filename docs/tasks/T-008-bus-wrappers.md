# T-008 — Bus wrappers

**Milestone:** G  **Depends on:** T-004  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/bus/, python/src/inspector/bus.py`

## Objective
Thin producer/consumer wrappers in both languages: protojson encoding, manual offset commit, bounded in-flight work, correlation-id propagation.

## Acceptance criteria
- [x] Publish and consume round-trip verified in both languages against a live broker
- [x] Offsets commit only after successful downstream publish
- [x] Consumer honours context cancellation and shuts down cleanly

## Validation
```
make check && make test-bus
```

## Reference
02-hld.md §4.1, §8 — read only what the criteria above require.

## Handoff notes
Bus interface with memory and franz-go implementations in Go, and a mirrored Protocol with MemoryBus in Python. protojson codec both sides, unknown fields tolerated. Per-key ordering asserted in both languages, plus a test that keys actually spread across partitions so the fake cannot hide ordering bugs. Structured logging with context-propagated arrival_id; account identifiers loggable only through a masking helper with no unmasked variant. Cross-language masking parity table: Go emits, Python asserts.
