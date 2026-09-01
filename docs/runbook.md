# Runbook

What to run, what to look at, and what to do when something is wrong.

---

## First checkout

```bash
cd go && go mod tidy   # resolves the Go module graph; needed once
cd .. && make check
```

`make check` runs format, lint, type check, protobuf lint, generated-code
staleness, and every unit, property, contract and scenario test. It needs no
network, no broker, no database and no API key. If it passes, the repository is
consistent.

## Running the stack

```bash
make up            # redpanda, postgres, topic-init, and five services
make logs          # follow everything
make down          # stop and remove volumes
```

The board is at <http://localhost:8080>. Cold start should reach healthy in
under a minute; `topic-init` runs once, creates the eight topics and exits, so
seeing it in `Exited (0)` is correct rather than a failure.

## Seeing it work

```bash
make demo
```

Generates the adversarial corpus and drops it into the landing directory one
case at a time, narrating what should happen. Watch the board while it runs.
Roughly five minutes end to end.

To drive it yourself instead, drop any file into `data/landing/`. Portwatch
polls every two seconds and waits for the file to stop changing before emitting
it, so expect a few seconds before it appears.

## What to look at

| Where | What it tells you |
|---|---|
| `/` | Every arrival, its client, its resolved value date, and its disposition. A dot beside a date means the filename and the contents disagreed. |
| `/arrivals/{id}` | Why that value date was chosen, and column by column which tier mapped each field and on what evidence. |
| `/quarantine` | Files waiting on a human, each with a specific reason. |
| `/slots` | Reconciliation slots, which side is still missing, and how long the late window has left. |

## Verifying the audit trail

```bash
make verify-audit
```

Walks every per-arrival hash chain and exits non-zero if any record has been
altered or removed, naming the first break. Worth running on a schedule: an
audit log nobody verifies is a filing cabinet, not a control.

## Enabling the model tier

Off by default. The deterministic stand-in is bound unless you say otherwise, so
a misconfigured deployment runs without a model rather than failing to start.

```bash
HM_ADJUDICATOR=claude ANTHROPIC_API_KEY=sk-... make up
HM_LIVE=1 make test-live      # opt-in test against the real API
```

Cost is bounded by the template cache: the second file with a given layout is
resolved from cache and costs nothing. Watch `HM_ADJUDICATOR=claude` logs for
`calls` and token counts.

## Configuration

| Variable | Component | Default |
|---|---|---|
| `HM_LANDING_DIR` | portwatch | `/data/landing` |
| `HM_SCAN_INTERVAL` | portwatch | `2s` |
| `HM_STABILITY_WINDOW` | portwatch | `5s` |
| `HM_KAFKA_BROKERS` | all | `redpanda:9092` |
| `HM_POSTGRES_DSN` | Go services | `postgres://hm:hm@postgres:5432/hm?sslmode=disable` |
| `HM_ADJUDICATOR` | inspector | `fake`, or `claude` |
| `ANTHROPIC_API_KEY` | inspector | unset; required only for `claude` |
| `HM_CONF_DISPATCH` | inspector | `0.85` |
| `HM_CONF_QUARANTINE` | inspector | `0.60` |
| `HM_LATE_WINDOW_DAYS` | berthmaster | `2` |
| `HM_MASK_ACCOUNTS` | all | `true` |
| `HM_HTTP_ADDR` | controlplane | `:8080` |

Client configuration lives in `config/clients/*.yaml` and calendars in
`config/calendars/*.yaml`. Both are validated strictly at load: an unknown key
is an error naming the file and the path, not a warning. A service that will not
start because of a typo is a better outcome than one that runs with the typo
silently ignored.

## When something is wrong

**A file landed but never appeared on the board.**
Check `make logs` for `portwatch`. A file still being written is deliberately not
emitted until its size and mtime stop changing. If it is ignored entirely, check
its extension against `IgnoreSuffixes` — `.tmp`, `.part` and `.done` are skipped
by design.

**A file appeared but has no client.**
It is in `/quarantine` with a reason. Either no filename pattern matched or no
known account identifier appeared in the contents. Fix the client YAML, or
correct it in the review screen.

**The value date looks wrong.**
Open the arrival. The detail page shows all three candidate sources and which
one was used. If the contents genuinely carry the wrong date, the client's
extract is wrong, and the review screen can override it with your name attached.

**A reconciliation ran against stale data.**
Check `/slots` for a `SUPERSEDED` state and `/api/assignments` for a `voided_at`.
A correction voids the prior assignment before issuing its replacement; both
carry the same slot key so the recon engine cannot see them out of order.

**The board is stale but the pipeline is fine.**
The read models are projections, never a source of truth. Stop the control
plane, truncate `arrival`'s projected columns, `assignment` and `alert`, and
restart; the projector rebuilds from the topics.

**`make check` fails on generated code.**
Run `make proto` and commit the result. Generated code is committed on purpose
so staleness is a visible diff rather than an invisible drift.

**Postgres is up but the control plane reports not ready.**
`/readyz` queries the store rather than merely reporting process liveness. Check
`HM_POSTGRES_DSN` and that migrations applied.

## Scaling notes

Inspector scales horizontally by partition count; it is the only component whose
work is unbounded per message. Portwatch is deliberately single-instance per
landing directory, though the database constraint arbitrates correctly if two
are run. Berthmaster's slot state is in Postgres, so multiple instances are safe,
but the overdue sweep would then run more than once per interval and should be
leader-elected before doing so.
