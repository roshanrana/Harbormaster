package web

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"google.golang.org/protobuf/encoding/protojson"
	hmv1 "harbormaster.dev/hm/gen/hmv1"
	"harbormaster.dev/hm/internal/masking"
)

// ProjectClassified writes a classified arrival into the board projection.
//
// Idempotent by arrival id, because at-least-once delivery means this will be
// called twice for the same message sooner or later and a board that
// double-counts is a board nobody trusts.
func (s *Store) ProjectClassified(ctx context.Context, m *hmv1.ArrivalClassified) error {
	payload, err := protojson.MarshalOptions{Multiline: false}.Marshal(m)
	if err != nil {
		return fmt.Errorf("web: marshal classification: %w", err)
	}

	valueDate := m.GetValueDate().GetResolved()
	const q = `
		UPDATE arrival SET
		  client_id = $2,
		  domain = $3,
		  value_date = NULLIF($4,'')::date,
		  disposition = $5,
		  overall_confidence = $6,
		  mismatch_flagged = $7,
		  classified_at = $8,
		  classification = $9::jsonb
		WHERE arrival_id = $1`
	res, err := s.db.ExecContext(ctx, q,
		m.GetArrivalId(),
		nullIfEmpty(m.GetClientId()),
		nullIfEmpty(trimEnumPrefix(m.GetDomain().String(), "PRODUCT_DOMAIN_")),
		valueDate,
		trimEnumPrefix(m.GetDisposition().String(), "ARRIVAL_DISPOSITION_"),
		m.GetOverallConfidence(),
		m.GetValueDate().GetMismatchFlagged(),
		m.GetClassifiedAt().AsTime(),
		string(payload),
	)
	if err != nil {
		return fmt.Errorf("web: project classified: %w", err)
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("web: rows affected: %w", err)
	}
	if affected == 0 {
		// The classified event outran its raw arrival row. Ordering across
		// topics is not guaranteed, so this is expected occasionally rather
		// than an error; the projector will see it again on replay.
		return fmt.Errorf("%w: arrival %s not yet recorded", ErrNotFound, m.GetArrivalId())
	}
	return nil
}

// ProjectAssignment records an issued berth assignment.
func (s *Store) ProjectAssignment(ctx context.Context, m *hmv1.BerthAssigned) error {
	const q = `
		INSERT INTO assignment (assignment_id, client_id, domain, value_date,
		    side_1_arrival, side_2_arrival, expectation_id, confidence, supersedes,
		    notes, emitted_at)
		VALUES ($1,$2,$3,$4::date,NULLIF($5,''),NULLIF($6,''),$7,$8,NULLIF($9,''),$10,$11)
		ON CONFLICT (assignment_id) DO NOTHING`
	if _, err := s.db.ExecContext(ctx, q,
		m.GetAssignmentId(), m.GetClientId(),
		trimEnumPrefix(m.GetDomain().String(), "PRODUCT_DOMAIN_"), m.GetValueDate(),
		m.GetSide_1().GetArrivalId(), m.GetSide_2().GetArrivalId(),
		m.GetExpectationId(), m.GetConfidence(), m.GetSupersedes(),
		m.GetNotes(), m.GetEmittedAt().AsTime(),
	); err != nil {
		return fmt.Errorf("web: project assignment: %w", err)
	}
	return nil
}

// ProjectSuperseded marks a prior assignment as withdrawn.
//
// The row is updated, never deleted. "This reconciliation ran and was then
// withdrawn" is a fact an auditor will ask about, and a deleted row cannot
// answer it.
func (s *Store) ProjectSuperseded(ctx context.Context, m *hmv1.BerthSuperseded) error {
	const q = `
		UPDATE assignment SET voided_at = $2, voided_by = $3
		WHERE assignment_id = $1 AND voided_at IS NULL`
	if _, err := s.db.ExecContext(ctx, q,
		m.GetAssignmentId(), m.GetEmittedAt().AsTime(), m.GetSupersededBy()); err != nil {
		return fmt.Errorf("web: project supersession: %w", err)
	}
	return nil
}

