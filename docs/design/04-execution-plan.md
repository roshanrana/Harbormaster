# Harbormaster — Execution Plan

**Status:** Phase 3 draft, awaiting the hard gate
**Last updated:** 2026-08-30
**Upstream:** `01-requirements.md`, `02-hld.md`, `03-lld.md`, `decisions.md`

---

## 1. Milestones

| ID | Milestone | Exit criteria |
|---|---|---|
| **G** | Guardrails | `make check` exists and passes on an empty repo: format, lint, type check, buf lint + codegen freshness, test harness, CI green |
| **M0** | Walking skeleton | One CSV lands in the landing directory and produces a berth assignment consumed by the recon stub, through the real Compose stack, real broker and real generated proto types |
| **M1** | Ingestion hardening | Stability detection, dedupe with suppression audit, JSON queue ingress, restart safety, object store abstraction |
| **M2** | Parser breadth | All six formats parse to a common `ParsedTable`, format decided by content not extension |
| **M3** | Intelligence | Client attribution, value-date resolution, three-tier mapping, price disambiguation, confidence and disposition routing |
| **M4** | Slot lifecycle | T±2 late window, supersession with ordered void/replacement, missing-file alerts, multi-date split |
| **M5** | Audit and review | Hash-chained audit with a verifier, four-eyes review queue, control plane read models and API |
| **M6** | Interface | Arrival board, arrival detail with per-field provenance, quarantine review, slot board |
| **M7** | Reference corpus | Corpus generator plus the twelve adversarial fixtures; golden and scenario tests green |
| **M8** | Live model tier | `ClaudeAdjudicator` behind the frozen interface, exercised against the real API |
| **M9** | Ship readiness | README, architecture narrative, runbook, demo walkthrough, ship report |

M0 is the walking skeleton: the thinnest possible slice that touches every piece of
the real architecture. Everything after it is thickening, not re-plumbing.

## 2. Task table

Scope column names the directories a task may touch. A task that needs to reach
outside its scope stops and amends the plan.

