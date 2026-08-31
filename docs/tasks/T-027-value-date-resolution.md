# T-027 — Value-date resolution

**Milestone:** M3  **Depends on:** T-025  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/valuedate.py`

## Objective
Three-source resolution with content precedence, calendar validation and mismatch flagging, per LLD §5.4.

## Acceptance criteria
- [ ] Content-explicit single value resolves at 0.97 confidence
- [ ] Filename/content disagreement always sets mismatch_flagged (FR-12)
- [ ] Resolved date is always a business day on the client calendar
- [ ] Property test: resolver never returns a weekend or holiday

## Validation
```
make check
```

## Reference
03-lld.md §5.4, FR-11..FR-14 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
