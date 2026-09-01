-- Read models for the operations board.
--
-- These are projections, not sources of truth. The event log is authoritative;
-- everything here can be rebuilt by replaying topics from offset zero, which is
-- why every write is an upsert keyed on an identifier the producer owns.

-- Berth assignments issued to the reconciliation engine.
CREATE TABLE IF NOT EXISTS assignment (
    assignment_id  TEXT PRIMARY KEY,
    client_id      TEXT        NOT NULL,
    domain         TEXT        NOT NULL,
    value_date     DATE        NOT NULL,
    side_1_arrival TEXT,
    side_2_arrival TEXT,
    expectation_id TEXT        NOT NULL,
    confidence     DOUBLE PRECISION NOT NULL DEFAULT 0,
    supersedes     TEXT,
    notes          TEXT        NOT NULL DEFAULT '',
    emitted_at     TIMESTAMPTZ NOT NULL,
    -- Set when a correction voids this assignment. Kept rather than deleted:
    -- "this reconciliation was run and then withdrawn" is a fact an auditor
    -- will ask about, and a deleted row cannot answer.
    voided_at      TIMESTAMPTZ,
    voided_by      TEXT
);

CREATE INDEX IF NOT EXISTS assignment_slot_idx ON assignment (client_id, domain, value_date);
CREATE INDEX IF NOT EXISTS assignment_emitted_idx ON assignment (emitted_at DESC);

-- Missing-file alerts.
CREATE TABLE IF NOT EXISTS alert (
    id             TEXT PRIMARY KEY,
    client_id      TEXT        NOT NULL,
    domain         TEXT        NOT NULL,
    value_date     DATE        NOT NULL,
    expectation_id TEXT        NOT NULL,
    missing_side   TEXT        NOT NULL,
    deadline       TIMESTAMPTZ NOT NULL,
    emitted_at     TIMESTAMPTZ NOT NULL,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT
);

CREATE INDEX IF NOT EXISTS alert_open_idx ON alert (acknowledged_at, emitted_at DESC);

-- Consumer offsets for the projector, so a restart resumes rather than
-- reprocessing from the beginning. Projections are idempotent either way, but
-- replaying 90 days of assignments on every restart is a poor default.
CREATE TABLE IF NOT EXISTS projection_offset (
    consumer   TEXT NOT NULL,
    topic      TEXT NOT NULL,
    partition  INT  NOT NULL,
    next_offset BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer, topic, partition)
);

-- Arrivals need a few projected columns the raw table does not carry, so the
-- board can filter without parsing JSONB on every request.
ALTER TABLE arrival ADD COLUMN IF NOT EXISTS client_id TEXT;
ALTER TABLE arrival ADD COLUMN IF NOT EXISTS domain TEXT;
ALTER TABLE arrival ADD COLUMN IF NOT EXISTS value_date DATE;
ALTER TABLE arrival ADD COLUMN IF NOT EXISTS overall_confidence DOUBLE PRECISION;
ALTER TABLE arrival ADD COLUMN IF NOT EXISTS mismatch_flagged BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE arrival ADD COLUMN IF NOT EXISTS classified_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS arrival_board_idx ON arrival (classified_at DESC);
CREATE INDEX IF NOT EXISTS arrival_client_idx ON arrival (client_id, value_date);
CREATE INDEX IF NOT EXISTS arrival_disposition_idx ON arrival (disposition);
