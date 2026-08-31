# T-009 — Structured logging and masking hook

**Milestone:** G  **Depends on:** T-002, T-003  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/masking/, go/internal/logging/, python/src/inspector/logging.py`

## Objective
JSON logging with correlation IDs in both languages, and a serialisation hook that masks account numbers to last-4 while leaving account names intact.

## Acceptance criteria
- [ ] Masking applied at serialisation, never at call sites
- [ ] Account name survives unmasked; account number renders as ****0119
- [ ] Property test: no log line in the suite contains a full account number
- [ ] HM_MASK_ACCOUNTS=false disables it for local debugging only

## Validation
```
make check
```

## Reference
ADR-011, 03-lld.md §10 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
