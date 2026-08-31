# Harbormaster — Low-Level Design

**Status:** Phase 2 draft, awaiting sign-off
**Last updated:** 2026-08-30
**Upstream:** `01-requirements.md`, `02-hld.md`, `decisions.md`

Interfaces defined here are **frozen contracts**. Changing one after approval is an
LLD amendment, not a mid-task edit.

---

## 1. Repository layout

```
harbormaster/
├── Makefile                      # check | up | down | demo | seed | verify-audit
├── docker-compose.yml            # core profile + observability, minio profiles
├── buf.yaml, buf.gen.yaml
├── proto/harbormaster/v1/*.proto # frozen message contracts
├── go/
│   ├── go.mod                    # single module, three binaries
│   ├── cmd/portwatch/main.go
│   ├── cmd/berthmaster/main.go
│   ├── cmd/controlplane/main.go
│   ├── internal/arrival/         # stability detection, hashing, dedupe
│   ├── internal/ingress/         # ftp watcher, json queue consumer
│   ├── internal/slot/            # expectation state machine
│   ├── internal/registry/        # client YAML load + validate + calendars
│   ├── internal/bus/             # kafka producer/consumer wrappers
│   ├── internal/store/           # postgres access, migrations
│   ├── internal/audit/           # hash-chained decision log
│   ├── internal/masking/         # serialisation hook
│   ├── internal/web/             # html/template handlers + HTMX partials
│   ├── web/templates/*.html      # server-rendered views
│   ├── web/static/               # vendored htmx.min.js + hand-written CSS
│   └── gen/hmv1/                 # buf-generated Go types
├── python/
│   ├── pyproject.toml            # uv-managed
│   ├── src/inspector/
│   │   ├── main.py               # consumer loop
│   │   ├── sniff.py              # format detection by content
│   │   ├── parsers/              # csv, excel, xml, fixml, email, json
│   │   ├── attribution.py        # client + account identification
│   │   ├── valuedate.py          # 3-source resolution + calendar
│   │   ├── mapping/
│   │   │   ├── canonical.py      # canonical schema + alias dictionary
│   │   │   ├── tier1_alias.py
│   │   │   ├── tier2_local.py    # rapidfuzz + fastembed
│   │   │   ├── tier3_llm.py      # Anthropic adjudicator + fake
│   │   │   ├── prices.py         # trade vs settlement disambiguation
│   │   │   └── cache.py          # template fingerprint cache
│   │   ├── confidence.py
│   │   └── emit.py               # parquet write + publish
│   ├── src/reconstub/main.py
│   └── tests/
├── config/clients/*.yaml         # per-client configuration
├── config/calendars/*.yaml
├── corpus/                       # reference corpus generator + fixtures
├── docs/
└── .github/workflows/ci.yml
```

## 2. Frozen contracts — Protobuf

`proto/harbormaster/v1/harbormaster.proto`. Field numbers are permanent.

### 2.1 Enums

```protobuf
enum SourceFormat { SOURCE_FORMAT_UNSPECIFIED=0; CSV=1; EXCEL=2; XML=3;
                    FIXML=4; EMAIL_TEXT=5; JSON=6; }
enum ProductDomain { PRODUCT_DOMAIN_UNSPECIFIED=0; TRADE=1; POSITION=2;
                     CASH=3; COLLATERAL=4; }
enum ReconSide { RECON_SIDE_UNSPECIFIED=0; INTERNAL_GL=1; EXTERNAL_CLIENT=2; }
enum ResolutionTier { RESOLUTION_TIER_UNSPECIFIED=0; ALIAS=1; LOCAL=2;
                      LLM=3; HUMAN=4; UNRESOLVED=5; }
enum SlotState { SLOT_STATE_UNSPECIFIED=0; OPEN=1; PARTIAL=2; ASSIGNED=3;
                  SUPERSEDED=4; MISSING=5; }
enum ArrivalDisposition { ARRIVAL_DISPOSITION_UNSPECIFIED=0; DISPATCHED=1;
                          QUARANTINED=2; REJECTED=3; SUPPRESSED_DUPLICATE=4; }
```

