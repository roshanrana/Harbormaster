# Harbormaster — Overview

**What it is:** the control layer that sits between a bank's file landing zone and its reconciliation engine, deciding which client a file belongs to, which business day it describes, and how its columns map onto the schema the engine expects. It declines when it cannot decide, and it records why.

**Read this if** you want the problem, the shape of the solution and what has been measured. For a feature-by-feature walk with commands, see [SHOWCASE.md](SHOWCASE.md).

---

## The setting

Reconciliation is a bank's daily proof that its books agree with the outside world. Trades, positions, cash and collateral are compared against what clients, custodians, clearing houses and exchanges say they hold. The internal side is well controlled. The external side arrives all day into a single FTP landing directory, as CSV, Excel, XML, FIXML and free-text email bodies, with a parallel stream of JSON messages from upstream integrations.

The reconciliation engine downstream is deliberately simple: it is configured with an expected file on each side and it matches records. It has no opinion about which client produced a file, what value date its contents belong to, or which of four price columns is the trade price. It has to be told. In most institutions, a person tells it, by hand, every morning, and the morning goes badly when a file arrives late, under a new name, or with a column layout the venue changed without notice.

Harbormaster is the thing that tells it, automatically where it can and with an explicit request for help where it cannot.

## The three hard problems

**Which day is this, really.** A file named `MCP_TRD_20260831.csv` landing at 06:40 on the 31st routinely contains the 28th's business. Reconcile it against the 31st and every row breaks; an analyst spends the morning discovering that nothing was wrong except the date. Harbormaster consults the filename, the content, and the arrival time against each client's business calendar, ranks them by how much they actually know, and surfaces a disagreement rather than resolving it silently.

**Which price is the price.** A cleared-futures extract carries traded price, prior settlement, official settlement and a mark. Swap two and the reconciliation still runs, still returns a number, and is wrong. Header vocabulary resolves most columns. What resolves the rest is structure: a settlement price is a property of an instrument on a day and repeats across rows; a trade price is a property of an execution and varies. Harbormaster uses that.

**When to stop guessing.** A wrong mapping costs more than an unresolved one, because unresolved becomes a review item and wrong becomes a silent break. Harbormaster declines, quarantines and asks, and every reason it gives names what it could not decide.

## The shape of the solution

Six services over a Kafka-compatible log. Go sits at the edges, where the work is I/O, concurrency and uptime; Python sits in the middle, where the work is data shape and inference. Message contracts are defined once in Protobuf and generated for both languages, so cross-language drift is a build failure rather than a silent field mismatch in production.

```
FTP landing dir ─┐
                 ├─► PORTWATCH (Go) ─► INSPECTOR (Python) ─► BERTHMASTER (Go) ─► reconciliation engine
JSON queue ──────┘   arrival, hashing,   parsing, attribution,   slot state machine,
                     write-completion,   value date, mapping     late window,
                     dedupe              ladder, confidence      supersession
                                              │
                                    quarantine ─► review queue (four-eyes)
                                              │
                                    CONTROL PLANE (Go) ─► operations console, /api/ops
```

Everything communicates through durable, replayable topics. The audit trail is a property of the architecture rather than a feature bolted onto it: read models are projections and can be rebuilt from offset zero, and a bad deployment is recovered by reverting the binary and replaying.

## The mapping ladder

The part most worth understanding. Every source column is mapped onto one canonical schema through three escalating tiers:

| Tier | Mechanism | Cost | Handles |
|---|---|---|---|
| 1 | Alias dictionary over normalised headers | microseconds | The columns the industry already has a name for |
| 2 | Fuzzy string match plus local sentence embeddings | milliseconds | Abbreviations, near-misses, different words for the same thing |
| 3 | A language model, given headers, samples and client context | seconds, and money | Genuinely novel layouts and free-text bodies |

Escalation is one-way. Each tier sees only what the previous one declined, and a column the dictionary resolved is never re-litigated by a model. Results are cached by template fingerprint, so the second file with a given layout costs nothing, and a reviewer can promote a confirmed mapping into the client's configuration, after which it resolves at Tier 1 forever.

**Model dependence therefore decreases as the system runs.** That is the opposite of the usual trajectory for an "AI-powered" integration, and it is the design's central claim.

## What has been measured

Against a committed synthetic corpus, generated deterministically across eight venue vocabularies and five currencies, with twelve fixtures adversarial by design:

| Target | Requirement | Measured |
|---|---|---|
| Client attribution | ≥ 99% | 100% of attributable fixtures |
| Value date correct | ≥ 98% | 100%; every resolved date is a business day on the client's calendar |
| Date disagreements flagged | 100% | 100%, asserted per fixture |
| Mapping provenance | 100% | Every dispatched mapping carries a tier and non-empty evidence |
| Quarantine rate | ≤ 5% | 0% of well-formed fixtures; only the deliberately unattributable file is held |
| Model escalation, warm | ≤ 2% | Second file with a known layout costs zero adjudications |
| Idempotency | — | Reprocessing the same content produces no additional instruction, in both languages |

379 tests. `make check` completes offline in about forty seconds with no broker, no database, no network and no API key. End-to-end and live-model suites are written and documented as gates to run on a host with Docker; the ship report marks them as such rather than claiming them.

## Honest limits

From [`ship-report.md`](ship-report.md) §5: Tier 2 embeddings are optional and the suite exercises the fuzzy-only degraded path; Excel parsing covers the quirks in the corpus, not all quirks; the email parser is deliberately conservative; the overdue sweep is not leader-elected; the console has no authentication because it would sit behind the institution's SSO; throughput is designed for, not load-tested.

## Where it sits among the other projects

Harbormaster is the front door to reconciliation. [LEDGERLENS](https://github.com/roshanrana/LedgerLens) is what a reconciliation engine with bounded AI adjudication looks like on the other side of the berth assignment. [SHADOWBOOK](https://github.com/roshanrana/shadowbook) reconciles at a different level, between two ledgers. All three share the same rules: deterministic first, models behind explicit contracts, hash-chained evidence, and named adversarial fixtures.

## Further reading

| Document | For |
|---|---|
| [`design/01-requirements.md`](design/01-requirements.md) | 42 functional and 12 measurable non-functional requirements |
| [`design/02-hld.md`](design/02-hld.md) | Architecture, component split, tech-stack rationale |
| [`design/03-lld.md`](design/03-lld.md) | Frozen contracts, schemas, error taxonomy, test strategy |
| [`design/decisions.md`](design/decisions.md) | Twenty decisions with context, consequences and costs |
| [`runbook.md`](runbook.md) | Start, seed, demo, verify, teardown, and what to do when it breaks |
| [`ship-report.md`](ship-report.md) | Gate results, measured correctness, defects found during construction, known issues |
