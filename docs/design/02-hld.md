# Harbormaster — High-Level Design

**Status:** Phase 1 draft, awaiting sign-off
**Last updated:** 2026-08-30
**Requirements:** `01-requirements.md`

---

## 1. Architecture style

**Event-driven pipeline over a log, with a polyglot service split.**

Every stage communicates through durable, replayable topics rather than direct
calls. This is chosen for three reasons drawn straight from the requirements:

- **FR-40 replay and NFR-3 restart safety.** A log-based backbone makes "reprocess
  everything from Tuesday" a consumer-offset operation, not a bespoke batch job.
  For a reconciliation control system this is not a nicety: when a mapping bug is
  found, the ability to replay three days of arrivals through corrected logic is
  the difference between a fix and an incident.
- **Asymmetric workloads.** Watching a directory is cheap, constant and must never
  stop. Classifying a 250k-row file is expensive, bursty and occasionally calls a
  language model. Decoupling them means a slow classification never causes a
  missed arrival, and classification can be scaled independently.
- **Audit by construction (FR-37, FR-39).** The event log *is* the audit trail.
  Decisions are not reconstructed from application logs after the fact; they are
  the messages the system runs on.

Rejected alternatives: a monolithic scheduled batch job (cannot satisfy
continuous arrival or replay, and couples ingestion latency to parse cost); direct
synchronous service calls (loses the audit log, couples availability).

## 2. System context

```
        ┌──────────────┐   ┌──────────────┐
        │ FTP landing  │   │ upstream     │
        │ directory    │   │ JSON queue   │
        └──────┬───────┘   └──────┬───────┘
               │                  │
               ▼                  ▼
        ┌──────────────────────────────┐
        │  PORTWATCH        (Go)       │  arrival detection, stability,
        │                              │  hashing, dedupe gate
        └──────────────┬───────────────┘
                       │ hm.arrivals.raw
                       ▼
        ┌──────────────────────────────┐
        │  INSPECTOR        (Python)   │  format sniff, parse, client ID,
        │                              │  value-date resolution, field
        │                              │  mapping T1/T2/T3, confidence
        └───────┬──────────────┬───────┘
                │              │ hm.arrivals.quarantined
   hm.arrivals.classified      ▼
                │       ┌─────────────┐
                │       │ review queue│◄── hm.review.decisions
                │       └──────┬──────┘
                ▼              │
        ┌──────────────────────▼───────┐
        │  BERTHMASTER      (Go)       │  expectation state machine,
        │                              │  side pairing, late window,
        │                              │  supersession, missing alerts
        └──────────────┬───────────────┘
                       │ hm.berth.assigned / .superseded / hm.alerts.missing
          ┌────────────┴────────────┐
          ▼                         ▼
  ┌───────────────┐        ┌──────────────────┐
  │ RECON STUB    │        │ CONTROL PLANE(Go)│──► UI (React/TS)
  │ (out of scope)│        │ read models, SSE │
  └───────────────┘        │ review actions   │
                           └──────────────────┘

  Cross-cutting: hm.audit.decisions (hash-chained) ──► Postgres
```

## 3. Component breakdown

| Component | Language | Responsibility | Why this language |
|---|---|---|---|
| **Portwatch** | Go | Directory watch, write-completion detection, streaming SHA-256, JSON queue ingress, duplicate gate | Long-lived daemon whose job is concurrent I/O and never falling over. Goroutines make per-file stability tracking trivial; streaming hash of a 2 GB file costs constant memory; ships as a static binary with no runtime. |
| **Inspector** | Python | Format detection, parsing, client attribution, value-date resolution, canonical field mapping, confidence scoring | The work is data-shaped and model-adjacent. Polars, openpyxl, lxml, ONNX embeddings and the Anthropic SDK all live here. Iteration speed on heuristics matters more than raw throughput, and the workload parallelises across consumer instances rather than threads. |
| **Berthmaster** | Go | Expectation state machine per client/domain/value-date, side pairing, T±2 late window, supersession, missing-file alerts | This is stateful scheduling with timers and windows. Go's concurrency and timer primitives fit it directly, and correctness here is about state transitions, not data wrangling. |
| **Control plane** | Go | REST + SSE API, Kafka→Postgres read-model projection, review action publishing, static UI hosting | It is a stream consumer that also serves HTTP. Keeping it in Go means Python stays single-purpose (the brain) rather than becoming an incidental web tier. |
| **UI** | Go templates + HTMX | Arrival board, confidence breakdown, quarantine review, berth assignments | Client-side state suits a live-updating board fed by SSE. |
| **Recon stub** | Python | Consumes berth assignments, emits a fake break report | Deliberately trivial. Exists only to prove the output contract. |

