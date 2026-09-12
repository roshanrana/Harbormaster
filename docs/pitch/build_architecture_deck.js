const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625
pres.author = "Roshan Rana";
pres.title = "Harbormaster — AI Systems Architecture Review";

// Palette (shared with the reference deck)
const NAVY = "14213D", INK = "1B2A41", WHITE = "FFFFFF", ICE = "DCE7F5", MINT = "2EC4B6",
  GOLD = "F2B134", MUTED = "6B7A90", CARD = "F3F6FA", LINE = "C9D3E0", CARD_D = "1C2B4F", RED = "D64550";
const HF = "Cambria", BF = "Calibri";
const ASSETS = "C:/Code-Central/harbormaster/docs/assets/";

let n = 0;
function base(title, kicker) {
  const s = pres.addSlide();
  n += 1;
  s.background = { color: WHITE };
  if (kicker) s.addText(kicker.toUpperCase(), { x: 0.5, y: 0.28, w: 6, h: 0.25, fontFace: BF, fontSize: 10, bold: true, color: MINT, charSpacing: 2, isTextBox: true, margin: 0 });
  s.addText(title, { x: 0.5, y: 0.5, w: 9, h: 0.6, fontFace: HF, fontSize: 26, bold: true, color: NAVY, isTextBox: true, margin: 0 });
  s.addText(`Harbormaster · AI Systems Architecture Review · ${n}`, { x: 0.5, y: 5.25, w: 9, h: 0.25, fontFace: BF, fontSize: 8, color: MUTED, isTextBox: true, margin: 0 });
  return s;
}
function dark(title, sub) {
  const s = pres.addSlide();
  n += 1;
  s.background = { color: NAVY };
  s.addText(title, { x: 0.6, y: 1.9, w: 8.8, h: 0.9, fontFace: HF, fontSize: 34, bold: true, color: WHITE, isTextBox: true, margin: 0 });
  if (sub) s.addText(sub, { x: 0.6, y: 2.85, w: 8.8, h: 0.6, fontFace: BF, fontSize: 15, italic: true, color: ICE, isTextBox: true, margin: 0 });
  return s;
}
function card(s, x, y, w, h, fill = CARD, line = LINE) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: line, width: 0.75 }, rectRadius: 0.06 });
}
function box(s, x, y, w, h, title, body, opt = {}) {
  const fill = opt.fill || CARD, tcol = opt.tcol || NAVY, bcol = opt.bcol || INK, line = opt.line || LINE;
  card(s, x, y, w, h, fill, line);
  s.addText(title, { x: x + 0.1, y: y + 0.06, w: w - 0.2, h: 0.28, fontFace: BF, fontSize: opt.ts || 11, bold: true, color: tcol, isTextBox: true, margin: 0 });
  if (body) s.addText(body, { x: x + 0.1, y: y + 0.34, w: w - 0.2, h: h - 0.4, fontFace: BF, fontSize: opt.bs || 8.5, color: bcol, isTextBox: true, margin: 0, valign: "top" });
}
function arrow(s, x1, y1, x2, y2, color = MUTED, w = 1.25) {
  const flipH = x2 < x1, flipV = y2 < y1;
  s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.01, h: Math.abs(y2 - y1) || 0.01, line: { color, width: w, endArrowType: "triangle" }, flipH, flipV });
}
function bullets(s, items, x, y, w, h, fs = 11, color = INK) {
  s.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1 } })), { x, y, w, h, fontFace: BF, fontSize: fs, color, isTextBox: true, margin: 0, paraSpaceAfter: 4, valign: "top" });
}
function table(s, rows, x, y, w, colW, fs = 8.5, rowH) {
  const data = rows.map((r, i) => r.map((c) => ({ text: c, options: i === 0 ? { bold: true, color: WHITE, fill: { color: NAVY }, fontSize: fs } : { fontSize: fs, color: INK } })));
  s.addTable(data, { x, y, w, colW, fontFace: BF, border: { type: "solid", pt: 0.5, color: LINE }, autoPage: false, rowH });
}
function imgFit(s, path, x, y, maxW, maxH, pw, ph) {
  const r = Math.min(maxW / pw, maxH / ph);
  const w = pw * r, h = ph * r;
  s.addImage({ path, x: x + (maxW - w) / 2, y, w, h });
  return { w, h };
}
function caption(s, text, x, y, w) {
  s.addText(text, { x, y, w, h: 0.3, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 1 Title
{
  const s = pres.addSlide(); n += 1; s.background = { color: NAVY };
  s.addText("Harbormaster", { x: 0.6, y: 1.35, w: 8, h: 0.9, fontFace: HF, fontSize: 44, bold: true, color: WHITE, isTextBox: true, margin: 0 });
  s.addText("AI Systems Architecture Review", { x: 0.6, y: 2.2, w: 8, h: 0.5, fontFace: BF, fontSize: 22, color: ICE, isTextBox: true, margin: 0 });
  s.addText("Intelligent file-arrival control for financial reconciliation — a three-tier mapping ladder, quarantine and four-eyes review, hash-chained audit", { x: 0.6, y: 2.78, w: 8.6, h: 0.6, fontFace: BF, fontSize: 13, italic: true, color: ICE, isTextBox: true, margin: 0 });
  s.addText("Ship readiness complete · 12 September 2026 · Roshan Rana, AI Systems Architect", { x: 0.6, y: 4.6, w: 8.8, h: 0.3, fontFace: BF, fontSize: 10, color: MUTED, isTextBox: true, margin: 0 });
  s.addShape(pres.shapes.OVAL, { x: 8.2, y: 1.2, w: 1.1, h: 1.1, fill: { color: MINT }, line: { color: MINT } });
  s.addText("H", { x: 8.2, y: 1.2, w: 1.1, h: 1.1, fontFace: HF, fontSize: 40, bold: true, color: NAVY, align: "center", valign: "middle", isTextBox: true, margin: 0 });
}

// ---------- 2 Executive summary
{
  const s = base("Executive summary", "Overview");
  const cols = [
    ["What it is", ["The control layer between a bank's FTP landing directory / JSON queue and its reconciliation engine: six event-driven services (Go + Python) that decide which client a file belongs to, which value date it describes, and how its columns map onto one canonical schema.", "It declines when it cannot decide, quarantines for a human, and records why."]],
    ["What it proves", ["A three-tier mapping ladder — alias dictionary, then fuzzy match, then a model — whose model dependence falls over time as confirmed mappings are cached and promoted into configuration.", "97.7% field-mapping accuracy and 80.8% resolved without a model, measured against a 214-column hand-labelled corpus by a bench harness that reproduces the same numbers on every run."]],
    ["Why it is enterprise-ready", ["Hash-chained, tamper-evident audit (an edited or deleted record is detected and the chain fails closed); quarantine with four-eyes review; masking of account numbers by default.", "20 architecture decisions, 50 task packs, twelve named adversarial fixtures, 347 tests passing offline in this run, CI running the same gate."]],
  ];
  cols.forEach((c, i) => {
    const x = 0.5 + i * 3.05;
    card(s, x, 1.3, 2.9, 3.25);
    s.addText(c[0], { x: x + 0.15, y: 1.4, w: 2.6, h: 0.35, fontFace: HF, fontSize: 15, bold: true, color: NAVY, isTextBox: true, margin: 0 });
    bullets(s, c[1], x + 0.15, 1.85, 2.6, 2.6, 10.5);
  });
  s.addText("Ask of the audience: agree the pilot scope (host-validated Docker run of make up / make test-e2e / HM_LIVE=1 make test-live, load test against the NFR-2 latency target) and whether Tier 2 embeddings (fastembed) ship enabled or degraded.", { x: 0.5, y: 4.7, w: 9, h: 0.45, fontFace: BF, fontSize: 10, italic: true, color: INK, isTextBox: true, margin: 0 });
}

// ---------- 3 Problem and users
{
  const s = base("The problem and the users", "Context");
  box(s, 0.5, 1.3, 4.3, 1.75, "The bank's problem", "Client, custodian and exchange reports land all day into one FTP directory as CSV, Excel, XML, FIXML and free-text email, plus a parallel JSON queue. Every venue names its columns differently, filenames are unreliable, and a file produced late at the client carries yesterday's business under today's date.", { bs: 10 });
  box(s, 5.2, 1.3, 4.3, 1.75, "The engine's constraint", "The downstream reconciliation engine is deliberately simple: it matches records for an expected file on each side. It has no opinion about which client, which value date, or which of four price columns is the trade price. It has to be told — correctly, or not at all.", { bs: 10 });
  table(s, [
    ["Actor", "Needs", "Frequency"],
    ["Reconciliation engine (downstream)", "One canonical Parquet schema per file, with client, value date and side already resolved", "Continuous, all day"],
    ["Four-eyes reviewer", "A specific reason for every quarantine, and the ability to correct, release or reject", "On quarantine (0% of well-formed fixtures)"],
    ["Client onboarding / ops team", "Per-client YAML config; a promoted mapping resolves at Tier 1 forever after", "As new clients or venues arrive"],
    ["Compliance / auditor", "A tamper-evident decision log that reconstructs any dispatch after the fact", "On review, or on demand"],
  ], 0.5, 3.25, 9.0, [2.6, 4.8, 1.6], 9);
}

// ---------- 4 Solution at a glance
{
  const s = base("Solution at a glance", "Approach");
  const steps = [
    ["1", "Arrival", "Portwatch detects a fully-written file or JSON payload, streams a SHA-256, and gates exact duplicates and same-content redeliveries by hash, not filename."],
    ["2", "Classify", "Inspector sniffs the format by content, attributes the client, and resolves the value date from three independent sources ranked by how much each actually knows."],
    ["3", "Map & score", "The mapping ladder resolves every column — alias, then fuzzy, then a model for the residue — and a composed confidence routes to dispatch, quarantine or reject."],
    ["4", "Berth assignment", "Berthmaster pairs both sides for the same client / domain / value date, handles the late window and supersession, and issues the assignment the recon engine consumes."],
  ];
  steps.forEach((st, i) => {
    const x = 0.5 + i * 2.3;
    card(s, x, 1.35, 2.15, 2.15, CARD_D, CARD_D);
    s.addShape(pres.shapes.OVAL, { x: x + 0.15, y: 1.5, w: 0.4, h: 0.4, fill: { color: MINT }, line: { color: MINT } });
    s.addText(st[0], { x: x + 0.15, y: 1.5, w: 0.4, h: 0.4, fontFace: BF, fontSize: 14, bold: true, color: NAVY, align: "center", valign: "middle", isTextBox: true, margin: 0 });
    s.addText(st[1], { x: x + 0.65, y: 1.52, w: 1.4, h: 0.36, fontFace: BF, fontSize: 13, bold: true, color: WHITE, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(st[2], { x: x + 0.15, y: 2.0, w: 1.85, h: 1.4, fontFace: BF, fontSize: 8.5, color: ICE, isTextBox: true, margin: 0, valign: "top" });
    if (i < 3) arrow(s, x + 2.15, 2.4, x + 2.3, 2.4, MINT, 2);
  });
  box(s, 0.5, 3.75, 4.4, 1.3, "Six services, one log", "Portwatch, Inspector, Berthmaster and Control plane over Kafka-compatible topics (Redpanda), a review queue with four-eyes decisions, and an operations console at /api/ops. Everything is replayable from offset zero.", { bs: 10 });
  box(s, 5.1, 3.75, 4.4, 1.3, "Deterministic by default", "The model tier is bound to a deterministic stand-in unless HM_ADJUDICATOR=claude and ANTHROPIC_API_KEY are set. make check and make bench run fully offline: no broker, no database, no network, no key.", { bs: 10 });
}

// ---------- 5 System context (C4 L1)
{
  const s = base("System context", "Architecture · C4 level 1");
  const actors = [["FTP landing dir", "client / custodian files"], ["Upstream queue", "JSON payloads"], ["Ops reviewer", "browser, four-eyes"], ["Recon engine", "downstream, stubbed"]];
  actors.forEach((a, i) => { box(s, 0.5, 1.3 + i * 0.85, 1.6, 0.7, a[0], a[1], { bs: 8.5 }); arrow(s, 2.1, 1.65 + i * 0.85, 2.75, 2.85, MUTED, 1); });
  card(s, 2.8, 1.3, 3.4, 3.4, "EEF6F4", MINT);
  s.addText("Harbormaster", { x: 2.95, y: 1.38, w: 3, h: 0.3, fontFace: HF, fontSize: 14, bold: true, color: NAVY, isTextBox: true, margin: 0 });
  box(s, 2.95, 1.75, 3.1, 0.75, "Ingestion", "Portwatch (Go): write-completion, hashing, dedupe, JSON ingress", { bs: 8.5 });
  box(s, 2.95, 2.6, 3.1, 1.0, "Inspector (Python)", "format sniff · attribution · value date · mapping ladder T1/T2/T3 · confidence", { bs: 8.5 });
  box(s, 2.95, 3.7, 3.1, 0.85, "Berthmaster + Control plane (Go)", "slot lifecycle · review queue · ops console /api/ops", { bs: 8.5 });
  box(s, 6.9, 1.3, 2.6, 0.75, "Redpanda (Kafka-compatible)", "8 durable topics; the event log is the audit trail", { bs: 8 });
  box(s, 6.9, 2.2, 2.6, 0.75, "Postgres 16", "read models, slot state, decision log, template cache", { bs: 8 });
  box(s, 6.9, 3.1, 2.6, 0.75, "Object store", "landed files + canonical Parquet; fs adapter default, S3 unwired", { bs: 8 });
  box(s, 6.9, 4.0, 2.6, 0.7, "Anthropic Claude (opt-in)", "Tier 3 adjudicator; deterministic fake bound by default", { bs: 8 });
  arrow(s, 6.2, 3.0, 6.9, 1.67, MUTED, 1); arrow(s, 6.2, 3.1, 6.9, 2.57, MUTED, 1); arrow(s, 6.2, 3.2, 6.9, 3.47, MUTED, 1); arrow(s, 6.2, 3.3, 6.9, 4.35, MUTED, 1);
  s.addText("Docker (Redpanda, Postgres, all six services) is host-validated: not run in this build environment (ADR-018). The gate and the bench harness never touch a network.", { x: 0.5, y: 4.85, w: 9, h: 0.35, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 6 Component architecture (C4 L2)
{
  const s = base("Component architecture", "Architecture · C4 level 2");
  const groups = [
    { t: "Portwatch (Go)", x: 0.5, items: [["scanner.go", "write-completion detection"], ["dedupe.go", "content hashing gate"], ["ingress/queue.go", "JSON ingress path"]] },
    { t: "Inspector (Python)", x: 2.85, items: [["parsers/*", "delimited · excel · xml · fixml · email"], ["attribution.py", "client scoring"], ["valuedate.py", "3-source resolution"], ["mapping/*", "tier1 · tier2 · tier3 · resolver"], ["confidence.py", "dispatch/quarantine/reject"]] },
    { t: "Berthmaster (Go)", x: 5.2, items: [["slot state machine", "expectation, late window"], ["supersession", "void + replace, ordered"], ["missing-file alerts", "unmet expectations"]] },
    { t: "Control plane (Go)", x: 7.55, items: [["web/", "html/template + HTMX board"], ["/api/ops", "operator posture"], ["review queue", "four-eyes decisions"]] },
  ];
  groups.forEach((g) => {
    card(s, g.x, 1.3, 2.15, 3.55);
    s.addText(g.t, { x: g.x + 0.1, y: 1.36, w: 2, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: NAVY, isTextBox: true, margin: 0 });
    g.items.forEach((it, i) => {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: g.x + 0.1, y: 1.72 + i * 0.62, w: 1.95, h: 0.54, fill: { color: WHITE }, line: { color: LINE, width: 0.75 }, rectRadius: 0.05 });
      s.addText(it[0], { x: g.x + 0.18, y: 1.75 + i * 0.62, w: 1.8, h: 0.24, fontFace: "Courier New", fontSize: 8.5, bold: true, color: NAVY, isTextBox: true, margin: 0 });
      s.addText(it[1], { x: g.x + 0.18, y: 1.97 + i * 0.62, w: 1.8, h: 0.26, fontFace: BF, fontSize: 8, color: INK, isTextBox: true, margin: 0 });
    });
  });
  arrow(s, 2.65, 3.1, 2.85, 3.1, MINT, 2); arrow(s, 5.0, 3.1, 5.2, 3.1, MINT, 2); arrow(s, 7.35, 3.1, 7.55, 3.1, MINT, 2);
  s.addText("Message contracts are defined once in proto/ and generated for both languages with buf; protojson on the wire keeps topics human-readable for triage.", { x: 0.5, y: 4.9, w: 9, h: 0.3, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 7 Critical flow
{
  const s = base("The arrival-to-berth-assignment pipeline", "Architecture · critical flow");
  const stages = [
    ["Detect", "write-completion + SHA-256; exact duplicate and redelivery suppressed by content hash"],
    ["Sniff & parse", "format decided by content, not extension; six parsers behind one interface"],
    ["Attribute", "client scored from filename patterns + embedded account IDs, not a priority list"],
    ["Resolve date", "filename, content and arrival time ranked; disagreement always flagged, never silent"],
    ["Map columns", "alias → fuzzy → model, one-way escalation, cached by template fingerprint"],
    ["Score", "weighted composite confidence; material fields count 3× incidental ones"],
    ["Route", "dispatch above threshold; quarantine to four-eyes; reject below the floor"],
    ["Assign berth", "both sides paired per client/domain/value-date; supersession replaces in order"],
  ];
  stages.forEach((st, i) => {
    const col = i % 4, row = Math.floor(i / 4);
    const x = 0.5 + col * 2.3, y = 1.4 + row * 1.7;
    card(s, x, y, 2.15, 1.35, row === 0 ? CARD : "EEF6F4", row === 0 ? LINE : MINT);
    s.addText(`${i + 1}. ${st[0]}`, { x: x + 0.1, y: y + 0.08, w: 1.95, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: NAVY, isTextBox: true, margin: 0 });
    s.addText(st[1], { x: x + 0.1, y: y + 0.4, w: 1.95, h: 0.9, fontFace: BF, fontSize: 8.5, color: INK, isTextBox: true, margin: 0, valign: "top" });
    if (col < 3) arrow(s, x + 2.15, y + 0.67, x + 2.3, y + 0.67, MUTED, 1.25);
  });
  arrow(s, 9.0, 2.75, 9.0, 3.1, MUTED, 1.25);
  s.addText("Every stage records why it decided what it did. Audit is a property of the architecture: each decision appends to a hash-chained log, and read models are projections rebuildable from offset zero.", { x: 0.5, y: 4.85, w: 9, h: 0.35, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 8 Core mechanism: the mapping ladder
{
  const s = base("The mapping ladder: falling model dependence", "Design · core mechanism");
  card(s, 0.5, 1.3, 4.6, 3.55, CARD_D, CARD_D);
  s.addText("Three escalating tiers, one-way", { x: 0.65, y: 1.38, w: 4.3, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: MINT, isTextBox: true, margin: 0 });
  s.addText([
    "T1  alias dictionary (µs)      160/214  74.8%",
    "T1  structural price rule       4/214    1.9%",
    "T2  fuzzy match (ms)            8/214    3.7%",
    "     client override (promoted) 1/214    0.5%",
    "T3  model, given the residue    5/214    2.3%",
    "     unresolved, declined      36/214   16.8%",
  ].join("\n"), { x: 0.65, y: 1.75, w: 4.3, h: 1.7, fontFace: "Courier New", fontSize: 9.5, color: WHITE, isTextBox: true, margin: 0, valign: "top" });
  bullets(s, [
    "Each tier sees only what the previous one declined; a column T1 resolved is never re-litigated by a model",
    "Results are cached by template fingerprint — the second file with a known layout costs nothing",
    "A reviewer can promote a confirmed T3 decision into the client's T1 dictionary; it resolves at T1 forever after",
  ], 0.65, 3.5, 4.3, 1.3, 9, ICE);
  const badges = [["Structure over vocabulary", "settlement/mark/prior-settlement repeat per instrument-day; trade price varies per row — resolved by that shape, not the header text", MINT], ["Provenance on every field", "each dispatched mapping carries a tier and non-empty evidence string; a mapping with no provenance is a defect", GOLD], ["Decline over guess", "a wrong mapping breaks reconciliation silently; unresolved becomes a review item instead", RED]];
  badges.forEach((b, i) => {
    box(s, 5.4, 1.3 + i * 1.22, 4.1, 1.12, b[0], b[1], { bs: 9, tcol: b[2] === RED ? RED : NAVY });
  });
  box(s, 5.4, 4.0, 4.1, 0.85, "Measured, not hoped", "Second file with a known layout costs zero adjudications — asserted in test_correctness_targets_across_the_corpus, not claimed in prose.", { bs: 9 });
}

// ---------- 9 Data architecture
{
  const s = base("Data architecture", "Architecture · data");
  box(s, 0.5, 1.3, 2.9, 3.55, "8 Kafka-compatible topics", "hm.arrivals.raw (Portwatch→Inspector)\nhm.arrivals.classified (30d)\nhm.arrivals.quarantined (30d)\nhm.review.decisions (30d)\nhm.berth.assigned (90d)\nhm.berth.superseded (90d)\nhm.alerts.missing (30d)\nhm.audit.decisions (compacted, infinite)\n\nPartitioned by client:domain:value_date — ordering within a slot is structural, not a runtime hope.", { bs: 8.5 });
  box(s, 3.7, 1.3, 2.75, 1.65, "Postgres 16", "Read models (arrival board, slot state), expectation state, hash-chained decision log, template mapping cache, review decisions. JSONB for variable-shape payloads.", { bs: 9 });
  box(s, 3.7, 3.1, 2.75, 1.75, "Object store", "Landed raw files + canonical Parquet output, behind an interface. Filesystem adapter is the default; an S3 adapter is implemented and unit-tested but unwired in the demo (ADR-015).", { bs: 9 });
  box(s, 6.75, 1.3, 2.75, 1.65, "Canonical output: Parquet, not CSV", "Typed and columnar; a null settlement price survives distinctly from a zero one, which the downstream engine must not confuse (ADR-006).", { bs: 9 });
  box(s, 6.75, 3.1, 2.75, 1.75, "Masking", "Account numbers masked to last-4 in logs and UI by default; account and client names stay visible. Applied in a serialisation hook, not per call site (ADR-011).", { bs: 9 });
  s.addText("Contracts are defined once in proto/ and generated for Go and Python by buf; a cross-language round-trip test is part of the offline gate.", { x: 0.5, y: 4.95, w: 9, h: 0.3, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 10 Integration / live-mode design
{
  const s = base("The model tier: opt-in, behind an interface", "Architecture · integration");
  box(s, 0.5, 1.3, 4.3, 1.7, "Off by default", "HM_ADJUDICATOR defaults to fake — a deterministic stand-in bound behind the same MappingAdjudicator interface Claude implements. A misconfigured deployment runs without a model rather than failing to start.", { bs: 9.5 });
  box(s, 5.2, 1.3, 4.3, 1.7, "Opt-in, explicit", "HM_ADJUDICATOR=claude ANTHROPIC_API_KEY=sk-... make up enables the real tier; HM_LIVE=1 make test-live is the opt-in test against the live API. Every prior phase runs against the deterministic fake.", { bs: 9.5 });
  box(s, 0.5, 3.15, 4.3, 1.7, "Bounded cost", "Escalation is one-way; results are cached by template fingerprint. The second file with a given layout is resolved from cache and costs nothing — watch HM_ADJUDICATOR=claude logs for call and token counts.", { bs: 9.5 });
  box(s, 5.2, 3.15, 4.3, 1.7, "What is and is not measured", "Offline: which columns fall through to T3, and whether the stand-in and cache behave correctly (41 columns reached T3 here; 18 adjudication calls). Live-model mapping accuracy itself is pending — it needs the real key and is marked so in metrics/headline.json.", { bs: 9.5 });
}

// ---------- 11 Design choices
{
  const s = base("Design choices and why", "Design decisions");
  table(s, [
    ["Decision", "Alternatives considered", "Why this one"],
    ["Three-tier mapping, not LLM-first (ADR-004)", "A model call per column", "1,000 files/day × 10–40 columns makes per-column LLM calls slow, non-deterministic and unbounded in cost"],
    ["Polyglot split: Go at the edges, Python in the middle (ADR-002)", "Single-language stack", "Portwatch/Berthmaster are I/O and state machines; Inspector is data shape and inference — each gets the right tool"],
    ["Protobuf as the single source of truth (ADR-003)", "Hand-written structs per language", "Two languages on one topic will drift; proto-as-source turns that into a build failure, not a production incident"],
    ["Poll the landing directory, not inotify (ADR-016)", "fsnotify / inotify watcher", "Landing dirs are NFS/SMB mounts; inotify silently misses remote-host writes exactly where it matters most"],
    ["Server-rendered HTMX, not a React SPA (ADR-012)", "React/TS/Vite front end", "No Node, no bundler, no second dependency tree, for a live board plus a review form"],
    ["fastembed (ONNX) over sentence-transformers (ADR-007)", "sentence-transformers + PyTorch", "~90 MB CPU-only image instead of ~2 GB; degrades to fuzzy-only if unavailable, and says so"],
    ["Topics provisioned by infrastructure, not the app (ADR-020)", "Broker auto-create topics", "A typo in a topic constant now fails loudly instead of silently stranding messages in a new topic"],
  ], 0.5, 1.3, 9.0, [2.7, 2.5, 3.8], 8.5);
}

// ---------- 12 Major features
{
  const s = base("Major features", "Product");
  const feats = [
    ["The mapping ladder", "Alias dictionary → fuzzy/embedding match → model adjudication for the residue, with provenance on every field and promotion into client config"],
    ["Value-date resolution", "Three independent sources ranked by what they know, resolved against per-client business calendars; disagreements always flagged"],
    ["Quarantine & four-eyes review", "Composite confidence routes to dispatch, quarantine or reject; no quarantined arrival ships without a recorded human decision"],
    ["Hash-chained audit", "Every classification and dispatch decision appends to a tamper-evident chain; a verifier walks it and reports the first break"],
    ["Slot lifecycle & supersession", "Expectation state machine per client/domain/value-date, a T±2 late window, and ordered void-then-replace on correction"],
    ["Operations console", "Embedded Go templates + HTMX over Postgres read models, projected from the topics; /api/ops for whoever is on call"],
  ];
  feats.forEach((f, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    box(s, 0.5 + col * 3.05, 1.3 + row * 1.75, 2.9, 1.55, f[0], f[1], { bs: 9 });
  });
}

// ---------- 13-16 Screenshots
{
  const s = base("The offline gate, green", "Screenshots · terminal (this run)");
  imgFit(s, ASSETS + "01-gate-green.png", 0.5, 1.25, 9.0, 3.55, 763, 665);
  caption(s, "go vet, ruff, mypy --strict, go test, and both pytest suites run in this task: 347 passed, 0 failed, 52 skipped (need a live Postgres). proto-check needs protoc/buf, absent on this host (pre-existing, not fixed here).", 0.5, 4.9, 9);
}
{
  const s = base("The bench reproduces every published number", "Screenshots · terminal (this run)");
  imgFit(s, ASSETS + "02-bench-run.png", 0.5, 1.25, 9.0, 3.1, 985, 336);
  caption(s, "python bench/onboard.py, run in this task, wrote metrics/headline.json byte-for-byte identical to the committed file — the README's 97.7% / 80.8% / 100.0% / 66.7% figures are reproducible, not asserted.", 0.5, 4.6, 9);
}
{
  const s = base("The mapping ladder deciding, and quarantine holding", "Screenshots · terminal (this run)");
  imgFit(s, ASSETS + "03-mapping-ladder.png", 0.5, 1.2, 9.0, 3.7, 948, 749);
  caption(s, "A small script run against the real Inspector for this task: four price columns disambiguated by structure, and the one deliberately unattributable fixture held in the four-eyes queue with its exact reasons.", 0.5, 4.95, 9);
}
{
  const s = base("The generated metrics card", "Screenshots · generated report");
  imgFit(s, ASSETS + "04-metrics-card.png", 1.4, 1.3, 7.2, 3.45, 960, 588);
  caption(s, "metrics/render.py renders this card from metrics/headline.json into docs/assets/metrics.svg and the README results block, so the deck, the README and the bench output cannot drift apart.", 0.5, 4.9, 9);
}

// ---------- 17 Security and compliance
{
  const s = base("Security and compliance controls", "Enterprise readiness · controls");
  table(s, [
    ["Boundary", "Threat", "Control in the code", "Evidence"],
    ["B1 landing directory", "malformed/oversized files, format confusion", "content-based sniffing, not extension; streaming hash; per-format parsers behind one interface", "arrival + parser tests"],
    ["B2 model tier (Claude)", "key leakage; unbounded cost; wrong mapping accepted", "key from env only; one-way escalation; cache by template; structured-output validated against canonical schema", "T3/resolver tests, ADR-004"],
    ["B3 operations console", "no authentication in the prototype", "explicitly out of scope by requirements §7; designed to sit behind the institution's SSO", "ship report §5, item 7"],
    ["B4 audit log", "tampering, deletion, silent edit", "SHA-256 hash chain per arrival; a verifier walks every chain and reports the first break; fails closed", "internal/audit tests, bench tamper check"],
    ["B5 logs and UI", "account numbers or client identifiers leaking", "numbers masked to last-4 by default in a serialisation hook; names stay visible for operability (ADR-011)", "masking + parity tests, Go & Python"],
  ], 0.5, 1.3, 9.0, [1.5, 2.1, 3.4, 2.0], 8);
  s.addText("Residual risks, written down rather than hidden: no console authentication (by design, pre-SSO), no leader election on the overdue sweep, throughput designed for but not load-tested.", { x: 0.5, y: 4.55, w: 9, h: 0.45, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 18 Enterprise readiness: process
{
  const s = base("How it was built: a gated, evidence-producing lifecycle", "Enterprise readiness · process");
  const gates = ["G brief", "M0 skeleton", "M1 ingest", "M2 parsers", "M3 intel.", "M4 slots", "M5 audit", "M6 UI", "M7 corpus", "M8 model", "M9 ship"];
  gates.forEach((g, i) => {
    const x = 0.5 + i * 0.845;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.35, w: 0.78, h: 0.62, fill: { color: i < 9 ? CARD_D : "1E5C57" }, line: { color: i < 9 ? CARD_D : "1E5C57" }, rectRadius: 0.05 });
    s.addText(g, { x: x + 0.02, y: 1.37, w: 0.74, h: 0.58, fontFace: BF, fontSize: 7, bold: true, color: WHITE, align: "center", valign: "middle", isTextBox: true, margin: 0 });
  });
  const stats = [["50", "task packs, each with scope, acceptance criteria and a validation command"], ["20", "architecture decisions, each with context, consequences and cost"], ["12", "named adversarial fixtures, each with its own scenario test"], ["347", "tests passing offline in this run: 0 failed, 52 skipped pending a live Postgres"]];
  stats.forEach((st, i) => {
    const x = 0.5 + i * 2.3;
    card(s, x, 2.2, 2.15, 1.25);
    s.addText(st[0], { x: x + 0.12, y: 2.25, w: 1.9, h: 0.5, fontFace: HF, fontSize: 28, bold: true, color: GOLD, isTextBox: true, margin: 0 });
    s.addText(st[1], { x: x + 0.12, y: 2.75, w: 1.9, h: 0.65, fontFace: BF, fontSize: 8.5, color: INK, isTextBox: true, margin: 0, valign: "top" });
  });
  box(s, 0.5, 3.65, 4.4, 1.25, "Split by what the build host can run", "Every task is marked validated-here or validate-on-host (ADR-018). Docker (Compose, Redpanda, the six-service stack) is absent from the build environment, so end-to-end and live-model gates are authored to spec and run on a host with Docker.", { bs: 9 });
  box(s, 5.1, 3.65, 4.4, 1.25, "One command validates the rest", "gofmt · go vet · golangci-lint · ruff · mypy --strict · buf lint + codegen staleness · a cross-language contract test · every unit, property and scenario test. CI runs the same make check target verbatim.", { bs: 9 });
}

// ---------- 19 Quality metrics (native chart)
{
  const s = base("Quality metrics from the bench and the gate", "Enterprise readiness · measurement");
  s.addChart(pres.charts.BAR, [{ name: "Value", labels: ["Field-mapping accuracy", "Resolved w/o a model", "Quarantine precision", "Quarantine recall", "Tests passing (÷400)"], values: [0.977, 0.808, 1.0, 0.667, 0.87] }], {
    x: 0.5, y: 1.3, w: 5.2, h: 3.5, barDir: "bar", chartColors: [MINT], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", dataLabelFontSize: 9, dataLabelColor: INK,
    catAxisLabelColor: INK, catAxisLabelFontSize: 9, valAxisLabelColor: MUTED, valAxisLabelFontSize: 8, valAxisMinVal: 0, valAxisMaxVal: 1.1, valGridLine: { color: LINE, size: 0.5 }, catGridLine: { style: "none" }, showLegend: false, showTitle: true, title: "Ratios (1.0 = target met)", titleFontSize: 10, titleColor: NAVY,
  });
  table(s, [
    ["KPI", "Value", "Target"],
    ["Field-mapping accuracy", "97.7% (209/214 columns, 19 files)", "n/a, headline"],
    ["Resolved without a model", "80.8% (173/214)", "n/a, headline"],
    ["Columns escalated to Tier 3", "41 (18 adjudication calls)", "≤2% once warm (NFR-8)"],
    ["Quarantine precision / recall", "100.0% / 66.7%", "n/a; recall is an honest miss"],
    ["Hash-chain tamper check", "detected, fail-closed", "must fail closed"],
    ["Tests today (this run)", "347 passed / 399 collected, 0 failed", "offline, no network"],
    ["make check (minus proto-check)", "green in this run", "green offline"],
  ], 5.9, 1.3, 3.6, [1.9, 1.1, 0.6], 7.5);
  s.addText("Quarantine recall (66.7%) is shown as measured, not smoothed: one of three files that should have been held slipped through in this corpus — see Quirks. Tier-3 escalation count is against a deterministic stand-in, not a live model.", { x: 0.5, y: 4.9, w: 9, h: 0.35, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 20 Quirks and limitations
{
  const s = base("Quirks and known limitations (stated, not hidden)", "Honesty");
  const q = [
    ["Quarantine recall is 66.7%, not 100%", "1 of 3 files that should have been held was not, in the fixed reference corpus. Precision is 100% (nothing held needlessly) but recall is the honest miss; mitigation is a lower quarantine threshold or an added evidence source, not yet done."],
    ["Tier 2 embeddings are optional and untested against a real model here", "fastembed is not installed in this environment, so the suite exercises the fuzzy-only degraded path; the degradation is recorded in the evidence string, never silent."],
    ["Live model accuracy is not measured offline", "The Tier 3 numbers above are against the deterministic stand-in. HM_LIVE=1 make test-live against the real Claude API is written but not run in this environment."],
    ["Docker-dependent gates are host-validated, not run here", "make up, make test-e2e, make demo and make verify-audit need Redpanda/Postgres/the six-service stack; ADR-018 marks every such task validate-on-host rather than claiming it done."],
    ["No authentication on the operations console", "Out of scope by requirements §7; intended to sit behind the institution's existing SSO for a pilot."],
    ["The overdue sweep is not leader-elected", "Running more than one Berthmaster instance would run the sweep more than once per interval. Slot state itself is safe across instances."],
    ["Throughput and p95 latency (NFR-2) are designed for, not measured", "The 1,000 arrivals/day envelope has no load test behind it in this environment."],
    ["golangci-lint and protoc/buf are not installed on this host", "go vet substituted for lint; proto-check could not run. Pre-existing gaps in this environment, not fixed as part of this task."],
  ];
  q.forEach((it, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    box(s, 0.5 + col * 4.6, 1.3 + row * 0.9, 4.45, 0.82, it[0], it[1], { bs: 7.8, ts: 9.5 });
  });
}

// ---------- 21 Cost and performance
{
  const s = base("Cost, performance and operability", "Enterprise readiness · operations");
  const cards = [["µs / ms / s+$", "the three tiers' cost, in order — most columns resolve for free"], ["0 keys", "needed for make check or make bench; the model tier is opt-in only"], ["~4.8s", "python/tests (257 passed) in this run; go test ./... a few seconds more"], ["0 → next time", "template-fingerprint cache: the second file with a known layout costs no model call"]];
  cards.forEach((c, i) => {
    const x = 0.5 + i * 2.3;
    card(s, x, 1.3, 2.15, 1.35);
    s.addText(c[0], { x: x + 0.12, y: 1.35, w: 1.9, h: 0.5, fontFace: HF, fontSize: 22, bold: true, color: GOLD, isTextBox: true, margin: 0 });
    s.addText(c[1], { x: x + 0.12, y: 1.87, w: 1.9, h: 0.75, fontFace: BF, fontSize: 8.5, color: INK, isTextBox: true, margin: 0, valign: "top" });
  });
  box(s, 0.5, 2.85, 4.4, 2.0, "Operability", "• Runbook: first checkout, running the stack, seeing it work, verifying the audit trail, configuration reference, what to do when something is wrong\n• make up targets healthy in under a minute (host-validated)\n• make demo narrates the twelve adversarial fixtures through the live board\n• Rollback: read models are projections, rebuilt by replaying topics from offset zero", { bs: 9 });
  box(s, 5.1, 2.85, 4.4, 2.0, "Observability and audit", "• Structured JSON logs with correlation IDs (slog / structlog); no metrics stack by design (ADR-014)\n• Hash-chained audit.decisions topic, compacted and retained indefinitely\n• make verify-audit walks every chain and names the first break\n• Client YAML is schema-validated strictly at load: an unknown key fails loudly, never at 3 a.m.", { bs: 9 });
}

// ---------- 22 Roadmap
{
  const s = base("Roadmap to production validation", "Next steps");
  const phases = [["Now", "Host validation", ["go mod tidy; make up && make test-e2e on a machine with Docker", "HM_LIVE=1 make test-live against the real Claude API", "Confirm the 60s p95 / 180s p99 latency targets (NFR-2)"]], ["Near term", "Close the recall gap", ["Investigate the missed quarantine case; consider a lower threshold or an added evidence source", "Install fastembed and re-measure Tier 2 with real embeddings, not fuzzy-only"]], ["Before pilot", "Operational hardening", ["Leader-elect the Berthmaster overdue sweep for multi-instance runs", "SSO in front of the operations console", "Load test the 1,000 arrivals/day envelope and the burst target"]], ["Scale", "Beyond the prototype", ["Wire the already-implemented S3 object-store adapter", "Extend the client dictionary from pilot-onboarding promotions", "Revisit Redpanda vs. managed Kafka for production topology"]]];
  phases.forEach((p, i) => {
    const x = 0.5 + i * 2.3;
    card(s, x, 1.3, 2.15, 3.5, i === 0 ? "EEF6F4" : CARD, i === 0 ? MINT : LINE);
    s.addText(p[0], { x: x + 0.12, y: 1.36, w: 1.9, h: 0.28, fontFace: BF, fontSize: 9, bold: true, color: MINT, charSpacing: 1, isTextBox: true, margin: 0 });
    s.addText(p[1], { x: x + 0.12, y: 1.62, w: 1.9, h: 0.35, fontFace: HF, fontSize: 13, bold: true, color: NAVY, isTextBox: true, margin: 0 });
    bullets(s, p[2], x + 0.12, 2.05, 1.9, 2.7, 8.5);
  });
  s.addText("Every item above is additive: the contracts, the ladder, the confidence scoring and the audit chain do not change.", { x: 0.5, y: 4.95, w: 9, h: 0.3, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 23 Appendix: decision log
{
  const s = base("Appendix A — Decision log (abridged, 20 total)", "Appendix");
  table(s, [
    ["ID", "Decision", "Consequence"],
    ["ADR-001", "Event-driven log backbone (Kafka-compatible) over batch or sync calls", "Replay is an offset operation; the log is the audit trail"],
    ["ADR-002", "Polyglot split: Go at the edges, Python in the middle", "Each language fits its workload; a hard requirement for shared contracts"],
    ["ADR-003", "Protobuf single source of truth, buf-generated, protojson on the wire", "Contract drift becomes a build failure, not a production incident"],
    ["ADR-004", "Three-tier field mapping, not LLM-first", "Model dependence decreases over time; NFR-8 (≤2% once warm) achievable"],
    ["ADR-006", "Parquet for canonical output, not CSV", "Nulls and types survive; a missing price is never confused with zero"],
    ["ADR-011", "Masking: numbers masked to last-4, names visible", "Boards and screenshots stay safe without hiding who a client is"],
    ["ADR-016", "Poll the landing directory, not inotify", "Correct on the NFS/SMB mounts this actually runs on"],
    ["ADR-018", "Split validation between build and host environments", "No task marked done on unexecuted code; the gap is visible, not implied"],
    ["ADR-020", "Topics provisioned by infrastructure, not the application", "A topic typo fails loudly instead of silently stranding messages"],
  ], 0.5, 1.3, 9.0, [1.0, 4.2, 3.8], 8);
}

// ---------- 24 Appendix: process stats and lessons
{
  const s = base("Appendix B — Build statistics and defects found", "Appendix");
  table(s, [
    ["Measure", "Count"],
    ["Go source", "4,991 lines across 12 packages and 3 binaries"],
    ["Python source", "6,295 lines"],
    ["Go tests", "73 passed, 47 skipped without a live Postgres, in this run"],
    ["Python tests", "257 passed / 262 collected (tests/), 17/17 (scenarios), in this run"],
    ["Documentation", "2,877 lines across requirements, HLD, LLD, ADRs, runbook, ship report"],
    ["Task packs / ADRs", "50 task packs; 20 architecture decisions"],
  ], 0.5, 1.3, 9.0, [3.2, 5.8], 9);
  box(s, 0.5, 3.35, 9.0, 1.55, "Defects found and fixed during construction (from the ship report)", "• Audit hashes recomputed differently on read: Postgres stores microseconds, Go carries nanoseconds — every chain would have failed verification\n• inputs/outcome stored as JSONB normalised key order, so hashed bytes did not match stored bytes — changed to TEXT\n• A description column full of commas beat the real pipe delimiter in the delimiter scorer\n• bv or \"\" in the recon stub made a genuine zero indistinguishable from null (Decimal(\"0\") is falsy)\n• Masking revealed short account numbers in full: \"last four\" of a four-character value is all of it", { bs: 8.5 });
}

// ---------- 25 Appendix: repository map
{
  const s = base("Appendix C — Repository map and how to run", "Appendix");
  s.addText(["go/              portwatch, berthmaster, controlplane, auditcheck,", "                 internal/{arrival,audit,bus,contract,ingress,", "                 logging,masking,registry,slot,store,web}", "python/          inspector (parsers, mapping, valuedate,", "                 attribution, confidence), corpus, reconstub", "proto/           harbormaster.proto — single source of truth", "config/          clients/*.yaml, calendars/*.yaml", "bench/           onboard.py, golden/ — the fixed labelled corpus", "metrics/         headline.json, card.json, render.py (drift-checked)", "tests/scenarios/ the twelve adversarial fixtures, one test each", "docs/design/     requirements, HLD, LLD, execution plan, 20 ADRs", "docs/tasks/      50 task packs", "docs/pitch/      this deck"].join("\n"), { x: 0.5, y: 1.3, w: 5.6, h: 3.3, fontFace: "Courier New", fontSize: 7.5, color: INK, isTextBox: true, margin: 0, valign: "top" });
  card(s, 6.3, 1.3, 3.2, 3.55, CARD_D, CARD_D);
  s.addText("Run it", { x: 6.45, y: 1.38, w: 3, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: MINT, isTextBox: true, margin: 0 });
  s.addText(["cd go && go mod tidy", "cd .. && make check", "make bench && make card", "make test-scenarios", "", "# with Docker (host-validated)", "make up", "make demo", "make verify-audit", "", "# the live model tier", "export HM_ADJUDICATOR=claude", "export ANTHROPIC_API_KEY=sk-...", "HM_LIVE=1 make test-live"].join("\n"), { x: 6.45, y: 1.72, w: 3, h: 3.05, fontFace: "Courier New", fontSize: 8.5, color: WHITE, isTextBox: true, margin: 0, valign: "top" });
}

// ---------- 26 Close
{
  const s = dark("Questions", "Harbormaster · roshanrana/harbormaster · design docs, decision log and runbook in the repository");
}

pres.writeFile({ fileName: "C:/Code-Central/harbormaster/docs/pitch/harbormaster-architecture-deck.pptx" }).then((f) => console.log("wrote", f, "slides", n));
