-- Arrivals. One row per detected file or queue payload.
-- The uniqueness constraint is on (content_sha256, original_name) rather than
-- content_sha256 alone: the same content redelivered under a new filename is a
-- distinct operational event worth recording (FR-7), even though it must not
-- produce a second downstream instruction.
CREATE TABLE IF NOT EXISTS arrival (
    arrival_id      TEXT PRIMARY KEY,
    content_sha256  TEXT        NOT NULL,
    original_name   TEXT        NOT NULL,
    ingress         TEXT        NOT NULL,
    uri             TEXT        NOT NULL,
    size_bytes      BIGINT      NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL,
    disposition     TEXT,
    classification  JSONB,
    CONSTRAINT arrival_content_name_uniq UNIQUE (content_sha256, original_name)
);

-- Dedupe lookup is the hot path in Portwatch: every arrival hits it once.
CREATE INDEX IF NOT EXISTS arrival_sha_idx ON arrival (content_sha256);
CREATE INDEX IF NOT EXISTS arrival_detected_idx ON arrival (detected_at DESC);

-- Reconciliation slots. The primary key IS the slot identity, which is the
-- same tuple used as the Kafka partition key (ADR-005).
CREATE TABLE IF NOT EXISTS slot (
    client_id       TEXT        NOT NULL,
    domain          TEXT        NOT NULL,
    value_date      DATE        NOT NULL,
    state           TEXT        NOT NULL,
    expectation_id  TEXT        NOT NULL,
    side_1_arrival  TEXT,
    side_2_arrival  TEXT,
    assignment_id   TEXT,
    opened_at       TIMESTAMPTZ NOT NULL,
    deadline        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (client_id, domain, value_date)
);

-- Berthmaster sweeps for slots past their deadline; this index is what keeps
-- that sweep from becoming a full scan as history accumulates.
CREATE INDEX IF NOT EXISTS slot_deadline_idx ON slot (state, deadline);

-- Tamper-evident decision log. Per-arrival hash chain (LLD 2.7).
CREATE TABLE IF NOT EXISTS audit_record (
    record_id     TEXT PRIMARY KEY,
    arrival_id    TEXT        NOT NULL,
    at            TIMESTAMPTZ NOT NULL,
    component     TEXT        NOT NULL,
    decision_type TEXT        NOT NULL,
    -- TEXT rather than JSONB on purpose. The record hash covers these exact
    -- bytes; JSONB normalises key order and whitespace on storage, so reading
    -- one back would produce a different string and a spurious chain break.
    -- Queryability is not worth a verifier that cries wolf.
    inputs        TEXT        NOT NULL DEFAULT '{}',
    outcome       TEXT        NOT NULL DEFAULT '{}',
    actor         TEXT        NOT NULL DEFAULT 'system',
    prev_hash     TEXT        NOT NULL DEFAULT '',
    record_hash   TEXT        NOT NULL
);

-- Chain verification walks one arrival in time order, so the index matches.
CREATE INDEX IF NOT EXISTS audit_arrival_idx ON audit_record (arrival_id, at);

-- Learned field mappings, keyed by template fingerprint. This table is what
-- keeps the model tier at the 2 percent target (NFR-8): the second file with a
-- given layout costs nothing.
CREATE TABLE IF NOT EXISTS template_mapping (
    template_fingerprint TEXT        NOT NULL,
    client_id            TEXT        NOT NULL,
    mappings             JSONB       NOT NULL,
    tier                 TEXT        NOT NULL,
    confirmed_by         TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (template_fingerprint, client_id)
);

-- Four-eyes review decisions. One decision per arrival; a second reviewer
-- acting on the same arrival is a conflict we want the database to reject.
CREATE TABLE IF NOT EXISTS review (
    arrival_id  TEXT PRIMARY KEY,
    reviewer    TEXT        NOT NULL,
    decision    TEXT        NOT NULL,
    corrections JSONB,
    decided_at  TIMESTAMPTZ NOT NULL
);