### 2.2 ArrivalRaw → `hm.arrivals.raw`

| Field | # | Type | Notes |
|---|---|---|---|
| arrival_id | 1 | string | ULID, monotonic |
| detected_at | 2 | Timestamp | UTC |
| ingress | 3 | string | `FTP` or `QUEUE` |
| uri | 4 | string | object-store URI of the stored raw payload |
| original_name | 5 | string | filename or queue message id |
| size_bytes | 6 | int64 | |
| content_sha256 | 7 | string | hex |
| landing_dir | 8 | string | |
| stability_ms | 9 | int64 | how long size was quiescent before emit |

### 2.3 ArrivalClassified → `hm.arrivals.classified`

| Field | # | Type | Notes |
|---|---|---|---|
| arrival_id | 1 | string | ties to ArrivalRaw |
| classified_at | 2 | Timestamp | |
| format | 3 | SourceFormat | from content sniff |
| source_hint | 4 | string | venue, e.g. `CME`, `EUREX` |
| client_id | 5 | string | |
| client_confidence | 6 | double | |
| account_ids | 7 | repeated string | masked at serialisation |
| domain | 8 | ProductDomain | |
| recon_side | 9 | ReconSide | |
| value_date | 10 | ValueDateResolution | see 2.4 |
| row_count | 11 | int64 | |
| field_mappings | 12 | repeated FieldMapping | see 2.5 |
| canonical_uri | 13 | string | Parquet output |
| overall_confidence | 14 | double | |
| disposition | 15 | ArrivalDisposition | |
| review_reasons | 16 | repeated string | |
| template_fingerprint | 17 | string | ordered hash of header set |
| sub_batch_index | 18 | int32 | for multi-date splits (FR-16) |
| sub_batch_total | 19 | int32 | |

### 2.4 ValueDateResolution

| Field | # | Type |
|---|---|---|
| resolved | 1 | string (`YYYY-MM-DD`) |
| from_filename | 2 | string |
| from_content | 3 | repeated string |
| from_arrival | 4 | string |
| method | 5 | string |
| confidence | 6 | double |
| mismatch_flagged | 7 | bool |
| calendar_id | 8 | string |
| notes | 9 | string |

`method` ∈ `CONTENT_EXPLICIT`, `CONTENT_INFERRED`, `FILENAME`,
`ARRIVAL_MINUS_CALENDAR`, `LLM_ADJUDICATED`, `HUMAN`.

### 2.5 FieldMapping

| Field | # | Type |
|---|---|---|
| source_field | 1 | string (column, XPath, or FIX tag) |
| canonical_field | 2 | string |
| tier | 3 | ResolutionTier |
| confidence | 4 | double |
| evidence | 5 | string (one line: matched alias, similarity, or model rationale) |

### 2.6 BerthAssigned → `hm.berth.assigned`

| Field | # | Type |
|---|---|---|
| assignment_id | 1 | string |
| emitted_at | 2 | Timestamp |
| client_id | 3 | string |
| domain | 4 | ProductDomain |
| value_date | 5 | string |
| side_1 | 6 | SideRef (arrival_id, canonical_uri, row_count) |
| side_2 | 7 | SideRef |
| expectation_id | 8 | string (from client YAML) |
| confidence | 9 | double |
| supersedes | 10 | string (prior assignment_id, empty if none) |
| notes | 11 | string |

`BerthSuperseded` carries `assignment_id`, `superseded_by`, `reason`, `emitted_at`.

### 2.7 AuditRecord → `hm.audit.decisions`

| Field | # | Type |
|---|---|---|
| record_id | 1 | string |
| arrival_id | 2 | string |
| at | 3 | Timestamp |
| component | 4 | string |
| decision_type | 5 | string |
| inputs_json | 6 | string |
| outcome_json | 7 | string |
| actor | 8 | string (`system` or user id) |
| prev_hash | 9 | string |
| record_hash | 10 | string |

