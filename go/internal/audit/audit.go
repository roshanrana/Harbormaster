// Package audit is the tamper-evident decision log.
//
// Every decision any component makes about an arrival is appended here with
// its inputs, its outcome and the actor responsible. Records for one arrival
// form a hash chain: each record's hash covers the previous record's hash, so
// editing or deleting any record invalidates every record after it.
//
// This is what makes FR-39 real. "Why was this file reconciled against the
// 28th?" is answerable months later from the chain alone, and the answer can
// be shown to be unaltered. In a reconciliation control system that is not a
// nice-to-have: it is the difference between an explanation and an assertion.
package audit

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"
)

// Entry is a decision to be recorded. RecordID, At and the hashes are filled
// in by Append.
type Entry struct {
	ArrivalID    string
	Component    string
	DecisionType string
	Inputs       map[string]any
	Outcome      map[string]any
	Actor        string
}

// Record is a persisted audit entry.
type Record struct {
	RecordID     string
	ArrivalID    string
	At           time.Time
	Component    string
	DecisionType string
	InputsJSON   string
	OutcomeJSON  string
	Actor        string
	PrevHash     string
	RecordHash   string
}

// Chain appends to and verifies the audit log.
type Chain struct {
	db  *sql.DB
	now func() time.Time
}

// New returns a Chain over db.
func New(db *sql.DB) *Chain { return &Chain{db: db, now: func() time.Time { return time.Now().UTC() }} }

// SetClock replaces the time source. Tests use this for deterministic hashes.
func (c *Chain) SetClock(fn func() time.Time) { c.now = fn }

// ComputeHash derives a record's hash from its content and its predecessor.
//
// Field order and the separator are part of the contract: changing either
// invalidates every chain ever written, so both are fixed here rather than
// being an implementation detail of whoever writes the next component.
func ComputeHash(r Record) string {
	h := sha256.New()
	for _, part := range []string{
		r.RecordID,
		r.ArrivalID,
		r.At.UTC().Format(time.RFC3339Nano),
		r.Component,
		r.DecisionType,
		r.InputsJSON,
		r.OutcomeJSON,
		r.Actor,
		r.PrevHash,
	} {
		h.Write([]byte(part))
		h.Write([]byte{0x1f}) // unit separator: prevents field-boundary ambiguity
	}
	return hex.EncodeToString(h.Sum(nil))
}

