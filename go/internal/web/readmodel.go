// Package web serves the operations board and projects events into read models.
//
// The read models are projections, never a source of truth. Everything here can
// be rebuilt by replaying the topics from offset zero, which is why every write
// is an upsert keyed on an identifier the producer owns. That property is what
// makes a bad projection a five-minute fix rather than an incident.
package web

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

// ArrivalRow is one line on the arrivals board.
type ArrivalRow struct {
	ArrivalID       string     `json:"arrival_id"`
	OriginalName    string     `json:"original_name"`
	Ingress         string     `json:"ingress"`
	SizeBytes       int64      `json:"size_bytes"`
	DetectedAt      time.Time  `json:"detected_at"`
	ClassifiedAt    *time.Time `json:"classified_at,omitempty"`
	ClientID        string     `json:"client_id"`
	Domain          string     `json:"domain"`
	ValueDate       string     `json:"value_date"`
	Disposition     string     `json:"disposition"`
	Confidence      float64    `json:"overall_confidence"`
	MismatchFlagged bool       `json:"mismatch_flagged"`
}

// ArrivalDetail is the full classification for one arrival.
type ArrivalDetail struct {
	ArrivalRow
	ContentSHA256  string          `json:"content_sha256"`
	URI            string          `json:"uri"`
	Classification json.RawMessage `json:"classification,omitempty"`
}

// AssignmentRow is one issued berth assignment.
type AssignmentRow struct {
	AssignmentID  string     `json:"assignment_id"`
	ClientID      string     `json:"client_id"`
	Domain        string     `json:"domain"`
	ValueDate     string     `json:"value_date"`
	Side1Arrival  string     `json:"side_1_arrival"`
	Side2Arrival  string     `json:"side_2_arrival"`
	ExpectationID string     `json:"expectation_id"`
	Confidence    float64    `json:"confidence"`
	Supersedes    string     `json:"supersedes,omitempty"`
	Notes         string     `json:"notes,omitempty"`
	EmittedAt     time.Time  `json:"emitted_at"`
	VoidedAt      *time.Time `json:"voided_at,omitempty"`
	VoidedBy      string     `json:"voided_by,omitempty"`
}

// Voided reports whether this assignment has been withdrawn by a correction.
func (a AssignmentRow) Voided() bool { return a.VoidedAt != nil }

// SlotRow is one reconciliation slot.
type SlotRow struct {
	ClientID      string    `json:"client_id"`
	Domain        string    `json:"domain"`
	ValueDate     string    `json:"value_date"`
	State         string    `json:"state"`
	ExpectationID string    `json:"expectation_id"`
	Side1Arrival  string    `json:"side_1_arrival,omitempty"`
	Side2Arrival  string    `json:"side_2_arrival,omitempty"`
	AssignmentID  string    `json:"assignment_id,omitempty"`
	Deadline      time.Time `json:"deadline"`
}

// MissingSide reports which side of an incomplete slot has not arrived.
func (s SlotRow) MissingSide() string {
	switch {
	case s.Side1Arrival == "":
		return "INTERNAL_GL"
	case s.Side2Arrival == "":
		return "EXTERNAL_CLIENT"
	default:
		return ""
	}
}

// AlertRow is one missing-file alert.
type AlertRow struct {
	ID             string     `json:"id"`
	ClientID       string     `json:"client_id"`
	Domain         string     `json:"domain"`
	ValueDate      string     `json:"value_date"`
	ExpectationID  string     `json:"expectation_id"`
	MissingSide    string     `json:"missing_side"`
	Deadline       time.Time  `json:"deadline"`
	EmittedAt      time.Time  `json:"emitted_at"`
	AcknowledgedAt *time.Time `json:"acknowledged_at,omitempty"`
	AcknowledgedBy string     `json:"acknowledged_by,omitempty"`
}

// ArrivalFilter narrows the board.
type ArrivalFilter struct {
	ClientID    string
	Disposition string
	ValueDate   string
	Since       time.Time
	Limit       int
}

// ErrNotFound is returned when a requested record does not exist.
var ErrNotFound = errors.New("web: not found")

// Store reads and writes the projections.
type Store struct{ db *sql.DB }

// NewStore returns a Store over db.
func NewStore(db *sql.DB) *Store { return &Store{db: db} }

const defaultLimit = 200

