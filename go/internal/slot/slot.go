// Package slot owns the reconciliation slot lifecycle.
//
// A slot is one reconciliation waiting to happen: a client, a product domain
// and a value date. It opens when the first side arrives, completes when both
// sides are present, and is superseded when a correction turns up for a date
// already dispatched.
//
// Two properties are worth stating because they are the reason this package
// exists rather than the logic being inlined into Berthmaster.
//
// Ordering is structural. Every event for a slot is keyed on the slot identity
// (ADR-005), so a void and its replacement land on the same partition and no
// consumer can observe them out of order. There is no distributed lock here
// because the partition key makes one unnecessary.
//
// Lateness is measured in business days on the client's calendar. A file for
// Friday arriving on Monday is one business day late, not three calendar days
// late, and a system that gets that wrong either closes slots too early or
// leaves them open across a holiday weekend.
package slot

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"harbormaster.dev/hm/internal/registry"
)

// State values, matching the proto enum.
type State string

const (
	StateOpen       State = "OPEN"
	StatePartial    State = "PARTIAL"
	StateAssigned   State = "ASSIGNED"
	StateSuperseded State = "SUPERSEDED"
	StateMissing    State = "MISSING"
)

// Key identifies a slot. It is also the message partition key.
type Key struct {
	ClientID  string
	Domain    string
	ValueDate string // YYYY-MM-DD
}

func (k Key) String() string {
	return fmt.Sprintf("%s:%s:%s", k.ClientID, k.Domain, k.ValueDate)
}

// Slot is one reconciliation's state.
type Slot struct {
	Key           Key
	State         State
	ExpectationID string
	Side1Arrival  string // internal GL
	Side2Arrival  string // external client
	AssignmentID  string
	OpenedAt      time.Time
	Deadline      time.Time
}

// Complete reports whether both sides are present.
func (s *Slot) Complete() bool { return s.Side1Arrival != "" && s.Side2Arrival != "" }

// Outcome is what an arrival did to a slot.
type Outcome struct {
	Slot *Slot
	// Assign is true when this arrival completed the slot and a berth
	// assignment should be published.
	Assign bool
	// Supersedes is the prior assignment id being voided, empty if none. When
	// set, a void must be published before the replacement assignment.
	Supersedes string
	// Reason explains the transition, for the audit record.
	Reason string
}

// ErrOutsideWindow means the arrival's value date is too far from today to
// belong to any slot this client would still accept.
var ErrOutsideWindow = errors.New("slot: value date outside the late-arrival window")

// Arrival is the input to the state machine.
type Arrival struct {
	ArrivalID string
	ClientID  string
	Domain    string
	ValueDate string
	Side      string // registry.SideInternalGL or registry.SideExternalClient
}

// Store persists slots.
type Store interface {
	Get(ctx context.Context, k Key) (*Slot, error)
	Upsert(ctx context.Context, s *Slot) error
	DueBefore(ctx context.Context, t time.Time) ([]*Slot, error)
}

// Machine applies arrivals to slots.
type Machine struct {
	store    Store
	reg      *registry.Registry
	now      func() time.Time
	fallback int // late window used when a client does not set one
}

// NewMachine returns a Machine.
func NewMachine(store Store, reg *registry.Registry, fallbackWindowDays int) *Machine {
	if fallbackWindowDays <= 0 {
		fallbackWindowDays = 2
	}
	return &Machine{
		store: store, reg: reg, fallback: fallbackWindowDays,
		now: func() time.Time { return time.Now().UTC() },
	}
}

// SetClock replaces the time source, for tests.
func (m *Machine) SetClock(fn func() time.Time) { m.now = fn }

// WindowDays returns the late-arrival window for a client.
func (m *Machine) WindowDays(clientID string) int {
	if c, ok := m.reg.Client(clientID); ok && c.LateWindowDays > 0 {
		return c.LateWindowDays
	}
	return m.fallback
}

// Accepts reports whether a value date is close enough to now to be routed.
//
// This is what makes a late file bind to the correct historical slot (FR-14)
// instead of being forced onto today, which would silently reconcile Friday's
// trades against Monday's ledger.
func (m *Machine) Accepts(clientID, valueDate string) (bool, error) {
	vd, err := parseDate(valueDate)
	if err != nil {
		return false, err
	}
	cal, ok := m.reg.CalendarFor(clientID)
	if !ok {
		return false, fmt.Errorf("slot: no calendar for client %s", clientID)
	}
	window := m.WindowDays(clientID)
	today := truncate(m.now())
	earliest := cal.AddBusinessDays(today, -window)
	latest := cal.AddBusinessDays(today, window)
	return !vd.Before(earliest) && !vd.After(latest), nil
}

