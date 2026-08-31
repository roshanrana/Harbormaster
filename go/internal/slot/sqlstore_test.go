package slot

import (
	"context"
	"database/sql"
	"os"
	"testing"
	"time"

	"harbormaster.dev/hm/internal/store"
)

func sqlStore(t *testing.T) (*SQLStore, *sql.DB) {
	t.Helper()
	dsn := os.Getenv("HM_TEST_POSTGRES_DSN")
	if dsn == "" {
		t.Skip("set HM_TEST_POSTGRES_DSN to run slot store tests")
	}
	db, err := store.Open(dsn)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	if _, err := db.ExecContext(ctx, `DROP TABLE IF EXISTS review, template_mapping, audit_record, slot, arrival, schema_migration CASCADE`); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Migrate(ctx, db); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return NewSQLStore(db), db
}

func TestSQLStoreRoundTrip(t *testing.T) {
	st, _ := sqlStore(t)
	ctx := context.Background()
	k := Key{ClientID: "CLNT004", Domain: "TRADE", ValueDate: "2026-08-28"}

	if got, err := st.Get(ctx, k); err != nil || got != nil {
		t.Fatalf("expected no slot yet, got %v %v", got, err)
	}
	in := &Slot{Key: k, State: StatePartial, ExpectationID: "EXP-1",
		Side1Arrival: "a1", OpenedAt: time.Now().UTC(), Deadline: time.Now().UTC().Add(time.Hour)}
	if err := st.Upsert(ctx, in); err != nil {
		t.Fatal(err)
	}
	got, err := st.Get(ctx, k)
	if err != nil {
		t.Fatal(err)
	}
	if got.State != StatePartial || got.Side1Arrival != "a1" || got.Side2Arrival != "" {
		t.Fatalf("round trip lost data: %+v", got)
	}
}

func TestUpsertDoesNotClobberTheOtherSide(t *testing.T) {
	// Both sides are written by separate events. An upsert that blanked the
	// side it was not carrying would lose a file that had already arrived.
	st, _ := sqlStore(t)
	ctx := context.Background()
	k := Key{ClientID: "CLNT004", Domain: "TRADE", ValueDate: "2026-08-28"}
	now := time.Now().UTC()

	if err := st.Upsert(ctx, &Slot{Key: k, State: StatePartial, ExpectationID: "EXP-1",
		Side1Arrival: "gl-1", OpenedAt: now, Deadline: now.Add(time.Hour)}); err != nil {
		t.Fatal(err)
	}
	if err := st.Upsert(ctx, &Slot{Key: k, State: StateAssigned, ExpectationID: "EXP-1",
		Side2Arrival: "cl-1", OpenedAt: now, Deadline: now.Add(time.Hour)}); err != nil {
		t.Fatal(err)
	}
	got, _ := st.Get(ctx, k)
	if got.Side1Arrival != "gl-1" || got.Side2Arrival != "cl-1" {
		t.Fatalf("a side was lost: %+v", got)
	}
	if got.State != StateAssigned {
		t.Fatalf("state = %s", got.State)
	}
}

func TestDueBeforeExcludesAssignedAndMissing(t *testing.T) {
	st, _ := sqlStore(t)
	ctx := context.Background()
	past := time.Now().UTC().Add(-time.Hour)

	for _, tc := range []struct {
		date  string
		state State
	}{
		{"2026-08-24", StatePartial},
		{"2026-08-25", StateAssigned},
		{"2026-08-26", StateMissing},
		{"2026-08-27", StateOpen},
	} {
		if err := st.Upsert(ctx, &Slot{
			Key:   Key{ClientID: "CLNT004", Domain: "TRADE", ValueDate: tc.date},
			State: tc.state, ExpectationID: "EXP-1", OpenedAt: past, Deadline: past,
		}); err != nil {
			t.Fatal(err)
		}
	}
	due, err := st.DueBefore(ctx, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if len(due) != 2 {
		t.Fatalf("want 2 overdue slots, got %d", len(due))
	}
	for _, s := range due {
		if s.State == StateAssigned || s.State == StateMissing {
			t.Fatalf("terminal slot returned as overdue: %+v", s)
		}
		if s.Key.ValueDate == "" {
			t.Fatal("value date did not survive the round trip")
		}
	}
}