**The split in one line:** Go at the edges where the work is I/O, concurrency and
uptime; Python in the middle where the work is data shape and inference.

## 4. Data architecture

### 4.1 Topics

| Topic | Producer | Consumers | Key | Retention |
|---|---|---|---|---|
| `hm.arrivals.raw` | Portwatch | Inspector | content hash | 7d |
| `hm.arrivals.classified` | Inspector | Berthmaster, Control plane | client:domain:value_date | 30d |
| `hm.arrivals.quarantined` | Inspector | Control plane | arrival id | 30d |
| `hm.review.decisions` | Control plane | Berthmaster, Inspector | arrival id | 30d |
| `hm.berth.assigned` | Berthmaster | Recon stub, Control plane | client:domain:value_date | 90d |
| `hm.berth.superseded` | Berthmaster | Recon stub, Control plane | client:domain:value_date | 90d |
| `hm.alerts.missing` | Berthmaster | Control plane | client:domain:value_date | 30d |
| `hm.audit.decisions` | all | Control plane | arrival id | compacted, infinite |

Partitioning by `client:domain:value_date` on the downstream topics guarantees
that all events for one reconciliation slot land on one partition and are
therefore ordered. That single choice is what makes supersession (FR-8, FR-9)
tractable without distributed locking.

### 4.2 Persistent stores

| Store | Contents | Rationale |
|---|---|---|
| **Postgres** | Read models (arrival board, slot state), expectation state, hash-chained decision log, template mapping cache, review decisions | Relational because the queries are relational: "which slots are open for client X within T±2". `JSONB` columns carry the variable-shape classification payloads without schema churn. |
| **Object store** | Landed raw files, canonical Parquet output | Behind an interface with a filesystem adapter for local demo and an S3 adapter for the production shape. MinIO available under an optional compose profile. |

Canonical output is written as **Parquet**, not CSV: typed, columnar, and it
preserves the distinction between a null field and an empty one, which matters
when the downstream engine must not treat a missing settlement price as zero.

### 4.3 Contracts

All inter-service messages are defined **once** in Protobuf under `proto/`, with
Go and Python types generated by `buf`. Encoding on the wire is `protojson`.

This is the single most important structural decision in a polyglot system. Two
languages consuming the same topic with hand-written structs on each side will
drift, and the drift will surface as a silent field-level mismatch in production
rather than a compile error. Proto-as-source-of-truth turns that class of bug
into a build failure. JSON encoding is retained over binary so that topics remain
human-readable during a demo and during incident triage — a deliberate trade of
throughput we do not need for legibility we do.

## 5. Critical flows

### 5.1 Happy path

1. Client drops `CLNT004_TRADES_20260830.csv`. Portwatch sees the create event,
   waits for size to quiesce for `stability_window`, streams SHA-256, checks the
   hash against seen-set, publishes `arrivals.raw`.
2. Inspector sniffs CSV, parses headers, matches client via filename pattern and
   embedded account IDs, reads the `Value Date` column, maps 14 columns to
   canonical fields (12 by alias, 2 by fuzzy), scores 0.94, writes Parquet,
   publishes `arrivals.classified`.
3. Berthmaster loads the client's expectation for `TRADE / 2026-08-30`, finds the
   GL extract already present on Side 1, marks the slot complete, publishes
   `berth.assigned`.
4. Recon stub consumes it and runs. Control plane projects all of the above onto
   the board.

### 5.2 Late arrival with date disagreement

