# T-008 — Bus wrappers

**Milestone:** G  **Depends on:** T-004  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/bus/, python/src/inspector/bus.py`

## Objective
Thin producer/consumer wrappers in both languages: protojson encoding, manual offset commit, bounded in-flight work, correlation-id propagation.

## Acceptance criteria
- [ ] Publish and consume round-trip verified in both languages against a live broker
- [ ] Offsets commit only after successful downstream publish
- [ ] Consumer honours context cancellation and shuts down cleanly

## Validation
```
make check && make test-bus
```

## Reference
02-hld.md §4.1, §8 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