// Apply routes an arrival to its slot and returns what should happen next.
func (m *Machine) Apply(ctx context.Context, a Arrival) (Outcome, error) {
	ok, err := m.Accepts(a.ClientID, a.ValueDate)
	if err != nil {
		return Outcome{}, err
	}
	if !ok {
		return Outcome{}, fmt.Errorf("%w: %s for %s (window %d business days)",
			ErrOutsideWindow, a.ValueDate, a.ClientID, m.WindowDays(a.ClientID))
	}

	client, ok := m.reg.Client(a.ClientID)
	if !ok {
		return Outcome{}, fmt.Errorf("slot: unknown client %s", a.ClientID)
	}
	exp, ok := client.ExpectationFor(a.Domain)
	if !ok {
		return Outcome{}, fmt.Errorf("slot: client %s has no expectation for domain %s",
			a.ClientID, a.Domain)
	}

	key := Key{ClientID: a.ClientID, Domain: a.Domain, ValueDate: a.ValueDate}
	s, err := m.store.Get(ctx, key)
	if err != nil {
		return Outcome{}, err
	}
	if s == nil {
		deadline, err := m.deadlineFor(a.ClientID, a.ValueDate)
		if err != nil {
			return Outcome{}, err
		}
		s = &Slot{Key: key, State: StateOpen, ExpectationID: exp.ID,
			OpenedAt: m.now(), Deadline: deadline}
	}

	out := Outcome{Slot: s}
	replacing := s.State == StateAssigned

	switch a.Side {
	case registry.SideInternalGL:
		out.Reason = describeSide(s.Side1Arrival, "internal GL")
		s.Side1Arrival = a.ArrivalID
	case registry.SideExternalClient:
		out.Reason = describeSide(s.Side2Arrival, "external client")
		s.Side2Arrival = a.ArrivalID
	default:
		return Outcome{}, fmt.Errorf("slot: unknown side %q", a.Side)
	}

	switch {
	case s.Complete() && replacing:
		// A correction for a slot that already dispatched. The prior
		// assignment must be voided before the replacement is published, and
		// because both messages share the slot key they cannot be reordered.
		out.Supersedes = s.AssignmentID
		out.Assign = true
		s.State = StateAssigned
		out.Reason = "correction supersedes a dispatched assignment"
	case s.Complete():
		out.Assign = true
		s.State = StateAssigned
	default:
		s.State = StatePartial
	}

	if err := m.store.Upsert(ctx, s); err != nil {
		return Outcome{}, err
	}
	return out, nil
}

// RecordAssignment stamps the assignment id onto the slot once published.
func (m *Machine) RecordAssignment(ctx context.Context, k Key, assignmentID string) error {
	s, err := m.store.Get(ctx, k)
	if err != nil {
		return err
	}
	if s == nil {
		return fmt.Errorf("slot: %s not found when recording assignment", k)
	}
	s.AssignmentID = assignmentID
	s.State = StateAssigned
	return m.store.Upsert(ctx, s)
}