File lands 2026-08-31 06:40 named `..._20260831.csv`, contents dated 2026-08-28.
Inspector derives three candidates (filename 08-31, content 08-28, arrival 08-31),
applies content-precedence (FR-12), validates 08-28 is a business day on the
client's calendar, sets `mismatch_flagged = true`, confidence 0.88. Berthmaster
finds the 08-28 slot still open (within T±2), assigns, and the board shows the
disagreement banner. The reconciliation runs against the correct historical day —
which is the entire point of the project.

### 5.3 Correction superseding a dispatched slot

An amended file for an already-assigned slot arrives with a different hash.
Portwatch passes it through (not a duplicate). Inspector classifies to the same
`client:domain:value_date`. Berthmaster sees an existing `ASSIGNED` slot, emits
`berth.superseded` naming the void assignment, then a fresh `berth.assigned`.
Same partition, so strictly ordered: the recon stub can never see the replacement
before the void.

### 5.4 Low-confidence email blob → four-eyes

An email body describing a cash movement yields client confidence 0.71.
Composite score falls in the quarantine band. Inspector publishes to
`arrivals.quarantined` with its full reasoning. A reviewer sees the board, corrects
the client attribution, approves. Control plane publishes `review.decisions`.
Berthmaster proceeds; the approving user is stamped on the audit record (FR-32).

### 5.5 Duplicate suppression

Same content redelivered under a new filename. Portwatch's hash lookup hits.
No `arrivals.raw` is published. A suppression record goes to `audit.decisions`
referencing the original arrival, so the board can show "seen 3×" rather than
silently discarding evidence that a client's scheduler is misconfigured.

## 6. The three-tier mapping strategy

The design decision that carries the most weight, so stated explicitly:

| Tier | Mechanism | Cost | Handles |
|---|---|---|---|
| **T1** | Alias dictionary lookup on normalised headers | ~µs | The ~85% of columns that are named something the industry already names them |
| **T2** | Rapidfuzz token-set ratio + ONNX MiniLM cosine similarity against canonical field descriptions | ~ms | Novel phrasings, abbreviations, near-misses |
| **T3** | Claude, given the header set, sample rows and client context, returning a structured mapping | ~s + $ | Genuinely ambiguous layouts, free-text email bodies, first sight of a new client template |

Escalation is one-way and results are cached by **template fingerprint** (an
ordered hash of the header set). The second file with the same layout costs
nothing. Confirmed T3 decisions are promoted into the client's T1 dictionary
(FR-28), so the system's model dependence decreases over time rather than
growing. NFR-8's ≤2% target is a direct consequence.

An LLM-first design would be simpler to write and worse in every dimension that
matters here: slower, non-deterministic across runs, unauditable at scale, and
unbounded in cost at 1,000 files a day. The model is used where judgement is
genuinely required, not as a substitute for a dictionary.

## 7. Tech-stack recommendation

Options and trade-offs per layer. The recommendation is bolded.

