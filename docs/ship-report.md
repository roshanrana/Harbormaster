# Ship Report

**Project:** Harbormaster
**Date:** 2026-09-01
**Scope:** production-shaped prototype, per `01-requirements.md`

---

## 1. What was built

Everything between a file landing and a reconciliation instruction being issued.
Six services over a Kafka-compatible log, a polyglot Go and Python split, an
operations console, a deterministic reference corpus, and a live model tier
behind an interface.

| Measure | Count |
|---|---|
| Go source | 4,991 lines across 12 packages and 3 binaries |
| Python source | 6,295 lines |
| Go tests | 111 passing, 2,612 lines |
| Python tests | 268 passing, 3,275 lines |
| Documentation | 2,877 lines |
| Configuration and contracts | 476 lines |
| Architecture decisions | 20, each with context, consequences and costs |
| Task packs | 50, each with scope, acceptance criteria and a validation command |

**379 tests pass.** `make check` completes offline in roughly 40 seconds with no
broker, no database, no network and no API key.

## 2. Gate results

| Gate | Command | Result |
|---|---|---|
| Format | `gofmt`, `ruff format` | Pass |
| Lint | `go vet`, `golangci-lint`, `ruff` | Pass |
| Type check | `mypy --strict` | Pass, 32 source files |
| Contracts | `buf lint`, codegen staleness | Pass |
| Cross-language contract | Go marshals, Python asserts | Pass |
| Unit and property | `go test`, `pytest` | Pass, 379 tests |
| Scenario | `make test-scenarios` | Pass, 17 tests over 12 fixtures |
| Database integration | Real Postgres 16 | Pass, 40 tests |
| CI | GitHub Actions runs `make check` verbatim | Configured |
| End to end | `make up && make test-e2e` | **Written, not executed here** (see §5) |
| Live model | `HM_LIVE=1 make test-live` | **Written, not executed here** (see §5) |

## 3. Measured correctness

Against the committed reference corpus, not against hopeful assertions.

| Target | Requirement | Measured |
|---|---|---|
| Client attribution | NFR-4, ≥ 99% | 100% of attributable fixtures |
| Value date correct | NFR-5, ≥ 98% | 100%; every resolved date is a business day on the client's calendar |
| Date disagreements flagged | NFR-5, 100% | 100%, asserted per fixture |
| Mapping provenance | NFR-6, 100% | Every dispatched mapping carries a tier and non-empty evidence |
| Quarantine rate | NFR-7, ≤ 5% | 0% of well-formed fixtures; only the deliberately unattributable file is held |
| Model escalation | NFR-8, ≤ 2% once warm | Second file with a known layout costs zero adjudications, asserted |
| Idempotency | NFR-9 | Reprocessing the same content produces no additional instruction, asserted in both languages |

The twelve adversarial cases each have a named test. A regression fails with a
name that says what broke, rather than as fixture number seven.

## 4. Notable defects found and fixed during construction

Listed because they are the useful part of a build record.

| Defect | Consequence had it shipped |
|---|---|
| Audit hashes recomputed differently on read | Every chain would fail verification the moment it was read. Postgres stores microseconds; Go timestamps carry nanoseconds. |
| `inputs`/`outcome` stored as `JSONB` | JSONB normalises key order, so hashed bytes would not match stored bytes. Changed to `TEXT`. |
| Delimiter scorer compared score against a stored agreement value | A description column full of commas beat the real pipe delimiter. |
| Header detection resolved a width tie toward the narrow row | A title banner was selected as the header row. |
| `bv or ""` in the recon stub | `Decimal("0")` is falsy, making a genuine zero indistinguishable from a null. |
| Masking revealed short account numbers in full | "Last four" of a four-character value is all of it. |
| Rollback test assumed a single migration | Silently passed until a second migration existed. |
| `bare_price_header` fixture emitted a third price column | The case stopped testing the structural path it existed to test. |

## 5. Known limitations

Stated plainly rather than omitted.

1. **End-to-end and live-model tests are written but were not executed in the
   build environment.** Docker is unavailable there (ADR-018), so Compose,
   Redpanda and any full-stack run were authored to spec and must be validated
   on a machine with Docker: `make up && make test-e2e`. Every task pack is
   marked `validated-here` or `validate-on-host`; nothing is marked done on
   unexecuted code.
2. **A developer-local `go.work` can shadow the module.** The repository ignores
   `go/go.work` so container-only replacements never ship. The Makefile runs Go
   gates with `GOWORK=off`, which keeps normal checkouts on the committed
   `go.mod` and `go.sum`.
3. **Tier 2 embeddings are optional and untested against a real model.**
   `fastembed` is an optional dependency; the degraded fuzzy-only path is what
   the suite exercises. The degradation is recorded in the evidence string
   rather than being silent, but the semantic path itself has not run here.
4. **Excel parsing handles the quirks in the corpus, not all quirks.** Merged
   headers, cover sheets, banners and totals rows are covered. Pivot tables,
   formulas returning errors, and multi-row headers are not.
5. **The email parser is deliberately conservative** and will decline lines a
   human would read easily. That is the intended trade, but it means free-text
   advices will generate review work.
6. **Berthmaster's overdue sweep is not leader-elected.** Running more than one
   instance would run the sweep more than once per interval. Slot state itself
   is safe across instances.
7. **No authentication on the console.** Out of scope by requirements section 7;
   it would sit behind the institution's existing SSO.
8. **Throughput is designed for, not load-tested.** The 1,000 arrivals/day
   envelope and the p95 latency target in NFR-2 have no measurement behind them.

## 6. Rollback posture

Migrations are reversible and the loader refuses to start if any migration is
missing its down half. Read models are projections and can be rebuilt by
replaying topics from offset zero. The event log is authoritative, so a bad
deployment is recovered by reverting the binary and replaying, not by repairing
rows.

## 7. Go / no-go

Every gate that can be executed in this environment passes. The two that cannot
are written and marked as such.

**Recommendation:** ready to run on a machine with Docker. Before calling it
done, run these three and confirm:

```bash
cd go && go mod tidy
make up && make test-e2e
HM_LIVE=1 make test-live
```

That is a decision for the reader, not an assertion by the builder.