`record_hash = SHA256(record_id ‖ arrival_id ‖ at ‖ component ‖ decision_type ‖ inputs_json ‖ outcome_json ‖ actor ‖ prev_hash)`.

## 3. Canonical record schema

The single layout the downstream engine sees. Written as Parquet.

| Column | Type | Notes |
|---|---|---|
| arrival_id | string | provenance |
| source_system | string | venue |
| client_id | string | |
| account_id | string | unmasked in Parquet, masked in logs/UI |
| account_name | string | never masked (ADR-011) |
| trade_id | string | |
| instrument_id | string | ISIN/CUSIP/SEDOL/venue symbol |
| instrument_type | string | FUTURE, OPTION, EQUITY, FX, BOND, CASH, COLLATERAL |
| trade_date | date | |
| value_date | date | resolved, not as-printed |
| quantity | decimal(28,8) | signed |
| trade_price | decimal(28,8) | execution price |
| settlement_price | decimal(28,8) | official/MTM close |
| gross_amount | decimal(28,4) | |
| net_amount | decimal(28,4) | |
| market_value | decimal(28,4) | |
| currency | string | ISO 4217 |
| side | string | BUY/SELL/LONG/SHORT |
| domain | string | ProductDomain |

Decimals, never floats. A float64 net amount will eventually produce a one-cent
break that costs an analyst an afternoon.

## 4. Client configuration schema

`config/clients/<client_id>.yaml`:

```yaml
client_id: CLNT004
client_name: Meridian Capital Partners
calendar: US_EQUITY
accounts:
  - id: "8842-00119"
    name: "Meridian Global Macro"
    venues: [CME, ICE]
  - id: "8842-00204"
    name: "Meridian Systematic"
    venues: [EUREX]
filename_hints:
  - pattern: "^MCP_(?P<domain>TRD|POS|CSH|COL)_(?P<date>\\d{8})\\.csv$"
    domain_map: {TRD: TRADE, POS: POSITION, CSH: CASH, COL: COLLATERAL}
expectations:
  - id: EXP-CLNT004-TRADE
    domain: TRADE
    cadence: DAILY
    cuts_per_day: 2                # FR-10: intraday + EOD, not duplicates
    sides:
      internal_gl:   {source_hint: GL_EXTRACT, format: CSV}
      external_client: {source_hint: CME, format: [CSV, FIXML]}
    late_window_days: 2            # ADR-010
    value_date_field_hints: ["Value Date", "SettleDate", "ValDate"]
field_overrides:                   # promoted T3/human decisions (FR-28)
  "Px_Sett": settlement_price
  "Px_Last": trade_price
```

Validated on load against a JSON Schema derived from this structure. Unknown keys
are an error, not a warning.

## 5. Module design

### 5.1 Portwatch (Go)

```go
type Watcher interface { Watch(ctx context.Context) (<-chan Candidate, error) }
type StabilityPolicy struct { QuietWindow time.Duration; SentinelSuffix string; PollInterval time.Duration }
type DedupeStore interface { SeenBefore(ctx, sha256 string) (prior string, ok bool, err error) }
```

Write-completion detection: a file is emitted when either the sentinel exists, or
`size` and `mtime` are unchanged across `QuietWindow` (default 5s) with at least
two consecutive polls. On restart, a full directory rescan reconciles against the
dedupe store.

### 5.2 Inspector (Python)

```python
class Parser(Protocol):
    def sniff(self, head: bytes, name: str) -> float: ...     # 0..1 confidence
    def parse(self, path: Path) -> ParsedTable: ...           # headers + rows + meta

class MappingAdjudicator(Protocol):                            # T3 seam
    def adjudicate(self, req: AdjudicationRequest) -> AdjudicationResult: ...
```

