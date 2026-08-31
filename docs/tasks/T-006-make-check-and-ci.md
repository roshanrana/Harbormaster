# T-006 — make check and CI

**Milestone:** G  **Depends on:** T-002..T-005  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `Makefile, .github/`

## Objective
Aggregate every static and test gate behind one command, and run the identical command in GitHub Actions.

## Acceptance criteria
- [x] `make check` runs fmt, lint, type check, buf lint, codegen freshness, all unit tests
- [x] Runs fully offline with no network and no API key
- [x] CI workflow invokes `make check` verbatim, not a reimplementation

## Validation
```
make check
```

## Reference
03-lld.md §9 — read only what the criteria above require.

## Handoff notes
`make check` runs fmt, lint, typecheck, buf lint, codegen staleness and all tests. Green, offline, no API key. CI invokes `make check` verbatim.
