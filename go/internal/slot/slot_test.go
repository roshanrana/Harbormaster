package slot

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"harbormaster.dev/hm/internal/registry"
)

// memStore keeps the state machine testable without a database.
type memStore struct{ slots map[string]*Slot }

func newMemStore() *memStore { return &memStore{slots: map[string]*Slot{}} }

func (m *memStore) Get(_ context.Context, k Key) (*Slot, error) {
	s, ok := m.slots[k.String()]
	if !ok {
		return nil, nil
	}
	cp := *s
	return &cp, nil
}

func (m *memStore) Upsert(_ context.Context, s *Slot) error {
	cp := *s
	m.slots[s.Key.String()] = &cp
	return nil
}

func (m *memStore) DueBefore(_ context.Context, t time.Time) ([]*Slot, error) {
	var out []*Slot
	for _, s := range m.slots {
		if s.Deadline.Before(t) && s.State != StateAssigned && s.State != StateMissing {
			cp := *s
			out = append(out, &cp)
		}
	}
	return out, nil
}

func day(s string) time.Time {
	d, _ := time.Parse("2006-01-02", s)
	return d
}

// Monday 2026-08-31. The preceding Friday is the 28th, and the 29th/30th are
// the weekend, which is what makes this a useful "today" for late arrivals.
const today = "2026-08-31"

func machine(t *testing.T) (*Machine, *memStore) {
	t.Helper()
	reg, err := registry.Load(filepath.Join("..", "..", "..", "config"))
	if err != nil {
		t.Fatal(err)
	}
	st := newMemStore()
	m := NewMachine(st, reg, 2)
	m.SetClock(func() time.Time { return day(today).Add(9 * time.Hour) })
	return m, st
}

func gl(id, date string) Arrival {
	return Arrival{ArrivalID: id, ClientID: "CLNT004", Domain: "TRADE",
		ValueDate: date, Side: registry.SideInternalGL}
}

func client(id, date string) Arrival {
	return Arrival{ArrivalID: id, ClientID: "CLNT004", Domain: "TRADE",
		ValueDate: date, Side: registry.SideExternalClient}
}

func TestFirstArrivalOpensPartialSlot(t *testing.T) {
	m, _ := machine(t)
	out, err := m.Apply(context.Background(), gl("a1", today))
	if err != nil {
		t.Fatal(err)
	}
	if out.Assign {
		t.Fatal("a single side should not produce an assignment")
	}
	if out.Slot.State != StatePartial {
		t.Fatalf("state = %s, want PARTIAL", out.Slot.State)
	}
	if out.Slot.ExpectationID != "EXP-CLNT004-TRADE" {
		t.Fatalf("expectation = %q", out.Slot.ExpectationID)
	}
}

func TestBothSidesCompleteTheSlot(t *testing.T) {
	m, _ := machine(t)
	ctx := context.Background()
	if _, err := m.Apply(ctx, gl("a1", today)); err != nil {
		t.Fatal(err)
	}
	out, err := m.Apply(ctx, client("a2", today))
	if err != nil {
		t.Fatal(err)
	}
	if !out.Assign {
		t.Fatal("both sides present should assign")
	}
	if out.Slot.State != StateAssigned || out.Supersedes != "" {
		t.Fatalf("state=%s supersedes=%q", out.Slot.State, out.Supersedes)
	}
}

func TestSidesMayArriveInEitherOrder(t *testing.T) {
	m, _ := machine(t)
	ctx := context.Background()
	if _, err := m.Apply(ctx, client("a1", today)); err != nil {
		t.Fatal(err)
	}
	out, _ := m.Apply(ctx, gl("a2", today))
	if !out.Assign {
		t.Fatal("client-first ordering should still assign")
	}
}

func TestLateFileBindsToItsHistoricalSlot(t *testing.T) {
	// FR-14, the reason the project exists. A file landing Monday whose
	// contents belong to Friday must reconcile against Friday's ledger.
	m, st := machine(t)
	ctx := context.Background()
	if _, err := m.Apply(ctx, gl("gl-fri", "2026-08-28")); err != nil {
		t.Fatal(err)
	}
	out, err := m.Apply(ctx, client("cl-fri", "2026-08-28"))
	if err != nil {
		t.Fatal(err)
	}
	if !out.Assign {
		t.Fatal("late arrival did not complete Friday's slot")
	}
	if _, exists := st.slots["CLNT004:TRADE:2026-08-31"]; exists {
		t.Fatal("late arrival leaked into today's slot")
	}
}

func TestWindowIsMeasuredInBusinessDays(t *testing.T) {
	// T-2 from Monday is the previous Thursday. Counting calendar days would
	// stop at Saturday and reject a perfectly ordinary Thursday file.
	m, _ := machine(t)
	for _, date := range []string{"2026-08-27", "2026-08-28", "2026-08-31", "2026-09-01", "2026-09-02"} {
		ok, err := m.Accepts("CLNT004", date)
		if err != nil {
			t.Fatal(err)
		}
		if !ok {
			t.Fatalf("%s should be inside the T+/-2 business-day window", date)
		}
	}
}