Two implementations of `MappingAdjudicator`: `ClaudeAdjudicator` and
`DeterministicFake`. `make check` binds the fake, so the entire suite runs offline
(NFR-12). This seam is the difference between a testable system and a demo.

Pipeline order: sniff → parse → attribute client → resolve value date → map fields
→ disambiguate prices → score confidence → split sub-batches → write Parquet →
publish.

### 5.3 Price disambiguation (`prices.py`)

Given N price-like columns:
1. Strong token match against settlement vocabulary (`settle`, `sett`, `close`,
   `mtm`, `official`, `eod`) or trade vocabulary (`exec`, `fill`, `deal`, `last`).
2. Client `field_overrides`.
3. Structural evidence: a column constant across all rows sharing an instrument is
   a settlement price; a column varying per row is a trade price.
4. Cross-check against amount: `|quantity × candidate − net_amount|` minimised.
5. Residual ambiguity → T3, then quarantine if still unresolved.

Step 3 and step 4 are what separate this from string matching. They are also the
cases most likely to appear in a demo, so they are covered explicitly in the corpus.

### 5.4 Value date resolution (`valuedate.py`)

```
candidates = {filename, content_explicit[], content_inferred[], arrival}
if content_explicit is single-valued  -> CONTENT_EXPLICIT, conf 0.97
if content_explicit is multi-valued   -> split into sub-batches (FR-16)
elif content_inferred consistent      -> CONTENT_INFERRED, conf 0.85
elif filename parses to business day  -> FILENAME, conf 0.70
else                                  -> ARRIVAL_MINUS_CALENDAR, conf 0.55
mismatch_flagged = filename_date exists and != resolved
resolved must be a business day on the client's calendar, else roll per convention
```

### 5.5 Berthmaster (Go) — slot state machine

```
                 arrival(side1)            arrival(side2)
   [OPEN] ──────────────────────► [PARTIAL] ──────────────────────► [ASSIGNED]
      │                                │                                 │
      │ late_window elapsed            │ late_window elapsed             │ correction
      ▼                                ▼                                 ▼
   [MISSING]                       [MISSING]                       [SUPERSEDED] ──► [ASSIGNED']
```

Slot key: `(client_id, domain, value_date)`. Transitions are persisted in Postgres
inside the same transaction that records the audit entry, so a crash between
"assigned" and "audited" is impossible.

### 5.6 Confidence composition

```
overall = 0.35·client + 0.35·value_date + 0.30·mapping_coverage
mapping_coverage = Σ(weight_f · conf_f) / Σ(weight_f)   over required fields for the domain
```
Economically material fields (quantity, prices, amounts) carry weight 3; identifiers
weight 2; the rest weight 1. Thresholds: ≥0.85 dispatch, 0.60–0.85 quarantine,
<0.60 reject.

## 6. Database schema (abridged DDL)

```sql
CREATE TABLE arrival (
  arrival_id TEXT PRIMARY KEY, content_sha256 TEXT NOT NULL,
  original_name TEXT, ingress TEXT, uri TEXT, size_bytes BIGINT,
  detected_at TIMESTAMPTZ NOT NULL, disposition TEXT,
  classification JSONB, UNIQUE (content_sha256, original_name));
CREATE INDEX ON arrival (content_sha256);

CREATE TABLE slot (
  client_id TEXT, domain TEXT, value_date DATE, state TEXT NOT NULL,
  expectation_id TEXT NOT NULL, side_1_arrival TEXT, side_2_arrival TEXT,
  assignment_id TEXT, opened_at TIMESTAMPTZ, deadline TIMESTAMPTZ,
  PRIMARY KEY (client_id, domain, value_date));
CREATE INDEX ON slot (state, deadline);

CREATE TABLE audit_record (
  record_id TEXT PRIMARY KEY, arrival_id TEXT NOT NULL, at TIMESTAMPTZ NOT NULL,
  component TEXT, decision_type TEXT, inputs JSONB, outcome JSONB,
  actor TEXT, prev_hash TEXT, record_hash TEXT NOT NULL);
CREATE INDEX ON audit_record (arrival_id, at);

CREATE TABLE template_mapping (
  template_fingerprint TEXT, client_id TEXT, mappings JSONB NOT NULL,
  tier TEXT, confirmed_by TEXT, created_at TIMESTAMPTZ,
  PRIMARY KEY (template_fingerprint, client_id));

CREATE TABLE review (
  arrival_id TEXT PRIMARY KEY, reviewer TEXT NOT NULL, decision TEXT NOT NULL,
  corrections JSONB, decided_at TIMESTAMPTZ NOT NULL);
```

