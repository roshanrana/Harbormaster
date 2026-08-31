# Harbormaster — Requirements

**Status:** Phase 0 draft, awaiting sign-off
**Last updated:** 2026-08-30

---

## 1. Problem statement

A tier-1 financial institution reconciles trades, positions, cash and collateral
against its general ledger. The internal side (Side 1) is well-controlled. The
external side (Side 2) is not: client, custodian and exchange reports arrive all
day into a single FTP landing directory as CSV, Excel, XML, FIXML and free-text
email bodies, with a parallel stream of JSON messages arriving on a queue from
upstream integrations. Layouts differ per counterparty and per venue (ICE, CME,
CBOE, LSEG, EUREX, NYSE, HKEX, Nasdaq). Filenames are unreliable. A file
produced late at the client carries yesterday's business content under today's
date stamp.

The existing reconciliation engine is deliberately simple. It is configured with
an expected file on each side and it matches records. It cannot determine which
value date a file's contents belong to, which client produced it, or which column
in a twelve-column price block is the trade price versus the settlement price. It
must be told.

Harbormaster is the intelligent front door that tells it. Files land at the port,
Harbormaster identifies the vessel and its cargo, determines the tide it sailed
on, and issues a berth assignment that the reconciliation engine consumes.

## 2. Scope

Harbormaster is responsible for everything between *a file appearing* and *a
reconciliation instruction being issued*. It does not perform reconciliation.

```
FTP drop ─┐
          ├─► Harbormaster ─► berth assignment (client + value date + file pair)
JSON queue ┘                        │
                                    └─► reconciliation engine (out of scope, stubbed)
```

## 3. Functional requirements

### 3.1 Ingestion

| ID | Requirement |
|---|---|
| FR-1 | Continuously watch one or more FTP landing directories and detect new files. |
| FR-2 | Emit an arrival event only once a file is **fully written**. Partial-write detection must not rely on the writer creating a sentinel file, though a sentinel must be honoured when present. |
| FR-3 | Consume a second ingress stream of JSON payloads from an external queue and treat each payload as an arrival equivalent to a file. |
| FR-4 | Compute a content hash for every arrival and record it. |
| FR-5 | Operate continuously. There is no nightly batch window; arrivals are expected at any hour including outside the local business day. |

### 3.2 Duplicate and correction handling

| ID | Requirement |
|---|---|
| FR-6 | **Exact duplicate** (identical content hash, previously seen): suppress reprocessing, record the suppression with a reference to the original arrival, do not emit a downstream instruction. |
| FR-7 | **Redelivery under a different filename** with identical content must be recognised as FR-6, not as a new file. |
| FR-8 | **Correction / amendment** (same client, same product domain, same value date, different content hash): treat as superseding the earlier arrival. Emit a supersession event carrying both arrival identifiers. |
| FR-9 | If a superseded arrival has already been dispatched for reconciliation, the supersession event must mark the prior berth assignment void and issue a replacement. |
| FR-10 | Distinguish a correction from a legitimate second file of the same type for the same date (for example an intraday and an end-of-day cut) using the client configuration, not guesswork. |

### 3.3 Late arrival and value-date resolution

| ID | Requirement |
|---|---|
| FR-11 | Derive candidate value dates from three independent sources: the filename, the file content (explicit date fields), and the arrival timestamp. |
| FR-12 | Content-derived dates take precedence over filename-derived dates. A disagreement between them must be recorded and flagged, never silently resolved. |
| FR-13 | Resolve value date against a per-client business calendar (weekends, venue holidays, settlement conventions) rather than naive calendar arithmetic. |
| FR-14 | A file landing on day D whose contents belong to D-1 or earlier must be routed to the correct historical reconciliation slot. |
| FR-15 | Reconciliation slots for a given client, domain and value date remain open for a configurable number of business days to accept late arrivals. |
| FR-16 | A single file containing rows spanning multiple value dates must be split into per-date sub-batches, each dispatched independently. |

### 3.4 Classification

| ID | Requirement |
|---|---|
| FR-17 | Determine file format by **content inspection**, not file extension. |
| FR-18 | Identify the owning client from filename patterns, embedded account identifiers, and source hints, producing a confidence score. |
| FR-19 | Extract all account identifiers present and validate them against the client configuration. |
| FR-20 | Classify the product domain of the contents: trade, position, cash, collateral. |
| FR-21 | Identify the originating venue or source system where determinable. |

### 3.5 Semantic field mapping

| ID | Requirement |
|---|---|
| FR-22 | Map every source column, XML path or FIX tag onto a single canonical record schema, so that the downstream engine sees one layout regardless of origin. |
| FR-23 | Resolve mappings through an escalating strategy: deterministic alias dictionary first, local similarity matching second, language-model adjudication only for the residue. |
| FR-24 | Record the resolution tier and confidence for **every** field decision. A mapping with no recorded provenance is a defect. |
| FR-25 | Correctly disambiguate multiple price columns in one record, in particular trade price versus settlement/mark price, and never conflate them. |
| FR-26 | Correctly identify which fields carry quantity, gross amount, net amount and market value, including where a client uses a bare or ambiguous header. |
| FR-27 | Cache mapping decisions per client template so a recurring layout does not incur repeated model cost. |
| FR-28 | Where a mapping is learned by model adjudication, promote it into the deterministic dictionary for that client after human confirmation. |

### 3.6 Confidence, quarantine and human review

