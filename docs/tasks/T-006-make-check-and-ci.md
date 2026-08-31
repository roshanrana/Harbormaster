# T-006 — make check and CI

**Milestone:** G  **Depends on:** T-002..T-005  **Status:** `pending`

## Scope
Only these paths may be touched: `Makefile, .github/`

## Objective
Aggregate every static and test gate behind one command, and run the identical command in GitHub Actions.

## Acceptance criteria
- [ ] `make check` runs fmt, lint, type check, buf lint, codegen freshness, all unit tests
- [ ] Runs fully offline with no network and no API key
- [ ] CI workflow invokes `make check` verbatim, not a reimplementation

## Validation
```
make check
```

## Reference
03-lld.md §9 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
