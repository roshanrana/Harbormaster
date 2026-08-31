# T-001 — Repo scaffold

**Milestone:** G  **Depends on:** -  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `root`

## Objective
Create the directory tree from LLD §1, a Makefile skeleton with empty targets, .gitignore, LICENSE and a placeholder README.

## Acceptance criteria
- [x] Tree matches LLD §1 exactly, including empty dirs with .gitkeep
- [x] `make` with no arguments prints the target list
- [x] No language toolchain files yet beyond placeholders

## Validation
```
make
```

## Reference
03-lld.md §1 — read only what the criteria above require.

## Handoff notes
Tree matches LLD section 1. `make` prints the target list.
