# STATE — Harbormaster

**Phase:** 5 — Build
**Status:** M3 complete; 235 Python tests + 10 Go packages green
**Updated:** 2026-08-30

## Now / next

- **Now:** Full three-tier mapping ladder live and wired into the Inspector.
  Escalation is one-way; the template cache means a repeated layout costs nothing.
- **Next:** T-039 control plane read models and API, T-038 review queue, then
  the UI (T-040/041/042) and the scenario suite (T-045).

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
| 2026-08-31 | T-008 | Bus seam both languages; per-key ordering + masking parity proven |
| 2026-08-31 | T-007 | Migrations + rollback, 6 tests green against real Postgres |
| 2026-08-31 | T-005 | Compose + Dockerfiles authored; ADR-020 moves topics to infra |
| 2026-08-31 | T-018 | ObjectStore + fs adapter; traversal rejected, partial writes invisible |
| 2026-08-31 | T-010/015/016 | Polling scanner, quiet window, dedupe verdicts, Portwatch binary |
| 2026-08-31 | T-037 | Hash-chained audit; tamper and deletion both detected |
| 2026-08-31 | T-028 | Canonical schema + 200-entry alias dictionary across 8 venues |
| 2026-08-31 | T-031 | Price disambiguation: vocabulary, preference, structure, arithmetic |
| 2026-08-31 | T-025 | Registry: 6 clients, 4 calendars, strict validation, business-day maths |
| 2026-08-31 | T-012/033/034/035 | Slot machine, late window, supersession, missing alerts, Berthmaster |
| 2026-08-31 | T-013 | Recon stub with break report; null never treated as zero |
| 2026-08-31 | T-027 | Value-date resolver: 3 sources, content precedence, business-day rolling |
| 2026-08-31 | T-026 | Attribution: agreement raises confidence, conflict quarantines |
| 2026-08-31 | T-032 | Weighted confidence, per-domain required fields, specific reasons |
| 2026-08-31 | T-011/024/036 | Inspector pipeline, content sniffing, multi-date splitting |
| 2026-08-31 | T-043/044 | Corpus generator, 8 venue vocabularies, 12 adversarial fixtures |
| 2026-08-31 | T-019..T-023 | Excel, XML, FIXML, JSON and email parsers; all six formats live |
| 2026-08-31 | T-029/030 | Tier 2 fuzzy+embedding, Tier 3 seam, durable template cache |

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
