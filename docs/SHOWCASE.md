# Harbormaster — Showcase

A guided tour of the features, with the commands that exercise them and the files where each one lives. [OVERVIEW.md](OVERVIEW.md) has the why; this has the what.

## Ten minutes, no Docker

```bash
cd go && go mod tidy && cd ..
make check              # every static and unit gate, fully offline, ~40s
make test-scenarios     # the named adversarial cases
```

`make check` runs `gofmt`, `go vet`, `golangci-lint`, `ruff`, `mypy --strict`, `buf lint`, a codegen-staleness check, a cross-language contract test where Go marshals and Python asserts, and 379 unit and property tests. No broker, no database, no network, no API key.

`make test-scenarios` runs `tests/scenarios/test_adversarial_corpus.py`. Each test is named for what it is built to break, so a regression fails as `test_four_price_columns_resolve_correctly` rather than as fixture number seven.

## Thirty minutes, with Docker

```bash
make up          # the stack; the operations board is at http://localhost:8080
make demo        # drives the adversarial corpus through it, narrated
make verify-audit
make down
```

Watch the board while `make demo` runs. Files land, get attributed and dated, mappings resolve at Tier 1 or 2, the one unattributable file goes to quarantine, a correction supersedes an already-dispatched reconciliation, and every decision appends to a hash chain that `make verify-audit` walks end to end.

## Feature tour

### 1. Arrival detection and deduplication (`go/internal/arrival/`, `go/internal/ingress/`)

| Look at | What it shows |
|---|---|
| `scanner.go` | Write-completion detection: a file is not "arrived" until it has stopped growing |
| `dedupe.go` | Content hashing; an exact duplicate and a redelivery under a new name collide on hash, not on filename |
| `ingress/queue.go` | The parallel JSON ingress path, normalised into the same arrival contract as files |

**Why it matters:** the two most common causes of double-counted reconciliations are a resent file and a file renamed by an upstream job. Both are caught by content, not by name.

### 2. Parsers for what actually arrives (`python/src/inspector/parsers/`)

| Look at | What it shows |
|---|---|
| `delimited.py` | Delimiter scoring that survives a description column full of commas |
| `excel.py` | Cover sheets, banners, merged headers and totals rows; finds the data rather than trusting sheet zero, row zero |
| `fixml.py`, `xml_parser.py` | Structured venue formats |
| `email_text.py` | Free-text cash advices, deliberately conservative: it declines lines a human would read easily, and says so |

### 3. Value-date resolution (`python/src/inspector/valuedate.py`, `config/calendars/`)

Three independent sources (filename, content, arrival time), each ranked by how much it actually knows, resolved against per-client business calendars. Disagreement is always surfaced. The scenario `test_late_arrival_binds_to_its_historical_value_date` is the one to read.

### 4. Client attribution (`python/src/inspector/attribution.py`, `config/clients/`)

Filename patterns and embedded account identifiers are scored for agreement rather than followed as a priority list. The deliberately unattributable fixture is the only file the whole corpus quarantines: `test_unattributable_files_are_the_only_quarantines`.

### 5. The mapping ladder (`python/src/inspector/mapping/`)

| Look at | What it shows |
|---|---|
| `tier1.py` | The alias dictionary over normalised headers |
| `tier2.py` | Fuzzy matching plus optional local embeddings; degradation to fuzzy-only is recorded in the evidence string, never silent |
| `tier3.py`, `tier3_llm.py` | The model tier behind an interface, with a deterministic stand-in bound by default |
| `resolver.py` | One-way escalation, template-fingerprint caching, and promotion of confirmed mappings into client configuration |
| `canonical.py` | The single schema everything maps onto |

**Why it matters:** `test_price_disambiguation.py` and the scenario `test_bare_price_headers_resolve_structurally` show a column resolved by *structure* (settlement price repeats across rows for an instrument-day; trade price varies) when the header alone cannot separate them. That is the difference between a mapping tool and a mapping tool that understands the data.

