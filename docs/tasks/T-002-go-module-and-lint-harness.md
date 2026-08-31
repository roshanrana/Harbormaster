# T-002 — Go module and lint harness

**Milestone:** G  **Depends on:** T-001  **Status:** `pending`

## Scope
Only these paths may be touched: `go/`

## Objective
Initialise a single Go module with three cmd packages, wire golangci-lint, go vet and go test.

## Acceptance criteria
- [ ] `go build ./...` succeeds with stub mains
- [ ] golangci-lint config committed and passing
- [ ] One trivial table-driven test exists and runs

## Validation
```
cd go && go build ./... && go vet ./... && golangci-lint run && go test ./...
```

## Reference
03-lld.md §1 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