// Append writes one entry, linked to the previous record for the same arrival.
//
// The read of the previous hash and the insert happen in one transaction at
// serializable isolation. Anything weaker allows two concurrent appends to read
// the same predecessor and fork the chain, which would look like tampering
// during verification and cost someone a very confusing afternoon.
func (c *Chain) Append(ctx context.Context, e Entry) error {
	inputs, err := marshal(e.Inputs)
	if err != nil {
		return err
	}
	outcome, err := marshal(e.Outcome)
	if err != nil {
		return err
	}
	actor := e.Actor
	if actor == "" {
		actor = "system"
	}

	tx, err := c.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return fmt.Errorf("audit: begin: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	var prevHash string
	err = tx.QueryRowContext(ctx,
		`SELECT record_hash FROM audit_record WHERE arrival_id = $1 ORDER BY at DESC, record_id DESC LIMIT 1`,
		e.ArrivalID).Scan(&prevHash)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return fmt.Errorf("audit: read previous: %w", err)
	}

	rec := Record{
		// Truncated to microseconds because that is Postgres's TIMESTAMPTZ
		// resolution. Hashing nanoseconds we cannot store back would make
		// every chain fail verification the moment it was read.
		RecordID: ulid.Make().String(), ArrivalID: e.ArrivalID,
		At:        c.now().UTC().Truncate(time.Microsecond),
		Component: e.Component, DecisionType: e.DecisionType,
		InputsJSON: inputs, OutcomeJSON: outcome, Actor: actor, PrevHash: prevHash,
	}
	rec.RecordHash = ComputeHash(rec)

	if _, err := tx.ExecContext(ctx, `
		INSERT INTO audit_record (record_id, arrival_id, at, component, decision_type,
		                          inputs, outcome, actor, prev_hash, record_hash)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
		rec.RecordID, rec.ArrivalID, rec.At, rec.Component, rec.DecisionType,
		rec.InputsJSON, rec.OutcomeJSON, rec.Actor, rec.PrevHash, rec.RecordHash); err != nil {
		return fmt.Errorf("audit: insert: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("audit: commit: %w", err)
	}
	return nil
}

// Read returns the chain for one arrival in order.
func (c *Chain) Read(ctx context.Context, arrivalID string) ([]Record, error) {
	rows, err := c.db.QueryContext(ctx, `
		SELECT record_id, arrival_id, at, component, decision_type,
		       inputs, outcome, actor, prev_hash, record_hash
		FROM audit_record WHERE arrival_id = $1 ORDER BY at ASC, record_id ASC`, arrivalID)
	if err != nil {
		return nil, fmt.Errorf("audit: read chain: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var out []Record
	for rows.Next() {
		var r Record
		if err := rows.Scan(&r.RecordID, &r.ArrivalID, &r.At, &r.Component, &r.DecisionType,
			&r.InputsJSON, &r.OutcomeJSON, &r.Actor, &r.PrevHash, &r.RecordHash); err != nil {
			return nil, fmt.Errorf("audit: scan: %w", err)
		}
		out = append(out, r)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("audit: iterate: %w", err)
	}
	return out, nil
}

// Break describes the first point at which a chain fails verification.
type Break struct {
	ArrivalID string
	RecordID  string
	Reason    string
	Position  int
}

// Verify walks one arrival's chain and returns the first break, or nil.
func (c *Chain) Verify(ctx context.Context, arrivalID string) (*Break, error) {
	records, err := c.Read(ctx, arrivalID)
	if err != nil {
		return nil, err
	}
	return VerifyRecords(arrivalID, records), nil
}

// VerifyRecords walks an already-loaded chain, in order, and returns the
// first break or nil. It is the pure half of Verify: the same walk runs over
// records read from Postgres and over a recorded chain in a file, so the
// offline bench (cmd/auditcheck) exercises exactly the check the control
// plane runs rather than a reimplementation that could drift.
func VerifyRecords(arrivalID string, records []Record) *Break {
	prev := ""
	for i, r := range records {
		if r.PrevHash != prev {
			return &Break{ArrivalID: arrivalID, RecordID: r.RecordID, Position: i,
				Reason: "prev_hash does not match the preceding record"}
		}
		if want := ComputeHash(r); want != r.RecordHash {
			return &Break{ArrivalID: arrivalID, RecordID: r.RecordID, Position: i,
				Reason: "record_hash does not match the record contents"}
		}
		prev = r.RecordHash
	}
	return nil
}

// VerifyAll walks every chain in the log and returns all breaks found.
func (c *Chain) VerifyAll(ctx context.Context) ([]Break, error) {
	rows, err := c.db.QueryContext(ctx, `SELECT DISTINCT arrival_id FROM audit_record`)
	if err != nil {
		return nil, fmt.Errorf("audit: list arrivals: %w", err)
	}
	var ids []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			_ = rows.Close()
			return nil, fmt.Errorf("audit: scan arrival id: %w", err)
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, fmt.Errorf("audit: iterate arrivals: %w", err)
	}
	_ = rows.Close()

	var breaks []Break
	for _, id := range ids {
		b, err := c.Verify(ctx, id)
		if err != nil {
			return nil, err
		}
		if b != nil {
			breaks = append(breaks, *b)
		}
	}
	return breaks, nil
}

func marshal(m map[string]any) (string, error) {
	if m == nil {
		return "{}", nil
	}
	b, err := json.Marshal(m)
	if err != nil {
		return "", fmt.Errorf("audit: marshal: %w", err)
	}
	return string(b), nil
}

// Summarise renders a chain as a human-readable trail. Used by the CLI
// verifier and by the arrival detail view.
func Summarise(records []Record) string {
	var sb strings.Builder
	for i, r := range records {
		fmt.Fprintf(&sb, "%2d  %s  %-14s %-22s %s\n",
			i+1, r.At.Format(time.RFC3339), r.Component, r.DecisionType, r.Actor)
	}
	return sb.String()
}