// ProjectAlert records a missing-file alert.
func (s *Store) ProjectAlert(ctx context.Context, m *hmv1.MissingFileAlert) error {
	// Deterministic id: one alert per slot and side, however many times the
	// sweep runs or the message is redelivered.
	id := fmt.Sprintf("%s:%s:%s:%s", m.GetClientId(),
		trimEnumPrefix(m.GetDomain().String(), "PRODUCT_DOMAIN_"),
		m.GetValueDate(), trimEnumPrefix(m.GetMissingSide().String(), "RECON_SIDE_"))

	const q = `
		INSERT INTO alert (id, client_id, domain, value_date, expectation_id,
		    missing_side, deadline, emitted_at)
		VALUES ($1,$2,$3,$4::date,$5,$6,$7,$8)
		ON CONFLICT (id) DO NOTHING`
	if _, err := s.db.ExecContext(ctx, q, id, m.GetClientId(),
		trimEnumPrefix(m.GetDomain().String(), "PRODUCT_DOMAIN_"), m.GetValueDate(),
		m.GetExpectationId(), trimEnumPrefix(m.GetMissingSide().String(), "RECON_SIDE_"),
		m.GetDeadline().AsTime(), m.GetEmittedAt().AsTime()); err != nil {
		return fmt.Errorf("web: project alert: %w", err)
	}
	return nil
}

// AcknowledgeAlert marks an alert as seen by a named person.
func (s *Store) AcknowledgeAlert(ctx context.Context, id, by string) error {
	res, err := s.db.ExecContext(ctx,
		`UPDATE alert SET acknowledged_at = NOW(), acknowledged_by = $2
		 WHERE id = $1 AND acknowledged_at IS NULL`, id, by)
	if err != nil {
		return fmt.Errorf("web: acknowledge alert: %w", err)
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return fmt.Errorf("%w: alert %s", ErrNotFound, id)
	}
	return nil
}

// --- review ----------------------------------------------------------------

// ReviewDecision is a reviewer's ruling on a quarantined arrival.
type ReviewDecision struct {
	ArrivalID           string            `json:"arrival_id"`
	Reviewer            string            `json:"reviewer"`
	Decision            string            `json:"decision"` // APPROVE | CORRECT | REJECT
	CorrectedClientID   string            `json:"corrected_client_id,omitempty"`
	CorrectedValueDate  string            `json:"corrected_value_date,omitempty"`
	CorrectedMappings   map[string]string `json:"corrected_mappings,omitempty"`
	PromoteToDictionary bool              `json:"promote_to_dictionary,omitempty"`
	Notes               string            `json:"notes,omitempty"`
}

// ErrAlreadyReviewed means someone else has already ruled on this arrival.
var ErrAlreadyReviewed = errors.New("web: arrival already reviewed")

// ValidDecisions is the closed set a reviewer may submit.
var ValidDecisions = map[string]bool{"APPROVE": true, "CORRECT": true, "REJECT": true}

// RecordReview persists a review decision.
//
// The primary key on arrival_id is what enforces four-eyes integrity: a second
// reviewer acting on the same arrival is rejected by the database rather than
// by a check that could race. A CORRECT with nothing corrected is refused,
// because an empty correction is almost always a mis-click and quietly
// accepting it would dispatch an unchanged file that a human believed they
// had fixed.
func (s *Store) RecordReview(ctx context.Context, d ReviewDecision) error {
	if !ValidDecisions[d.Decision] {
		return fmt.Errorf("web: unknown decision %q", d.Decision)
	}
	if d.Reviewer == "" {
		return errors.New("web: a review decision must name its reviewer")
	}
	if d.Decision == "CORRECT" && d.CorrectedClientID == "" &&
		d.CorrectedValueDate == "" && len(d.CorrectedMappings) == 0 {
		return errors.New("web: a CORRECT decision must carry at least one correction")
	}

	corrections, err := json.Marshal(map[string]any{
		"client_id":  d.CorrectedClientID,
		"value_date": d.CorrectedValueDate,
		"mappings":   d.CorrectedMappings,
		"promote":    d.PromoteToDictionary,
		"notes":      d.Notes,
	})
	if err != nil {
		return fmt.Errorf("web: marshal corrections: %w", err)
	}

	res, err := s.db.ExecContext(ctx, `
		INSERT INTO review (arrival_id, reviewer, decision, corrections, decided_at)
		VALUES ($1,$2,$3,$4::jsonb,$5)
		ON CONFLICT (arrival_id) DO NOTHING`,
		d.ArrivalID, d.Reviewer, d.Decision, string(corrections), time.Now().UTC())
	if err != nil {
		return fmt.Errorf("web: record review: %w", err)
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return ErrAlreadyReviewed
	}
	return nil
}