## 7. Control plane API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/arrivals?since=&client=&state=` | board rows |
| GET | `/api/arrivals/{id}` | full classification incl. per-field provenance |
| GET | `/api/slots?value_date=&state=` | slot board |
| GET | `/api/quarantine` | review queue |
| POST | `/api/quarantine/{id}/decision` | `{decision, corrections, reviewer}` → publishes `review.decisions` |
| GET | `/api/audit/{arrival_id}` | chain, with verification status |
| GET | `/api/events` | SSE stream of board deltas |
| GET | `/healthz`, `/readyz` | probes |

## 8. Error taxonomy

| Class | Example | Handling |
|---|---|---|
| `TRANSIENT` | broker unavailable, Postgres timeout | retry with backoff, do not commit offset |
| `MALFORMED` | unparseable file, invalid XML | reject, audit, no retry |
| `AMBIGUOUS` | client or value date undeterminable | quarantine for review |
| `CONFIG` | client YAML invalid or expectation missing | fail loud at load; arrival quarantined with a config-pointer reason |
| `MODEL` | LLM unavailable, malformed structured output | fall back to local tiers, mark tier `UNRESOLVED`, quarantine if material |
| `CONTRACT` | proto decode failure | dead-letter topic, alert |

Every class maps to exactly one disposition. There is no default branch.

## 9. Test strategy

| Level | Scope | Tool |
|---|---|---|
| Unit — Go | stability detection, slot transitions, masking, hash chain | `go test`, table-driven |
| Unit — Python | each parser, alias tiers, price disambiguation, value-date matrix | `pytest`, parametrised |
| Property | value-date resolver never returns a non-business day; mapping never assigns one canonical field twice | `hypothesis` |
| Golden | each corpus fixture → expected canonical Parquet + expected classification | `pytest` snapshot |
| Contract | proto round-trip Go↔Python for every message | both suites |
| Integration | Compose stack, corpus replayed, assert berth assignments | `make demo` + assertions |
| Scenario | the twelve adversarial cases from requirements §8, each an explicit named test | integration |

`make check` = format, lint (golangci-lint, ruff), type check (go vet, mypy),
buf lint + breaking-change check, codegen freshness, unit + property + golden +
contract tests. Offline, no network, fake adjudicator.

## 10. Configuration matrix

| Variable | Component | Default |
|---|---|---|
| `HM_LANDING_DIR` | portwatch | `/data/landing` |
| `HM_STABILITY_WINDOW` | portwatch | `5s` |
| `HM_KAFKA_BROKERS` | all | `redpanda:9092` |
| `HM_POSTGRES_DSN` | go services | `postgres://hm@postgres/hm` |
| `HM_ADJUDICATOR` | inspector | `fake` \| `claude` |
| `ANTHROPIC_API_KEY` | inspector | unset (required only when `claude`) |
| `HM_CONF_DISPATCH` / `HM_CONF_QUARANTINE` | inspector | `0.85` / `0.60` |
| `HM_MASK_ACCOUNTS` | all | `true` |
| `HM_OBJECT_STORE` | all | `fs` \| `s3` (s3 adapter present, unused) |
| `HM_LATE_WINDOW_DAYS` | berthmaster | `2` |

## 11. Open questions

Carried to the gate.