| ID | Requirement |
|---|---|
| FR-29 | Produce an overall confidence score per arrival, composed from client, value-date and field-mapping confidences. |
| FR-30 | Auto-dispatch above a configurable high threshold; route to quarantine between thresholds; reject below the low threshold. |
| FR-31 | Quarantined arrivals enter a four-eyes review queue. A reviewer's decision releases, corrects or rejects the arrival. |
| FR-32 | No quarantined arrival is ever dispatched without a recorded human decision. |

### 3.7 Dispatch

| ID | Requirement |
|---|---|
| FR-33 | Maintain a per-client YAML configuration declaring expected files, their product domain, their reconciliation side, cadence, filename hints, account identifiers, calendar and late-arrival tolerance. |
| FR-34 | Emit a berth assignment only when both configured sides are present for the same client, domain and value date. |
| FR-35 | Where one side is missing beyond its expected cadence, raise a missing-file alert naming the specific expectation that is unmet. |
| FR-36 | Write every berth assignment to both the message queue and an append-only log file. |

### 3.8 Audit, security and observability

| ID | Requirement |
|---|---|
| FR-37 | Maintain an append-only, tamper-evident decision log capturing every classification and dispatch decision with its inputs and confidence. |
| FR-38 | Mask account numbers and client identifiers in all operational logs and in the UI by default; unmasked values require an explicit privilege. |
| FR-39 | Any decision must be fully reconstructable after the fact from the decision log alone. |
| FR-40 | Every event stream must be replayable from a given offset without side-effect duplication. |
| FR-41 | Provide a web interface showing arrivals, resolved client and value date, confidence breakdown, quarantine queue and issued berth assignments. |
| FR-42 | The review actions in FR-31 are performable from that interface. |

## 4. Non-functional requirements

| ID | Category | Target |
|---|---|---|
| NFR-1 | Throughput | 1,000 arrivals per day sustained; burst of 100 arrivals in a 5-minute window without backlog growth. |
| NFR-2 | Latency | p95 arrival-to-classified under 60 seconds for files up to 250k rows; p99 under 180 seconds. |
| NFR-3 | Availability | Ingestion tolerates restart at any point with no lost or double-processed arrival. |
| NFR-4 | Correctness — client | ≥ 99% correct client attribution on the reference corpus. |
| NFR-5 | Correctness — value date | ≥ 98% correct value date auto-resolved; 100% of filename/content disagreements flagged. |
| NFR-6 | Correctness — mapping | 100% of dispatched records have every economically material field mapped with recorded provenance. |
| NFR-7 | Quarantine rate | ≤ 5% of arrivals on the reference corpus. |
| NFR-8 | Model cost control | ≤ 2% of arrivals reach the language-model tier once template caches are warm. |
| NFR-9 | Idempotency | Reprocessing the same content hash produces no additional downstream instruction. |
| NFR-10 | Auditability | Every dispatched instruction traceable to its arrival, its field decisions and, where applicable, its reviewer. |
| NFR-11 | Operability | Full stack starts with a single command on a developer machine and seeds a working demo. |
| NFR-12 | Testability | Deterministic offline test run with no external network dependency. |

## 5. Constraints

| ID | Constraint |
|---|---|
| C-1 | Docker is available on the development machine and is the preferred demo vehicle. |
| C-2 | Go is to be used where it is the better fit, particularly for I/O-bound, long-running daemon components. Language selection per component is justified in the HLD. |
| C-3 | The language-model tier calls the real Anthropic API. Live calls are exercised at the end of the build; all prior phases run against a deterministic stand-in behind the same interface. |
| C-4 | The reconciliation engine is stubbed. Harbormaster's output contract is the boundary. |
| C-5 | Built and run locally first. Repository publication is a later, separate activity. |
| C-6 | Documentation states design rationale and trade-offs on its own merits. |

## 6. Assumptions

- A-1 Client configuration is authored by an operations team and treated as externally owned input; Harbormaster consumes it and validates it but does not own its lifecycle.
- A-2 The FTP landing directory is a shared mount reachable by the ingestion component.
- A-3 Venue and client sample data is synthetic but modelled on real report structures and conventions.
- A-4 Business calendars are supplied as configuration; no market-data vendor integration.
- A-5 Side 1 (internal GL extract) arrives through the same landing directory as a well-formed file.

## 7. Out of scope

- PDF and scanned-document ingestion, and any OCR pipeline.
- The reconciliation matching logic itself, break classification, and break workflow.
- FIX session layer. FIXML **files** are parsed; no session is initiated or maintained.
- Production deployment, cluster operations, HA topology, DR.
- Enterprise SSO, credential vaulting, HSM-backed key management.
- Multi-tenant authorisation beyond the masking privilege in FR-38.
- Real market data, real client data, or connectivity to any live venue.
- Automated remediation of breaks.

## 8. Reference corpus

Correctness targets are measured against a committed synthetic corpus that must
include, at minimum:

- All six in-scope formats.
- At least six distinct client configurations across at least five venues.
- A late-arrival case: file landing D+1 containing D-1 business content.
- A filename/content date disagreement.
- An exact duplicate and a same-content/different-filename redelivery.
- A correction superseding an already-dispatched file.
- A multi-date file requiring split.
- A record carrying four or more price columns including trade and settlement.
- A free-text email body containing a cash movement.
- A bare-header file where a price column is labelled only `Price`.
- A file whose client cannot be determined, to exercise quarantine.

## 9. Open questions

Carried to the Phase 0 gate. See the accompanying summary.