// Arrivals returns board rows, newest first.
func (s *Store) Arrivals(ctx context.Context, f ArrivalFilter) ([]ArrivalRow, error) {
	limit := f.Limit
	if limit <= 0 || limit > 1000 {
		limit = defaultLimit
	}

	var where []string
	var args []any
	add := func(clause string, value any) {
		args = append(args, value)
		where = append(where, fmt.Sprintf(clause, len(args)))
	}
	if f.ClientID != "" {
		add("client_id = $%d", f.ClientID)
	}
	if f.Disposition != "" {
		add("disposition = $%d", f.Disposition)
	}
	if f.ValueDate != "" {
		add("value_date = $%d", f.ValueDate)
	}
	if !f.Since.IsZero() {
		add("detected_at >= $%d", f.Since)
	}
	clause := ""
	if len(where) > 0 {
		clause = "WHERE " + strings.Join(where, " AND ")
	}
	args = append(args, limit)

	query := fmt.Sprintf(`
		SELECT arrival_id, original_name, ingress, size_bytes, detected_at, classified_at,
		       COALESCE(client_id,''), COALESCE(domain,''),
		       COALESCE(to_char(value_date,'YYYY-MM-DD'),''),
		       COALESCE(disposition,''), COALESCE(overall_confidence,0), mismatch_flagged
		FROM arrival %s
		ORDER BY COALESCE(classified_at, detected_at) DESC
		LIMIT $%d`, clause, len(args))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("web: arrivals: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var out []ArrivalRow
	for rows.Next() {
		var r ArrivalRow
		if err := rows.Scan(&r.ArrivalID, &r.OriginalName, &r.Ingress, &r.SizeBytes,
			&r.DetectedAt, &r.ClassifiedAt, &r.ClientID, &r.Domain, &r.ValueDate,
			&r.Disposition, &r.Confidence, &r.MismatchFlagged); err != nil {
			return nil, fmt.Errorf("web: scan arrival: %w", err)
		}
		out = append(out, r)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("web: iterate arrivals: %w", err)
	}
	return out, nil
}

// Arrival returns one arrival with its full classification payload.
func (s *Store) Arrival(ctx context.Context, id string) (*ArrivalDetail, error) {
	const q = `
		SELECT arrival_id, original_name, ingress, size_bytes, detected_at, classified_at,
		       COALESCE(client_id,''), COALESCE(domain,''),
		       COALESCE(to_char(value_date,'YYYY-MM-DD'),''),
		       COALESCE(disposition,''), COALESCE(overall_confidence,0), mismatch_flagged,
		       content_sha256, uri, classification
		FROM arrival WHERE arrival_id = $1`
	var d ArrivalDetail
	var raw []byte
	err := s.db.QueryRowContext(ctx, q, id).Scan(
		&d.ArrivalID, &d.OriginalName, &d.Ingress, &d.SizeBytes, &d.DetectedAt,
		&d.ClassifiedAt, &d.ClientID, &d.Domain, &d.ValueDate, &d.Disposition,
		&d.Confidence, &d.MismatchFlagged, &d.ContentSHA256, &d.URI, &raw)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("%w: arrival %s", ErrNotFound, id)
	}
	if err != nil {
		return nil, fmt.Errorf("web: arrival %s: %w", id, err)
	}
	if len(raw) > 0 {
		d.Classification = json.RawMessage(raw)
	}
	return &d, nil
}

