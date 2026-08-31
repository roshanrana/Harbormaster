# T-009 — Structured logging and masking hook

**Milestone:** G  **Depends on:** T-002, T-003  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/masking/, go/internal/logging/, python/src/inspector/logging.py`

## Objective
JSON logging with correlation IDs in both languages, and a serialisation hook that masks account numbers to last-4 while leaving account names intact.

## Acceptance criteria
- [x] Masking applied at serialisation, never at call sites
- [x] Account name survives unmasked; account number renders as ****0119
- [x] Property test: no log line in the suite contains a full account number
- [x] HM_MASK_ACCOUNTS=false disables it for local debugging only

## Validation
```
make check
```

## Reference
ADR-011, 03-lld.md §10 — read only what the criteria above require.

## Handoff notes
Masking hook implemented with 6 table-driven cases. Short identifiers fully masked rather than revealed. Account names provably untouched. Structured logging deferred to T-008 where the bus wrapper needs it.
