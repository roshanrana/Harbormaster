package arrival

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
)

// Verdict is what a dedupe check concluded about an arrival.
type Verdict string

const (
	// VerdictNew is content never seen before.
	VerdictNew Verdict = "NEW"
	// VerdictDuplicate is the exact same content under the exact same name.
	// Suppressed: it produces no downstream instruction (FR-6).
	VerdictDuplicate Verdict = "DUPLICATE"
	// VerdictRedelivery is identical content under a different filename.
	// Also suppressed downstream, but recorded, because it usually means a
	// client's scheduler is misconfigured and someone should know (FR-7).
	VerdictRedelivery Verdict = "REDELIVERY"
)

// Decision is the outcome of a dedupe check.
type Decision struct {
	Verdict Verdict
	// PriorArrivalID is the arrival this one duplicates, empty when new.
	PriorArrivalID string
	// PriorName is the filename the content first arrived under.
	PriorName string
	// SeenCount is how many times this content has now been observed.
	SeenCount int
}

// Suppress reports whether this arrival should stop here rather than being
// published. Both duplicate classes suppress; only the reason differs.
func (d Decision) Suppress() bool {
	return d.Verdict == VerdictDuplicate || d.Verdict == VerdictRedelivery
}

// Deduper recognises content that has been seen before.
type Deduper interface {
	Check(ctx context.Context, sha256Hex, originalName string) (Decision, error)
}

// SQLDeduper is backed by the arrival table.
//
// The uniqueness constraint lives in the schema, not here. Application-level
// dedupe alone loses to a race between two Portwatch instances; the database
// is the only thing that can arbitrate. This type reads the state, and the
// constraint enforces it.
type SQLDeduper struct{ db *sql.DB }

// NewSQLDeduper returns a Deduper over db.
func NewSQLDeduper(db *sql.DB) *SQLDeduper { return &SQLDeduper{db: db} }

// Check classifies an arrival against what has already been recorded.
func (d *SQLDeduper) Check(ctx context.Context, sha256Hex, originalName string) (Decision, error) {
	const q = `
		SELECT arrival_id, original_name
		FROM arrival
		WHERE content_sha256 = $1
		ORDER BY detected_at ASC`
	rows, err := d.db.QueryContext(ctx, q, sha256Hex)
	if err != nil {
		return Decision{}, fmt.Errorf("arrival: dedupe query: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var first struct {
		id, name string
	}
	count := 0
	sameNameSeen := false
	for rows.Next() {
		var id, name string
		if err := rows.Scan(&id, &name); err != nil {
			return Decision{}, fmt.Errorf("arrival: dedupe scan: %w", err)
		}
		if count == 0 {
			first.id, first.name = id, name
		}
		if name == originalName {
			sameNameSeen = true
		}
		count++
	}
	if err := rows.Err(); err != nil {
		return Decision{}, fmt.Errorf("arrival: dedupe iterate: %w", err)
	}

	switch {
	case count == 0:
		return Decision{Verdict: VerdictNew, SeenCount: 1}, nil
	case sameNameSeen:
		return Decision{Verdict: VerdictDuplicate, PriorArrivalID: first.id,
			PriorName: first.name, SeenCount: count + 1}, nil
	default:
		return Decision{Verdict: VerdictRedelivery, PriorArrivalID: first.id,
			PriorName: first.name, SeenCount: count + 1}, nil
	}
}

// Record inserts an arrival. A unique-violation means another instance won the
// race, which is not an error: it is the constraint doing its job.
func (d *SQLDeduper) Record(ctx context.Context, a Record) error {
	const q = `
		INSERT INTO arrival (arrival_id, content_sha256, original_name, ingress, uri, size_bytes, detected_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7)
		ON CONFLICT ON CONSTRAINT arrival_content_name_uniq DO NOTHING`
	res, err := d.db.ExecContext(ctx, q, a.ArrivalID, a.SHA256, a.OriginalName,
		a.Ingress, a.URI, a.Size, a.DetectedAt)
	if err != nil {
		return fmt.Errorf("arrival: record: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("arrival: rows affected: %w", err)
	}
	if n == 0 {
		return ErrAlreadyRecorded
	}
	return nil
}

// ErrAlreadyRecorded means the constraint rejected the insert because this
// exact content and filename were already recorded.
var ErrAlreadyRecorded = errors.New("arrival: already recorded")
