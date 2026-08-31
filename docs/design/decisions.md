# Decision Log

Append-only. Each entry: context, decision, consequences. Newest at the bottom.

---

### ADR-001 — Event-driven log backbone over batch or synchronous calls
**Phase:** 1
**Context:** Arrivals are continuous and bursty; classification cost is uneven; the
system must be replayable and auditable (FR-37, FR-40, NFR-3).
**Decision:** All stages communicate over durable Kafka-compatible topics.
**Consequences:** Replay becomes an offset operation. The audit trail is the event
log rather than a parallel artefact. Cost: operational surface of a broker, and
at-least-once semantics that force idempotent consumers.

### ADR-002 — Polyglot split: Go at the edges, Python in the middle
**Phase:** 1
**Context:** Portwatch and Berthmaster are long-lived I/O and state machines.
Inspector is data parsing and inference.
**Decision:** Go for Portwatch, Berthmaster, Control plane. Python for Inspector
and the recon stub.
**Consequences:** Each component uses the language that fits its workload, and
Python stays single-purpose. Cost: two toolchains, two test harnesses, and a hard
requirement for shared contracts (see ADR-003).

### ADR-003 — Protobuf as the single source of truth for message contracts
**Phase:** 1
**Context:** Two languages consuming the same topics will drift if each hand-writes
its structs, and the drift surfaces as silent field mismatches.
**Decision:** Define all messages in `proto/`, generate Go and Python types with
`buf`. Encode on the wire as `protojson`.
**Consequences:** Contract drift becomes a build failure. Topics stay
human-readable for demos and triage. Cost: a codegen step in `make check`, and
JSON encoding overhead we can afford at this volume.

### ADR-004 — Three-tier field mapping, not LLM-first
**Phase:** 1
**Context:** 1,000 files/day, each with 10–40 columns. An LLM call per column is
slow, non-deterministic and unbounded in cost.
**Decision:** Deterministic alias dictionary → local fuzzy/embedding match →
Claude adjudication for the residue only. Cache by template fingerprint; promote
confirmed model decisions into the client dictionary.
**Consequences:** Model dependence decreases over time. NFR-8 (≤2% of arrivals
reaching T3) is achievable. Cost: three code paths to maintain and a dictionary
that needs curating.

### ADR-005 — Partition downstream topics by full slot identity
**Phase:** 1
**Context:** Supersession (FR-9) requires that a void and its replacement are seen
in order by every consumer.
**Decision:** Key `arrivals.classified`, `berth.*` and `alerts.missing` on
`client:domain:value_date`.
**Consequences:** Ordering within a reconciliation slot is a structural property,
not a runtime hope. No distributed locking needed. Cost: potential partition skew
if one client dominates volume; acceptable at this scale.

### ADR-006 — Parquet for canonical output, not CSV
**Phase:** 1
**Context:** The downstream engine must distinguish a missing settlement price from
a zero one.
**Decision:** Canonical records are written as typed Parquet.
**Consequences:** Nulls survive, types survive, files are smaller. Cost: not
directly readable in a text editor, mitigated by a `hm inspect` command.

### ADR-007 — fastembed (ONNX) over sentence-transformers for Tier 2
**Phase:** 1
**Context:** Tier 2 needs sentence embeddings; sentence-transformers pulls PyTorch
and roughly 2 GB of image.
**Decision:** Use fastembed with MiniLM-L6-v2 ONNX weights; degrade to fuzzy-only
if the model is unavailable.
**Consequences:** Container stays small and CPU-only. Cost: fewer model options,
and a documented degraded mode.

### ADR-008 — Redpanda as the local broker
**Phase:** 1
**Context:** Need a Kafka-compatible log that starts fast in Compose.
**Decision:** Redpanda, single binary, no ZooKeeper or JVM.
**Consequences:** Sub-15-second cold start; identical client code to Apache Kafka.
Cost: none material at prototype scale; production would revisit.

### ADR-009 — Skill references directory absent; standard templates used
**Phase:** 1
**Context:** `enterprise-dev-lifecycle` names `references/design-templates.md`,
`references/execution-planning.md`, `references/context-engineering.md` and
`references/validation-shipping.md`, none of which are present in the installed
skill.
**Decision:** Proceed with conventional HLD/LLD/execution-plan structure and the
token-discipline rules stated inline in `SKILL.md`.
**Consequences:** Documents may differ cosmetically from the intended house
template. Flagged for the user; trivially reconciled if the references appear.

### ADR-010 — Late-arrival window T±2 business days
**Phase:** 0 gate
**Context:** Files may arrive early or late relative to their value date.
**Decision:** Reconciliation slots accept arrivals within ±2 business days of the
resolved value date, per-client overridable.
**Consequences:** Bounded slot state. Anything outside the window becomes a
missing-file alert or a quarantine rather than an unbounded open slot.

### ADR-011 — Masking policy: numbers masked, names visible
**Phase:** 0 gate
**Context:** Operators need to recognise a client at a glance without account
numbers leaking into logs and screenshots.
**Decision:** Account numbers masked to last-4 in logs and UI; account and client
names shown in full. Applied in a serialisation hook.
**Consequences:** Boards stay readable and screenshots stay safe. Cost: an
explicit privilege path is needed if full numbers are ever required.

