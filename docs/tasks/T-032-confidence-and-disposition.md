# T-032 — Confidence and disposition

**Milestone:** M3  **Depends on:** T-026, T-027, T-030, T-031  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/confidence.py`

## Objective
Weighted composition per LLD §5.6 and routing to dispatch, quarantine or reject.

## Acceptance criteria
- [x] Weights: material fields 3, identifiers 2, others 1
- [x] Thresholds 0.85 / 0.60 configurable by env
- [x] Disposition recorded on the classified message and in audit
- [x] Quarantine reasons are specific, never 'low confidence'

## Validation
```
make check
```

## Reference
03-lld.md §5.6, FR-29, FR-30 — read only what the criteria above require.

## Handoff notes
Weighted confidence composition with per-domain required fields. Unknown client or unmapped required field never dispatches regardless of composite score. Every quarantine reason names what was uncertain. 12 tests.