| Layer | Options | Recommendation |
|---|---|---|
| Edge/daemon language | **Go** (static binary, goroutines, mature fsnotify) · Rust (faster, steeper, slower to write) · Python (one less language, poor fit for a long-lived watcher) | **Go 1.23** |
| Intelligence language | **Python 3.12** (only viable ecosystem for parsing + embeddings + LLM SDK) · Go (would mean reimplementing Excel/Parquet/embedding stacks) | **Python 3.12** |
| Event log | **Redpanda** (Kafka wire-compatible, single binary, no ZooKeeper/JVM, ~10s cold start) · Apache Kafka KRaft (canonical, heavier locally) · NATS JetStream (lighter, smaller ecosystem) | **Redpanda**, Kafka-compatible so the skill and the code transfer unchanged |
| Contracts | **Protobuf + buf** (single source of truth across languages) · JSON Schema (weaker codegen) · hand-written structs (drift) | **Protobuf 3 + buf**, `protojson` on the wire |
| Dataframe | **Polars** (Rust core, lazy, strong typing, fast on wide files) · pandas (ubiquitous, heavier, weaker nulls) | **Polars** |
| Store | **Postgres 16** · SQLite (no concurrent writers) · Mongo (loses the relational slot queries) | **Postgres 16** with JSONB |
| Embeddings | **fastembed** (ONNX MiniLM, ~90 MB, no torch) · sentence-transformers (~2 GB image with torch) · fuzzy-only (weaker T2) | **fastembed**, using MiniLM-L6-v2 weights; degrades to fuzzy-only if unavailable |
| LLM | **Anthropic Claude** via official SDK, structured output, prompt caching | **Claude**, behind a `MappingAdjudicator` interface with a deterministic fake for offline tests |
| API/UI backend | **Go + chi + SSE** · Python FastAPI (adds a web tier to the brain service) | **Go + chi**, SSE for live board updates |
| Frontend | **Server-rendered Go templates + HTMX + hand-written CSS** (zero build step, no Node in the image, fully offline) · React/TS/Vite (more client state, adds a build stage) | **Go html/template + HTMX + bespoke CSS**, vendored assets, served directly by the control plane |
| Orchestration | **Docker Compose** | **Compose**; a single core profile of 6 services, no optional profiles |
| Observability | **Structured logs** (`slog` / `structlog`) with correlation IDs · add Prometheus/Grafana | **Structured logs only**; no metrics stack in the demo |
| CI | **GitHub Actions** running the same `make check` as local | **GitHub Actions** |

## 8. Cross-cutting concerns

**Idempotency.** Every consumer is keyed on content hash or arrival ID and writes
through an upsert. At-least-once delivery is assumed; exactly-once is not.

**Masking (FR-38, per gate decision).** Account *numbers* are masked to last-4 in
logs and UI; account *names* remain visible. Masking is applied in a serialisation
hook, not at each call site, so it cannot be forgotten.

**Tamper-evident audit (FR-37).** Each `audit.decisions` record carries the SHA-256
of the previous record for its arrival, forming a per-arrival hash chain. A
verification command walks the chain and reports the first break.

**Time.** All timestamps are UTC internally. Value dates are calendar dates with no
timezone, resolved against a per-client calendar. Venue local time is used only
when interpreting a source timestamp, never for storage.

**Configuration.** Client YAML is loaded, schema-validated and hot-reloadable.
Invalid config fails at load with a pointer to the offending path, never at 3 a.m.
mid-file.

**Backpressure.** Inspector consumes with bounded in-flight work and manual offset
commit after successful publish, so a slow classification stalls its own partition
rather than dropping messages.

## 9. Non-functional design

- **NFR-1/2 throughput and latency.** Inspector scales horizontally by partition
  count. Parsing is streaming for CSV/JSON; Excel is unavoidably whole-file, which
  is why the 250k-row qualifier exists in the target.
- **NFR-3 restart safety.** Portwatch persists its seen-set and last-scan
  watermark; on restart it rescans the directory and reconciles against the set.
- **NFR-9 idempotency.** Guaranteed by content-hash keying end to end.
- **NFR-11/12 operability and offline test.** `make up` starts the stack;
  `make demo` seeds and drives the reference corpus; `make check` runs everything
  with the fake adjudicator and no network.

## 10. Risks

| # | Risk | Mitigation |
|---|---|---|
| R-1 | Value date genuinely undeterminable from a given file | Quarantine rather than guess; the review queue exists precisely for this |
| R-2 | LLM returns a plausible but wrong mapping | Structured output validated against the canonical schema; low-confidence results quarantined; T3 never auto-promotes without human confirmation |
| R-3 | Cross-language contract drift | Protobuf single source; `make check` fails on uncommitted codegen |
| R-4 | Excel format variance (merged cells, multi-row headers, embedded totals) | Explicit header-detection heuristics with a documented failure mode; corpus includes an awkward workbook |
| R-5 | Synthetic corpus is easier than reality | Corpus is written to include the twelve named adversarial cases from requirements §8, not just happy paths |
| R-6 | Compose stack too heavy to demo | Six services, no Node build, no metrics stack; `make up` to green in under a minute |
| R-7 | Supersession race across partitions | Partition key includes the full slot identity, making ordering a property of the design rather than a runtime hope |

## 11. Open questions

Carried to the Phase 1/2 gate.