// Overdue returns slots whose deadline has passed without both sides arriving,
// and marks them MISSING so the alert fires once rather than on every sweep.
func (m *Machine) Overdue(ctx context.Context) ([]*Slot, error) {
	due, err := m.store.DueBefore(ctx, m.now())
	if err != nil {
		return nil, err
	}
	var out []*Slot
	for _, s := range due {
		if s.State == StateAssigned || s.State == StateMissing {
			continue
		}
		s.State = StateMissing
		if err := m.store.Upsert(ctx, s); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, nil
}

// MissingSide reports which side of an incomplete slot never arrived.
func MissingSide(s *Slot) string {
	switch {
	case s.Side1Arrival == "":
		return registry.SideInternalGL
	case s.Side2Arrival == "":
		return registry.SideExternalClient
	default:
		return ""
	}
}

func (m *Machine) deadlineFor(clientID, valueDate string) (time.Time, error) {
	vd, err := parseDate(valueDate)
	if err != nil {
		return time.Time{}, err
	}
	cal, ok := m.reg.CalendarFor(clientID)
	if !ok {
		return time.Time{}, fmt.Errorf("slot: no calendar for client %s", clientID)
	}
	// The slot stays open for the full late window past its value date, then
	// becomes a missing-file alert. Anchoring on the value date rather than on
	// arrival time means a slot opened by an early file still closes on
	// schedule.
	return cal.AddBusinessDays(vd, m.WindowDays(clientID)).Add(23*time.Hour + 59*time.Minute), nil
}

func describeSide(existing, label string) string {
	if existing == "" {
		return "first " + label + " file for this slot"
	}
	return "replacement " + label + " file for this slot"
}

func parseDate(s string) (time.Time, error) {
	d, err := time.Parse("2006-01-02", s)
	if err != nil {
		return time.Time{}, fmt.Errorf("slot: %q is not a YYYY-MM-DD value date: %w", s, err)
	}
	return d, nil
}

func truncate(t time.Time) time.Time {
	return time.Date(t.Year(), t.Month(), t.Day(), 0, 0, 0, 0, time.UTC)
}

// --- SQL store -------------------------------------------------------------

// SQLStore persists slots in Postgres.
type SQLStore struct{ db *sql.DB }

// NewSQLStore returns a Store over db.
func NewSQLStore(db *sql.DB) *SQLStore { return &SQLStore{db: db} }

// Get returns a slot, or nil if it does not exist.
func (s *SQLStore) Get(ctx context.Context, k Key) (*Slot, error) {
	const q = `
		SELECT state, expectation_id, COALESCE(side_1_arrival,''), COALESCE(side_2_arrival,''),
		       COALESCE(assignment_id,''), opened_at, deadline
		FROM slot WHERE client_id=$1 AND domain=$2 AND value_date=$3`
	var out Slot
	out.Key = k
	var state string
	err := s.db.QueryRowContext(ctx, q, k.ClientID, k.Domain, k.ValueDate).Scan(
		&state, &out.ExpectationID, &out.Side1Arrival, &out.Side2Arrival,
		&out.AssignmentID, &out.OpenedAt, &out.Deadline)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("slot: get %s: %w", k, err)
	}
	out.State = State(state)
	return &out, nil
}

// Upsert writes a slot.
func (s *SQLStore) Upsert(ctx context.Context, sl *Slot) error {
	const q = `
		INSERT INTO slot (client_id, domain, value_date, state, expectation_id,
		                  side_1_arrival, side_2_arrival, assignment_id, opened_at, deadline)
		VALUES ($1,$2,$3,$4,$5,NULLIF($6,''),NULLIF($7,''),NULLIF($8,''),$9,$10)
		ON CONFLICT (client_id, domain, value_date) DO UPDATE SET
		  state = EXCLUDED.state,
		  side_1_arrival = COALESCE(EXCLUDED.side_1_arrival, slot.side_1_arrival),
		  side_2_arrival = COALESCE(EXCLUDED.side_2_arrival, slot.side_2_arrival),
		  assignment_id = COALESCE(EXCLUDED.assignment_id, slot.assignment_id),
		  deadline = EXCLUDED.deadline`
	if _, err := s.db.ExecContext(ctx, q, sl.Key.ClientID, sl.Key.Domain, sl.Key.ValueDate,
		string(sl.State), sl.ExpectationID, sl.Side1Arrival, sl.Side2Arrival,
		sl.AssignmentID, sl.OpenedAt, sl.Deadline); err != nil {
		return fmt.Errorf("slot: upsert %s: %w", sl.Key, err)
	}
	return nil
}

// DueBefore returns slots whose deadline has passed.
func (s *SQLStore) DueBefore(ctx context.Context, t time.Time) ([]*Slot, error) {
	const q = `
		SELECT client_id, domain, to_char(value_date,'YYYY-MM-DD'), state, expectation_id,
		       COALESCE(side_1_arrival,''), COALESCE(side_2_arrival,''),
		       COALESCE(assignment_id,''), opened_at, deadline
		FROM slot WHERE deadline < $1 AND state NOT IN ('ASSIGNED','MISSING')`
	rows, err := s.db.QueryContext(ctx, q, t)
	if err != nil {
		return nil, fmt.Errorf("slot: due before: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var out []*Slot
	for rows.Next() {
		var sl Slot
		var state string
		if err := rows.Scan(&sl.Key.ClientID, &sl.Key.Domain, &sl.Key.ValueDate, &state,
			&sl.ExpectationID, &sl.Side1Arrival, &sl.Side2Arrival, &sl.AssignmentID,
			&sl.OpenedAt, &sl.Deadline); err != nil {
			return nil, fmt.Errorf("slot: scan: %w", err)
		}
		sl.State = State(state)
		out = append(out, &sl)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("slot: iterate: %w", err)
	}
	return out, nil
}
