# STATE — Harbormaster

**Phase:** 4 — Guardrails
**Status:** `make check` green; W1-W3 partially complete
**Updated:** 2026-08-30

## Now / next

- **Now:** Guardrails gate passing. T-001, T-002, T-003, T-004, T-006, T-009 done
  and validated here. Contracts frozen and proven across Go and Python.
- **Next:** T-005 (Compose), T-007 (migrations), T-008 (bus + structured logging)
  to close W1-W3, then M0 walking skeleton (W4-W5).

## Decisions taken at intake

| # | Decision |
|---|---|
| D-01 | Project name: Harbormaster. |
| D-02 | Production-shaped prototype, enterprise-grade design; not a deployed system. |
| D-03 | Scale envelope: 1,000 arrivals/day, continuous, no batch window. |
| D-04 | Formats: CSV, Excel, XML, FIXML, email text, JSON-on-queue. PDF excluded. |
| D-05 | Real Anthropic API for the model tier, exercised last, behind an interface. |
| D-06 | Docker-based local demo. |
| D-07 | Audit log, identifier masking, four-eyes review queue all in scope. |
| D-08 | Per-client YAML configuration. |
| D-09 | Reconciliation engine fully stubbed. |
| D-10 | Polyglot permitted; Go where it fits. Stack decided in Phase 1. |
| D-11 | Web UI in scope, read-only observability plus review actions. |
| D-12 | No hard deadline. Token discipline per skill applies. |

## Task log

| Date | Task | Result |
|---|---|---|
| 2026-08-30 | Phase 0 intake | Requirements drafted, STATE created |
| 2026-08-30 | Phase 0 gate | Approved; ADR-010, ADR-011 recorded |
| 2026-08-30 | Phase 1 HLD | Architecture + stack recommended; ADR-001..009 |
| 2026-08-30 | Phase 2 LLD | Contracts, schemas, error taxonomy, test strategy |
| 2026-08-30 | Phase 1/2 gate | Approved; ADR-012..015 recorded, HLD/LLD amended |
| 2026-08-30 | Phase 3 plan | 9 milestones, 50 tasks, 16 waves, packs generated |
| 2026-08-30 | Phase 3 gate | Approved. T-043 pulled forward to W6; T-028/T-043 left unsplit |
| 2026-08-31 | Toolchain audit | Go/protoc/buf/Postgres/golangci-lint installed; Docker unavailable |
| 2026-08-31 | ADR-016..019 | Polling watcher, Bus seam, split validation, Go dep policy |
| 2026-08-31 | T-001/002/003 | Scaffold, Go module, Python project — all lint/type clean |
| 2026-08-31 | T-004 | Proto frozen, codegen committed, cross-language round-trip green |
| 2026-08-31 | T-009 | Masking hook + 6 cases; short-identifier leak case covered |
| 2026-08-31 | T-006 | `make check` green offline; CI runs the same target verbatim |

## Blockers

- **B-01 Docker unavailable in the build environment.** Resolved by ADR-018:
  validation is split, and each task pack now carries `validated-here` or
  `validate-on-host`.
- **B-02 `go.sum` cannot be generated here.** `google.golang.org/protobuf` is
  blocked by egress policy, so `go mod tidy` fails and no `go.sum` is committed.
  First run on a normal machine must be `cd go && go mod tidy`. CI does this
  explicitly. Not a code defect; noted so it is not mistaken for one.

## Deviations

- Skill `references/*.md` not present in the installed skill; standard document
  structure used instead. See ADR-009.
- Go 1.22.2 (Ubuntu archive) rather than the 1.23 named in the HLD. No functional
  impact; go.mod targets 1.22.
- Egress policy blocks `golang.org/*`, `google.golang.org/*` and `gopkg.in/*`.
  Dependency set restricted to github.com-hosted modules; `fsnotify` therefore
  unavailable. Generated protobuf Go compiles via a gitignored `go.work` override.