// Quarantine returns arrivals awaiting a review decision.
//
// Only arrivals with no recorded decision are returned: once a reviewer has
// acted the item leaves the queue, which is what stops two people working the
// same file.
func (s *Store) Quarantine(ctx context.Context) ([]ArrivalRow, error) {
	const q = `
		SELECT a.arrival_id, a.original_name, a.ingress, a.size_bytes, a.detected_at,
		       a.classified_at, COALESCE(a.client_id,''), COALESCE(a.domain,''),
		       COALESCE(to_char(a.value_date,'YYYY-MM-DD'),''),
		       COALESCE(a.disposition,''), COALESCE(a.overall_confidence,0), a.mismatch_flagged
		FROM arrival a
		LEFT JOIN review r ON r.arrival_id = a.arrival_id
		WHERE a.disposition IN ('QUARANTINED','REJECTED') AND r.arrival_id IS NULL
		ORDER BY a.classified_at ASC`
	rows, err := s.db.QueryContext(ctx, q)
	if err != nil {
		return nil, fmt.Errorf("web: quarantine: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var out []ArrivalRow
	for rows.Next() {
		var r ArrivalRow
		if err := rows.Scan(&r.ArrivalID, &r.OriginalName, &r.Ingress, &r.SizeBytes,
			&r.DetectedAt, &r.ClassifiedAt, &r.ClientID, &r.Domain, &r.ValueDate,
			&r.Disposition, &r.Confidence, &r.MismatchFlagged); err != nil {
			return nil, fmt.Errorf("web: scan quarantine: %w", err)
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// Assignments returns issued berth assignments, newest first.
func (s *Store) Assignments(ctx context.Context, limit int) ([]AssignmentRow, error) {
	if limit <= 0 || limit > 1000 {
		limit = defaultLimit
	}
	const q = `
		SELECT assignment_id, client_id, domain, to_char(value_date,'YYYY-MM-DD'),
		       COALESCE(side_1_arrival,''), COALESCE(side_2_arrival,''), expectation_id,
		       confidence, COALESCE(supersedes,''), notes, emitted_at, voided_at,
		       COALESCE(voided_by,'')
		FROM assignment ORDER BY emitted_at DESC LIMIT $1`
	rows, err := s.db.QueryContext(ctx, q, limit)
	if err != nil {
		return nil, fmt.Errorf("web: assignments: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var out []AssignmentRow
	for rows.Next() {
		var a AssignmentRow
		if err := rows.Scan(&a.AssignmentID, &a.ClientID, &a.Domain, &a.ValueDate,
			&a.Side1Arrival, &a.Side2Arrival, &a.ExpectationID, &a.Confidence,
			&a.Supersedes, &a.Notes, &a.EmittedAt, &a.VoidedAt, &a.VoidedBy); err != nil {
			return nil, fmt.Errorf("web: scan assignment: %w", err)
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

// Slots returns reconciliation slots, optionally filtered by state or date.
func (s *Store) Slots(ctx context.Context, state, valueDate string) ([]SlotRow, error) {
	var where []string
	var args []any
	if state != "" {
		args = append(args, state)
		where = append(where, fmt.Sprintf("state = $%d", len(args)))
	}
	if valueDate != "" {
		args = append(args, valueDate)
		where = append(where, fmt.Sprintf("value_date = $%d", len(args)))
	}
	clause := ""
	if len(where) > 0 {
		clause = "WHERE " + strings.Join(where, " AND ")
	}
	query := fmt.Sprintf(`
		SELECT client_id, domain, to_char(value_date,'YYYY-MM-DD'), state, expectation_id,
		       COALESCE(side_1_arrival,''), COALESCE(side_2_arrival,''),
		       COALESCE(assignment_id,''), deadline
		FROM slot %s ORDER BY value_date DESC, client_id, domain`, clause)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("web: slots: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var out []SlotRow
	for rows.Next() {
		var r SlotRow
		if err := rows.Scan(&r.ClientID, &r.Domain, &r.ValueDate, &r.State,
			&r.ExpectationID, &r.Side1Arrival, &r.Side2Arrival, &r.AssignmentID,
			&r.Deadline); err != nil {
			return nil, fmt.Errorf("web: scan slot: %w", err)
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// Alerts returns missing-file alerts. Unacknowledged first.
func (s *Store) Alerts(ctx context.Context, includeAcknowledged bool) ([]AlertRow, error) {
	q := `
		SELECT id, client_id, domain, to_char(value_date,'YYYY-MM-DD'), expectation_id,
		       missing_side, deadline, emitted_at, acknowledged_at, COALESCE(acknowledged_by,'')
		FROM alert`
	if !includeAcknowledged {
		q += " WHERE acknowledged_at IS NULL"
	}
	q += " ORDER BY acknowledged_at NULLS FIRST, emitted_at DESC LIMIT 500"

	rows, err := s.db.QueryContext(ctx, q)
	if err != nil {
		return nil, fmt.Errorf("web: alerts: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var out []AlertRow
	for rows.Next() {
		var a AlertRow
		if err := rows.Scan(&a.ID, &a.ClientID, &a.Domain, &a.ValueDate, &a.ExpectationID,
			&a.MissingSide, &a.Deadline, &a.EmittedAt, &a.AcknowledgedAt,
			&a.AcknowledgedBy); err != nil {
			return nil, fmt.Errorf("web: scan alert: %w", err)
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

// Summary is the headline count set for the board.
type Summary struct {
	Arrivals    int `json:"arrivals"`
	Dispatched  int `json:"dispatched"`
	Quarantined int `json:"quarantined"`
	Rejected    int `json:"rejected"`
	Assignments int `json:"assignments"`
	OpenAlerts  int `json:"open_alerts"`
	Mismatches  int `json:"value_date_mismatches"`
	// QuarantineRate is measured against NFR-7's five percent target, so the
	// board shows the number the requirement is written in terms of.
	QuarantineRate float64 `json:"quarantine_rate"`
}

const quarantineRateTarget = 0.05

// OperationalPosture translates board counts into an operator-facing status.
type OperationalPosture struct {
	Level                string   `json:"level"`
	Label                string   `json:"label"`
	Action               string   `json:"action"`
	Rationale            []string `json:"rationale"`
	QuarantineRateTarget float64  `json:"quarantine_rate_target"`
}

// Posture derives the next operational action from the current summary.
func (s Summary) Posture() OperationalPosture {
	out := OperationalPosture{
		Level:                "CLEAR",
		Label:                "Clear",
		Action:               "No operator action is waiting in the console.",
		QuarantineRateTarget: quarantineRateTarget,
	}

	switch {
	case s.OpenAlerts > 0:
		out.Level = "INCIDENT"
		out.Label = "Action required"
		out.Action = "Acknowledge missing-file alerts and contact the producing system owner."
	case s.QuarantineRate > quarantineRateTarget:
		out.Level = "ATTENTION"
		out.Label = "Rate above target"
		out.Action = "Review held files and promote confirmed mappings into the dictionary."
	case s.Quarantined > 0:
		out.Level = "ATTENTION"
		out.Label = "Review needed"
		out.Action = "Open the review queue and record decisions for held files."
	case s.Rejected > 0:
		out.Level = "ATTENTION"
		out.Label = "Rejected files"
		out.Action = "Inspect rejected arrivals and confirm the producer has the expected format."
	case s.Mismatches > 0:
		out.Level = "ATTENTION"
		out.Label = "Schedule drift"
		out.Action = "Inspect value-date disagreements for late upstream batches."
	}

	out.Rationale = s.postureRationale()
	if len(out.Rationale) == 0 {
		out.Rationale = []string{"no open alerts or queued reviews"}
	}
	return out
}

// DegradedPosture is shown when the projection store cannot answer.
func DegradedPosture() OperationalPosture {
	return OperationalPosture{
		Level:                "DEGRADED",
		Label:                "Projection unavailable",
		Action:               "Check Postgres connectivity and replay the projector once the store is back.",
		Rationale:            []string{"summary query failed"},
		QuarantineRateTarget: quarantineRateTarget,
	}
}

func (s Summary) postureRationale() []string {
	var out []string
	if s.OpenAlerts > 0 {
		out = append(out, fmt.Sprintf("open missing-file alerts: %d", s.OpenAlerts))
	}
	if s.Quarantined > 0 {
		out = append(out, fmt.Sprintf("review queue: %d", s.Quarantined))
	}
	if s.Rejected > 0 {
		out = append(out, fmt.Sprintf("rejected arrivals: %d", s.Rejected))
	}
	if s.Mismatches > 0 {
		out = append(out, fmt.Sprintf("value-date disagreements: %d", s.Mismatches))
	}
	if s.QuarantineRate > 0 {
		out = append(out, fmt.Sprintf("quarantine rate: %.0f%% (target %.0f%%)",
			s.QuarantineRate*100, quarantineRateTarget*100))
	}
	return out
}

// Summary computes the board headline counts.
func (s *Store) Summary(ctx context.Context) (Summary, error) {
	var out Summary
	const q = `
		SELECT
		  (SELECT count(*) FROM arrival),
		  (SELECT count(*) FROM arrival WHERE disposition = 'DISPATCHED'),
		  (SELECT count(*) FROM arrival WHERE disposition = 'QUARANTINED'),
		  (SELECT count(*) FROM arrival WHERE disposition = 'REJECTED'),
		  (SELECT count(*) FROM assignment WHERE voided_at IS NULL),
		  (SELECT count(*) FROM alert WHERE acknowledged_at IS NULL),
		  (SELECT count(*) FROM arrival WHERE mismatch_flagged)`
	if err := s.db.QueryRowContext(ctx, q).Scan(&out.Arrivals, &out.Dispatched,
		&out.Quarantined, &out.Rejected, &out.Assignments, &out.OpenAlerts,
		&out.Mismatches); err != nil {
		return out, fmt.Errorf("web: summary: %w", err)
	}
	classified := out.Dispatched + out.Quarantined + out.Rejected
	if classified > 0 {
		out.QuarantineRate = float64(out.Quarantined) / float64(classified)
	}
	return out, nil
}
