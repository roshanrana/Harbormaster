# T-002 — Go module and lint harness

**Milestone:** G  **Depends on:** T-001  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/`

## Objective
Initialise a single Go module with three cmd packages, wire golangci-lint, go vet and go test.

## Acceptance criteria
- [x] `go build ./...` succeeds with stub mains
- [x] golangci-lint config committed and passing
- [x] One trivial table-driven test exists and runs

## Validation
```
cd go && go build ./... && go vet ./... && golangci-lint run && go test ./...
```

## Reference
03-lld.md §1 — read only what the criteria above require.

## Handoff notes
Go module `harbormaster.dev/hm`, golangci-lint v1.62.2, go vet and go test all clean.
