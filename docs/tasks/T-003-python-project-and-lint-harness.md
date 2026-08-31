# T-003 — Python project and lint harness

**Milestone:** G  **Depends on:** T-001  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/`

## Objective
Initialise the Python project with uv, pyproject, ruff, mypy strict and pytest.

## Acceptance criteria
- [x] `uv sync` resolves offline from a committed lock
- [x] ruff and mypy pass on a stub module
- [x] One trivial parametrised pytest runs

## Validation
```
cd python && uv run ruff check . && uv run mypy src && uv run pytest
```

## Reference
03-lld.md §1 — read only what the criteria above require.

## Handoff notes
uv project synced, ruff + mypy strict + pytest green on 3 source files.