// Review returns the decision recorded for an arrival, if any.
func (s *Store) Review(ctx context.Context, arrivalID string) (*ReviewDecision, error) {
	var d ReviewDecision
	var corrections []byte
	err := s.db.QueryRowContext(ctx,
		`SELECT arrival_id, reviewer, decision, corrections FROM review WHERE arrival_id = $1`,
		arrivalID).Scan(&d.ArrivalID, &d.Reviewer, &d.Decision, &corrections)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("%w: review for %s", ErrNotFound, arrivalID)
	}
	if err != nil {
		return nil, fmt.Errorf("web: read review: %w", err)
	}
	var payload struct {
		ClientID  string            `json:"client_id"`
		ValueDate string            `json:"value_date"`
		Mappings  map[string]string `json:"mappings"`
		Promote   bool              `json:"promote"`
		Notes     string            `json:"notes"`
	}
	if len(corrections) > 0 {
		_ = json.Unmarshal(corrections, &payload)
	}
	d.CorrectedClientID = payload.ClientID
	d.CorrectedValueDate = payload.ValueDate
	d.CorrectedMappings = payload.Mappings
	d.PromoteToDictionary = payload.Promote
	d.Notes = payload.Notes
	return &d, nil
}

// --- offsets ---------------------------------------------------------------

// SaveOffset records the projector's position so a restart resumes.
func (s *Store) SaveOffset(ctx context.Context, consumer, topic string, partition int32, next int64) error {
	const q = `
		INSERT INTO projection_offset (consumer, topic, partition, next_offset, updated_at)
		VALUES ($1,$2,$3,$4,NOW())
		ON CONFLICT (consumer, topic, partition) DO UPDATE
		SET next_offset = EXCLUDED.next_offset, updated_at = NOW()`
	if _, err := s.db.ExecContext(ctx, q, consumer, topic, partition, next); err != nil {
		return fmt.Errorf("web: save offset: %w", err)
	}
	return nil
}

// --- helpers ---------------------------------------------------------------

func nullIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func trimEnumPrefix(value, prefix string) string {
	if len(value) > len(prefix) && value[:len(prefix)] == prefix {
		return value[len(prefix):]
	}
	return value
}

// MaskAccountsInClassification redacts account numbers inside a stored
// classification payload before it leaves the process (ADR-011).
//
// Applied here rather than at each template or handler, because a masking rule
// that has to be remembered at call sites is a rule that will be forgotten in
// the one place it mattered.
func MaskAccountsInClassification(raw json.RawMessage) json.RawMessage {
	if len(raw) == 0 || !masking.Enabled() {
		return raw
	}
	var payload map[string]any
	if err := json.Unmarshal(raw, &payload); err != nil {
		return raw
	}
	if ids, ok := payload["accountIds"].([]any); ok {
		for i, v := range ids {
			if s, isString := v.(string); isString {
				ids[i] = masking.AccountNumber(s)
			}
		}
		payload["accountIds"] = ids
	}
	out, err := json.Marshal(payload)
	if err != nil {
		return raw
	}
	return out
}