| ID | Task | Milestone | Depends on | Scope |
|---|---|---|---|---|
| T-001 | Repo scaffold, Makefile skeleton, .gitignore, directory tree | G | — | root |
| T-002 | Go module, golangci-lint, vet, test harness | G | T-001 | `go/` |
| T-003 | Python project via uv, ruff, mypy, pytest | G | T-001 | `python/` |
| T-004 | Protobuf contracts, buf config, Go + Python codegen, freshness check | G | T-002, T-003 | `proto/`, `buf.*`, `go/gen/`, `python/src/hmv1/` |
| T-005 | Compose core profile: redpanda, postgres, six services, healthchecks | G | T-001 | `docker-compose.yml`, `*/Dockerfile` |
| T-006 | `make check` aggregator and GitHub Actions running the same command | G | T-002..T-005 | `Makefile`, `.github/` |
| T-007 | Postgres migrations for LLD §6 schema | G | T-005 | `go/internal/store/migrations/` |
| T-008 | Bus wrappers: Go producer/consumer, Python producer/consumer | G | T-004 | `go/internal/bus/`, `python/src/inspector/bus.py` |
| T-009 | Structured logging and the masking serialisation hook, both languages | G | T-002, T-003 | `go/internal/masking/`, `go/internal/logging/`, `python/src/inspector/logging.py` |
| T-010 | Portwatch minimal: watch, hash, publish `arrivals.raw` | M0 | T-008 | `go/cmd/portwatch/`, `go/internal/ingress/` |
| T-011 | Inspector minimal: CSV sniff, parse, alias mapping, Parquet, publish | M0 | T-008 | `python/src/inspector/` |
| T-012 | Berthmaster minimal: slot open → partial → assigned | M0 | T-007, T-008 | `go/cmd/berthmaster/`, `go/internal/slot/` |
| T-013 | Recon stub consuming `berth.assigned` | M0 | T-008 | `python/src/reconstub/` |
| T-014 | M0 end-to-end integration test through Compose | M0 | T-010..T-013 | `tests/integration/` |
| T-015 | Write-completion detection: quiet window, sentinel, restart rescan | M1 | T-010 | `go/internal/arrival/` |
| T-016 | Dedupe store, redelivery detection, suppression audit records | M1 | T-015, T-007 | `go/internal/arrival/`, `go/internal/store/` |
| T-017 | JSON queue ingress adapter | M1 | T-015 | `go/internal/ingress/` |
| T-018 | ObjectStore interface, fs adapter, s3 adapter (unwired) | M1 | T-002 | `go/internal/store/objectstore/` |
| T-019 | Excel parser: header detection, merged cells, totals rows | M2 | T-011 | `python/src/inspector/parsers/` |
| T-020 | XML parser with path flattening | M2 | T-011 | `python/src/inspector/parsers/` |
| T-021 | FIXML parser: tag mapping, repeating groups | M2 | T-020 | `python/src/inspector/parsers/` |
| T-022 | Email text parser: structure extraction from free prose | M2 | T-011 | `python/src/inspector/parsers/` |
| T-023 | JSON payload parser | M2 | T-011 | `python/src/inspector/parsers/` |
| T-024 | Content-based format sniffing across all six | M2 | T-019..T-023 | `python/src/inspector/sniff.py` |
| T-025 | Client registry: YAML load, schema validation, calendars | M3 | T-002 | `go/internal/registry/`, `config/` |
| T-026 | Client attribution with confidence | M3 | T-025 | `python/src/inspector/attribution.py` |
| T-027 | Value-date resolution engine and calendar rolling | M3 | T-025 | `python/src/inspector/valuedate.py` |
| T-028 | Canonical schema and the expanded Tier 1 alias dictionary | M3 | T-011 | `python/src/inspector/mapping/` |
| T-029 | Tier 2 local matching: rapidfuzz + fastembed, degraded mode | M3 | T-028 | `python/src/inspector/mapping/` |
| T-030 | Tier 3 seam: adjudicator interface, deterministic fake, template cache | M3 | T-029 | `python/src/inspector/mapping/` |
| T-031 | Price disambiguation, all four steps | M3 | T-028 | `python/src/inspector/mapping/prices.py` |
| T-032 | Confidence composition, thresholds, disposition routing | M3 | T-026, T-027, T-030, T-031 | `python/src/inspector/confidence.py` |
| T-033 | Full slot state machine with T±2 window and deadlines | M4 | T-012, T-025 | `go/internal/slot/` |
| T-034 | Supersession: ordered void then replacement | M4 | T-033 | `go/internal/slot/` |
| T-035 | Missing-file alerts on deadline expiry | M4 | T-033 | `go/internal/slot/` |
| T-036 | Multi-date split into sub-batches | M4 | T-027 | `python/src/inspector/` |
| T-037 | Hash-chained audit log and `make verify-audit` | M5 | T-007 | `go/internal/audit/` |
| T-038 | Review queue, decision endpoint, `review.decisions` consumer | M5 | T-037, T-033 | `go/internal/web/`, `go/internal/slot/` |
| T-039 | Read-model projector, REST API, SSE stream | M5 | T-037 | `go/cmd/controlplane/`, `go/internal/web/` |
| T-040 | UI shell, bespoke CSS, vendored HTMX, arrival board | M6 | T-039 | `go/web/` |
| T-041 | Arrival detail: per-field provenance and confidence breakdown | M6 | T-040 | `go/web/` |
| T-042 | Quarantine review screen and slot board | M6 | T-040, T-038 | `go/web/` |
| T-043 | Corpus generator: clients, calendars, venues, all six formats | M7 | T-024, T-025 | `corpus/`, `config/` |
| T-044 | The twelve adversarial fixtures from requirements §8 | M7 | T-043 | `corpus/` |
| T-045 | Golden tests and named scenario integration tests | M7 | T-044, T-032, T-034 | `tests/` |
| T-046 | `ClaudeAdjudicator`: structured output, prompt caching, retry, cost counter | M8 | T-030 | `python/src/inspector/mapping/tier3_llm.py` |
| T-047 | Live smoke test against the real API, opt-in via env | M8 | T-046, T-045 | `tests/live/` |
| T-048 | README, architecture narrative, runbook | M9 | T-045 | `docs/`, `README.md` |
| T-049 | `make demo`: seeded walkthrough with a narrated script | M9 | T-045, T-042 | `Makefile`, `scripts/`, `docs/` |
| T-050 | Ship report | M9 | T-047, T-048, T-049 | `docs/ship-report.md` |