### ADR-012 — Server-rendered HTMX over a React SPA
**Phase:** 2 gate
**Context:** The UI is a live board plus a review form. A React SPA would add Node,
a bundler, a build stage in the image and a second dependency tree.
**Decision:** Go `html/template` handlers with HTMX partial swaps and bespoke CSS.
Assets vendored; no Node anywhere in the repo.
**Consequences:** The control plane serves the UI directly, the image stays small,
and `make check` needs no JS toolchain. Cost: less client-side interactivity, which
this screen does not need.

### ADR-013 — fastembed confirmed for Tier 2
**Phase:** 2 gate
**Decision:** ONNX MiniLM via fastembed; fuzzy-only degraded mode retained.
**Consequences:** Inspector image stays roughly 90 MB rather than ~2 GB, CPU-only.

### ADR-014 — Structured logs only; no metrics stack
**Phase:** 2 gate
**Context:** Prometheus and Grafana would add two services and a dashboard to
maintain for a demo that has no load to observe.
**Decision:** Structured JSON logs with correlation IDs (`slog`, `structlog`). No
Prometheus, Grafana or OTel collector.
**Consequences:** Six services in Compose. Cost: no latency histograms; NFR-2 is
evidenced by timing assertions in the integration suite instead.

### ADR-015 — Filesystem object store by default, S3 adapter present but unwired
**Phase:** 2 gate
**Decision:** `ObjectStore` interface with an `fs` adapter as the default and an
`s3` adapter implemented and unit-tested but not exercised in the demo. No MinIO.
**Consequences:** The production storage path is visible in the code and the
migration is a config change, without a seventh container.

### ADR-016 — Poll the landing directory; do not use inotify
**Phase:** 4
**Context:** Landing directories in this setting are almost always NFS or SMB
mounts written by a remote FTP daemon. inotify does not fire for writes made by
another host, so an event-driven watcher would silently miss arrivals in exactly
the deployment where it matters most. (The `fsnotify` module is also unavailable
under this environment's egress policy, which prompted the review.)
**Decision:** Portwatch scans on a configurable interval and applies the quiet-window
stability rule from LLD §5.1. No inotify.
**Consequences:** Correct on network mounts, trivially testable, and restart-safe
because a scan is idempotent. Cost: detection latency bounded by the scan interval
rather than being instantaneous, which the 60-second NFR absorbs comfortably.

### ADR-017 — Bus interface with an in-memory implementation
**Phase:** 4
**Context:** Go logic should be unit-testable without a broker, and no in-process
Kafka fake is available for Go 1.22 here.
**Decision:** A `Bus` interface in Go with two implementations: `memory` for unit
tests and `franz` (franz-go) for real use. Mirrors the `MappingAdjudicator` seam on
the Python side.
**Consequences:** Slot state machine, supersession and audit chaining are all
testable in milliseconds with no infrastructure. Cost: the memory implementation
must faithfully preserve per-key ordering or tests will pass on false premises.

### ADR-018 — Split validation between environments
**Phase:** 4
**Context:** Docker is absent from the build environment. Compose, Redpanda and any
end-to-end run cannot execute during construction.
**Decision:** Each task pack is marked `validated-here` or `validate-on-host`.
Everything that can be executed during construction is: Python in full, Go unit
tests against a real local Postgres, proto codegen with a cross-language round-trip.
Compose, Redpanda and the end-to-end path are authored to spec and validated on the
user's machine via `make up && make test-e2e`.
**Consequences:** No task is marked done on unexecuted code, and the gap is visible
rather than implied. Cost: integration defects surface later than they otherwise
would.

### ADR-019 — Go dependency policy: github.com-hosted, minimal, stdlib-first
**Phase:** 4
**Context:** Egress policy blocks `golang.org/*`, `google.golang.org/*` and
`gopkg.in/*`.
**Decision:** Go dependencies limited to franz-go, lib/pq, goccy/go-yaml,
oklog/ulid and chi. HTTP, templating, JSON, crypto and file walking all use stdlib.
Generated protobuf code compiles via a gitignored `go.work` override in this
environment only; `go.mod` stays pristine.
**Consequences:** A small, auditable dependency tree, which is a virtue in this
domain regardless of what forced it. Cost: some conveniences hand-rolled.

### ADR-020 — Topics provisioned by infrastructure, not by the application
**Phase:** 4
**Context:** The Go admin client (`kadm`) pulls `golang.org/x/crypto`, which is
blocked here. That prompted a review of whether the application should be
creating topics at all.
**Decision:** Topics are created by a one-shot `rpk` step in the Compose stack.
Broker auto-creation is explicitly disabled. No service holds cluster-admin
rights at runtime.
**Consequences:** A typo in a topic constant now fails loudly instead of quietly
creating a new topic and stranding messages in it. The topic list, its partition
count and the audit topic's compaction policy are visible in the stack
definition rather than buried in Go. Cost: adding a topic is a stack change, not
a code change, which is the correct friction.