### 6. Confidence and the decision to stop (`python/src/inspector/confidence.py`)

A composite confidence across attribution, date and mapping, with thresholds for dispatch, quarantine and reject, and a reason string that names what could not be decided.

### 7. Slots, lateness and supersession (`go/internal/slot/`)

The slot state machine: expected file on each side, a late window, missing-file alerts, and correction-after-dispatch handling. `test_correction_differs_in_content_but_targets_the_same_slot` and the Go `slot_test.go` cover the lifecycle.

### 8. Hash-chained audit (`go/internal/audit/`)

Every decision appends to a tamper-evident chain. Two defects found while building it are in the ship report and worth reading: Postgres stores microsecond timestamps while Go carries nanoseconds, so hashes recomputed on read did not match until timestamps were canonicalised; and storing the hashed payload as `JSONB` normalised key order, so stored bytes did not match hashed bytes. Both would have broken every verification the moment it was attempted.

### 9. Masking, in two languages (`go/internal/masking/`, `python/src/inspector/masking.py`)

Account identifiers are masked before they reach logs or the console. `parity_export_test.go` and `test_masking_parity.py` assert that Go and Python mask identically, from the same fixture. One defect found: "last four" of a four-character value is all of it.

### 10. Contracts (`proto/harbormaster/v1/harbormaster.proto`)

Defined once, generated for both languages. `go/internal/contract/roundtrip_test.go` and `python/tests/test_contract_roundtrip.py` are the cross-language gate: Go marshals, Python asserts, and vice versa.

### 11. The operations console (`go/internal/web/`)

Embedded Go templates and HTMX over Postgres read models projected from the topics. `/api/ops` exposes posture for whoever is on call. Read models are projections and can be rebuilt by replaying from offset zero.

### 12. The reference corpus (`python/src/corpus/`)

`generate.py` produces the corpus deterministically; `test_corpus_generation_is_reproducible` asserts byte-identical output from the same seed. `scenarios.py` defines the twelve adversarial fixtures, and `test_every_scenario_documents_what_it_breaks` refuses a fixture without a stated purpose.

## Things worth noticing

- **Model dependence falls over time.** Template caching plus promotion into configuration means the second file with a known layout costs zero model calls, and that is asserted rather than hoped: `test_correctness_targets_across_the_corpus`.
- **Eight defects found during construction are listed in the ship report**, each with what it would have cost had it shipped. A build record that hides its defects is not a build record.
- **Go and Python were chosen for what each is good at**, and the seam is a generated contract. Twenty decisions in `design/decisions.md` explain every significant choice, with the costs.
- **The demo is adversarial.** `make demo` does not run clean files through a happy path; it runs the twelve fixtures that were designed to break it.

## Questions this project answers, and where

| Question | Where the answer lives |
|---|---|
| How do you onboard a new client's file layout without writing code? | `config/clients/`, and the promotion path in `mapping/resolver.py` |
| What happens when a venue changes its columns overnight? | The ladder escalates to Tier 2 or 3, caches the result, and a reviewer promotes it; `docs/runbook.md` covers the operator side |
| How do you keep an LLM from silently corrupting a reconciliation? | One-way escalation, evidence on every mapping, quarantine over guessing: `confidence.py` and `resolver.py` |
| How would you prove, months later, why a file was dispatched the way it was? | The hash chain in `go/internal/audit/` and `make verify-audit` |
| How do you recover from a bad deployment? | Ship report §6: revert the binary and replay the log; read models are projections |
| What would you do differently at production scale? | Ship report §5: leader election for the sweep, SSO on the console, load testing against the 1,000/day envelope |

## What it does not claim

Throughput is designed for, not measured. The live model tier and the end-to-end Compose suite are written and documented as gates to run on a host with Docker. Excel and email parsing cover the corpus, not every artefact a venue can produce.