## 3. Dependency graph

```
T-001 ─┬─ T-002 ─┬─ T-004 ─── T-008 ─┬─ T-010 ─ T-015 ─┬─ T-016
       ├─ T-003 ─┘                   ├─ T-011          ├─ T-017
       └─ T-005 ─── T-007            ├─ T-012          └─ T-018
                                     └─ T-013
       T-002/003 ─ T-009
       T-002..005 ─ T-006

  M0 gate: T-010..T-013 ──► T-014

  T-011 ─┬─ T-019 ─┐
         ├─ T-020 ─ T-021 ─┤
         ├─ T-022 ─────────┼─ T-024 ──┐
         ├─ T-023 ─────────┘          │
         └─ T-028 ─┬─ T-029 ─ T-030 ─┐│
                   └─ T-031 ─────────┤│
  T-025 ─┬─ T-026 ───────────────────┼┴─ T-032 ──┐
         ├─ T-027 ─── T-036          │           │
         └─ T-033 ─┬─ T-034 ─────────┼───────────┤
                   └─ T-035          │           │
  T-007 ─ T-037 ─┬─ T-038 ─┐         │           │
                 └─ T-039 ─ T-040 ─┬─ T-041      │
                                   └─ T-042      │
  T-024 + T-025 ─ T-043 ─ T-044 ─ T-045 ◄────────┘
  T-030 ─ T-046 ─ T-047 ─┐
  T-045 ─ T-048 ─────────┼─ T-050
  T-045 + T-042 ─ T-049 ─┘
```

## 4. Wave schedule

Tasks within a wave touch disjoint file scopes and can run in parallel.

| Wave | Tasks | Gate at end of wave |
|---|---|---|
| W1 | T-001, T-002, T-003, T-005 | Toolchains installed, containers build |
| W2 | T-004, T-007, T-009 | Codegen fresh, migrations apply, masking unit-tested |
| W3 | T-006, T-008 | **`make check` green on an empty repo** (Guardrails gate) |
| W4 | T-010, T-011, T-012, T-013 | Each service starts and round-trips its own contract |
| W5 | T-014 | **M0 walking skeleton runs end to end** |
| W6 | T-015, T-018, T-025 | Ingestion and registry foundations |
| W7 | T-016, T-017, T-019, T-020, T-022, T-023, T-028 | Parsers and dedupe |
| W8 | T-021, T-024, T-026, T-027, T-029, T-031, T-033 | Format decisions and resolution engines |
| W9 | T-030, T-032, T-034, T-035, T-036, T-037 | **M3 and M4 complete** |
| W10 | T-038, T-039 | Control plane serving read models |
| W11 | T-040, T-043 | Board renders, corpus generates |
| W12 | T-041, T-042, T-044 | **M6 interface complete** |
| W13 | T-045 | **M7: all twelve scenarios green** |
| W14 | T-046, T-048 | Model tier implemented, docs drafted |
| W15 | T-047, T-049 | **M8 live call verified, demo scripted** |
| W16 | T-050 | **Ship report; go/no-go** |

## 5. Validation gates

| Gate | Command | Blocks |
|---|---|---|
| Task | `make check` | marking any task done |
| Guardrails | `make check` on empty repo + CI green | W4 |
| M0 | `make up && make test-e2e` | W6 |
| M3/M4 | unit + property + golden suites green | W10 |
| M7 | all twelve named scenario tests green | W14 |
| Ship | `make check && make demo && make verify-audit` | release |

## 6. Two-strike policy

A task failing its validation twice is marked `blocked` in its pack, findings are
written into the pack, a line is appended to the `STATE.md` task log, and work
moves to the next unblocked task in the wave.

## 7. Deliberately out of the plan

Deployment manifests, Helm charts, autoscaling, SSO, secret management, load
testing, and any reconciliation matching logic. Listed here so their absence reads
as a decision rather than an omission.
