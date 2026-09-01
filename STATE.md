# STATE — Harbormaster

**Phase:** 9 — Ship readiness
**Status:** complete; awaiting host validation of the two Docker-dependent gates
**Updated:** 2026-09-01

## Now / next

- **Now:** All 50 tasks done. 379 tests passing. `make check` green offline in
  ~40s. Ship report at `docs/ship-report.md`.
- **Next (on a machine with Docker):**
  1. `cd go && go mod tidy`
  2. `make up && make test-e2e`
  3. `HM_LIVE=1 make test-live`

## Milestones

| ID | Milestone | Status |
|---|---|---|
| G | Guardrails | Done |
| M0 | Walking skeleton | Done |
| M1 | Ingestion hardening | Done |
| M2 | Parser breadth | Done |
| M3 | Intelligence | Done |
| M4 | Slot lifecycle | Done |
| M5 | Audit and review | Done |
| M6 | Interface | Done |
| M7 | Reference corpus | Done |
| M8 | Live model tier | Done (live call is host-validated) |
| M9 | Ship readiness | Done |

## Decisions

20 ADRs in `docs/design/decisions.md`, ADR-001 through ADR-020.

## Task log

| Date | Task | Result |
|---|---|---|
| 2026-08-30 | Phase 0–3 | Requirements, HLD, LLD, execution plan; all gates approved |
| 2026-08-31 | Guardrails | `make check` green on an empty repo; CI runs the same target |
| 2026-08-31 | M0 | Portwatch, Inspector, Berthmaster, recon stub end to end |
| 2026-08-31 | M1–M4 | Ingestion hardening, six parsers, three-tier mapping, slot lifecycle |
| 2026-09-01 | M5–M6 | Control plane, review queue, operations console |
| 2026-09-01 | M7–M9 | Corpus, scenario suite, live model tier, docs, ship report |

## Blockers

None. Two gates are host-dependent by design (ADR-018) and are marked
`validate-on-host` in their task packs.

## Deviations

- Skill `references/*.md` not present in the installed skill; standard document
  structure used instead. See ADR-009.
- Go 1.22.2 rather than the 1.23 named in the HLD. No functional impact.
- Egress policy blocked `golang.org/*`, `google.golang.org/*` and `gopkg.in/*`,
  restricting Go dependencies to github.com-hosted modules. This produced a
  smaller dependency tree than planned and two better decisions: polling rather
  than inotify (ADR-016) and topic provisioning in infrastructure rather than
  the application (ADR-020).
- `go.sum` not committed; `go mod tidy` must run once on first checkout.