func TestFileOutsideTheWindowIsRejected(t *testing.T) {
	m, _ := machine(t)
	_, err := m.Apply(context.Background(), gl("old", "2026-08-20"))
	if !errors.Is(err, ErrOutsideWindow) {
		t.Fatalf("want ErrOutsideWindow, got %v", err)
	}
}

func TestPerClientWindowOverrideIsHonoured(t *testing.T) {
	// CLNT023 sets late_window_days: 3 because their files land after the
	// London close.
	m, _ := machine(t)
	if got := m.WindowDays("CLNT023"); got != 3 {
		t.Fatalf("CLNT023 window = %d, want 3", got)
	}
	if got := m.WindowDays("CLNT004"); got != 2 {
		t.Fatalf("CLNT004 window = %d, want 2", got)
	}
}

func TestCorrectionSupersedesADispatchedAssignment(t *testing.T) {
	// FR-8 and FR-9. The prior assignment id must be carried so a void can be
	// published before the replacement.
	m, _ := machine(t)
	ctx := context.Background()
	_, _ = m.Apply(ctx, gl("a1", today))
	out, _ := m.Apply(ctx, client("a2", today))
	if !out.Assign {
		t.Fatal("setup did not assign")
	}
	if err := m.RecordAssignment(ctx, out.Slot.Key, "asg-001"); err != nil {
		t.Fatal(err)
	}

	corrected, err := m.Apply(ctx, client("a3-corrected", today))
	if err != nil {
		t.Fatal(err)
	}
	if !corrected.Assign {
		t.Fatal("correction should produce a replacement assignment")
	}
	if corrected.Supersedes != "asg-001" {
		t.Fatalf("supersedes = %q, want asg-001", corrected.Supersedes)
	}
	if corrected.Slot.Side2Arrival != "a3-corrected" {
		t.Fatal("corrected arrival was not recorded on the slot")
	}
}

func TestReplacementBeforeDispatchDoesNotSupersede(t *testing.T) {
	// A second file while the slot is still PARTIAL just replaces the side.
	// Nothing has been dispatched, so there is nothing to void.
	m, _ := machine(t)
	ctx := context.Background()
	_, _ = m.Apply(ctx, client("a1", today))
	out, err := m.Apply(ctx, client("a2", today))
	if err != nil {
		t.Fatal(err)
	}
	if out.Supersedes != "" {
		t.Fatalf("nothing was dispatched, supersedes should be empty, got %q", out.Supersedes)
	}
	if out.Reason != "replacement external client file for this slot" {
		t.Fatalf("reason = %q", out.Reason)
	}
}

func TestSlotKeyIsThePartitionKey(t *testing.T) {
	// Ordering of a void and its replacement depends on both sharing this
	// key, so its format is part of the contract (ADR-005).
	k := Key{ClientID: "CLNT004", Domain: "TRADE", ValueDate: "2026-08-28"}
	if k.String() != "CLNT004:TRADE:2026-08-28" {
		t.Fatalf("key format changed: %s", k.String())
	}
}

func TestOverdueSlotsAreReportedOnceAndMarkedMissing(t *testing.T) {
	m, _ := machine(t)
	ctx := context.Background()
	if _, err := m.Apply(ctx, gl("only-one-side", "2026-08-28")); err != nil {
		t.Fatal(err)
	}
	// Jump past the deadline.
	m.SetClock(func() time.Time { return day("2026-09-10") })

	first, err := m.Overdue(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(first) != 1 {
		t.Fatalf("want 1 overdue slot, got %d", len(first))
	}
	if MissingSide(first[0]) != registry.SideExternalClient {
		t.Fatalf("missing side = %s", MissingSide(first[0]))
	}
	second, err := m.Overdue(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(second) != 0 {
		t.Fatal("an overdue slot alerted twice")
	}
}

func TestAssignedSlotNeverAlerts(t *testing.T) {
	m, _ := machine(t)
	ctx := context.Background()
	_, _ = m.Apply(ctx, gl("a1", "2026-08-28"))
	_, _ = m.Apply(ctx, client("a2", "2026-08-28"))
	m.SetClock(func() time.Time { return day("2026-09-10") })
	overdue, err := m.Overdue(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(overdue) != 0 {
		t.Fatal("a completed slot raised a missing-file alert")
	}
}

func TestUnknownClientAndDomainAreRejected(t *testing.T) {
	m, _ := machine(t)
	ctx := context.Background()
	_, err := m.Apply(ctx, Arrival{ArrivalID: "x", ClientID: "NOPE", Domain: "TRADE",
		ValueDate: today, Side: registry.SideInternalGL})
	if err == nil {
		t.Fatal("unknown client was accepted")
	}
	_, err = m.Apply(ctx, Arrival{ArrivalID: "x", ClientID: "CLNT004", Domain: "CASH",
		ValueDate: today, Side: registry.SideInternalGL})
	if err == nil {
		t.Fatal("CLNT004 has no CASH expectation; it should be rejected")
	}
}

func TestMalformedValueDateIsRejected(t *testing.T) {
	m, _ := machine(t)
	if _, err := m.Apply(context.Background(), gl("x", "31/08/2026")); err == nil {
		t.Fatal("a non-ISO value date was accepted")
	}
}
