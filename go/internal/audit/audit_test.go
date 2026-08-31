package audit

import (
	"context"
	"database/sql"
	"os"
	"testing"
	"time"

	"harbormaster.dev/hm/internal/store"
)

func testDB(t *testing.T) *sql.DB {
	t.Helper()
	dsn := os.Getenv("HM_TEST_POSTGRES_DSN")
	if dsn == "" {
		t.Skip("set HM_TEST_POSTGRES_DSN to run audit tests")
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
	return db
}

func TestChainVerifies(t *testing.T) {
	db := testDB(t)
	c := New(db)
	ctx := context.Background()
	for i, dt := range []string{"ARRIVAL_DETECTED", "CLASSIFIED", "BERTH_ASSIGNED"} {
		if err := c.Append(ctx, Entry{
			ArrivalID: "arr-1", Component: "test", DecisionType: dt,
			Inputs: map[string]any{"step": i}, Outcome: map[string]any{"ok": true},
		}); err != nil {
			t.Fatal(err)
		}
	}
	b, err := c.Verify(ctx, "arr-1")
	if err != nil {
		t.Fatal(err)
	}
	if b != nil {
		t.Fatalf("unexpected break: %+v", b)
	}
	recs, _ := c.Read(ctx, "arr-1")
	if len(recs) != 3 {
		t.Fatalf("want 3 records, got %d", len(recs))
	}
	if recs[0].PrevHash != "" {
		t.Fatal("first record should have an empty prev_hash")
	}
	if recs[1].PrevHash != recs[0].RecordHash || recs[2].PrevHash != recs[1].RecordHash {
		t.Fatal("records are not chained")
	}
}

func TestTamperedOutcomeIsDetected(t *testing.T) {
	// The whole point of the chain. Someone edits a decision after the fact;
	// verification must find it and say which record.
	db := testDB(t)
	c := New(db)
	ctx := context.Background()
	for _, dt := range []string{"A", "B", "C"} {
		if err := c.Append(ctx, Entry{ArrivalID: "arr-2", Component: "test", DecisionType: dt}); err != nil {
			t.Fatal(err)
		}
	}
	recs, _ := c.Read(ctx, "arr-2")
	if _, err := db.ExecContext(ctx,
		`UPDATE audit_record SET outcome = '{"tampered":true}' WHERE record_id = $1`,
		recs[1].RecordID); err != nil {
		t.Fatal(err)
	}
	b, err := c.Verify(ctx, "arr-2")
	if err != nil {
		t.Fatal(err)
	}
	if b == nil {
		t.Fatal("tampering was not detected")
	}
	if b.RecordID != recs[1].RecordID {
		t.Fatalf("break reported at the wrong record: %+v", b)
	}
}

func TestDeletedRecordIsDetected(t *testing.T) {
	db := testDB(t)
	c := New(db)
	ctx := context.Background()
	for _, dt := range []string{"A", "B", "C"} {
		if err := c.Append(ctx, Entry{ArrivalID: "arr-3", Component: "test", DecisionType: dt}); err != nil {
			t.Fatal(err)
		}
	}
	recs, _ := c.Read(ctx, "arr-3")
	if _, err := db.ExecContext(ctx, `DELETE FROM audit_record WHERE record_id = $1`, recs[1].RecordID); err != nil {
		t.Fatal(err)
	}
	b, err := c.Verify(ctx, "arr-3")
	if err != nil {
		t.Fatal(err)
	}
	if b == nil {
		t.Fatal("a deleted record left the chain looking valid")
	}
}

func TestChainsAreIndependentPerArrival(t *testing.T) {
	db := testDB(t)
	c := New(db)
	ctx := context.Background()
	for _, id := range []string{"arr-a", "arr-b"} {
		for _, dt := range []string{"X", "Y"} {
			if err := c.Append(ctx, Entry{ArrivalID: id, Component: "test", DecisionType: dt}); err != nil {
				t.Fatal(err)
			}
		}
	}
	// Breaking one arrival's chain must not implicate the other.
	recs, _ := c.Read(ctx, "arr-a")
	if _, err := db.ExecContext(ctx, `UPDATE audit_record SET actor='mallory' WHERE record_id=$1`, recs[0].RecordID); err != nil {
		t.Fatal(err)
	}
	breaks, err := c.VerifyAll(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(breaks) != 1 || breaks[0].ArrivalID != "arr-a" {
		t.Fatalf("expected exactly one break on arr-a, got %+v", breaks)
	}
}

func TestActorDefaultsToSystem(t *testing.T) {
	db := testDB(t)
	c := New(db)
	ctx := context.Background()
	if err := c.Append(ctx, Entry{ArrivalID: "arr-4", Component: "test", DecisionType: "A"}); err != nil {
		t.Fatal(err)
	}
	recs, _ := c.Read(ctx, "arr-4")
	if recs[0].Actor != "system" {
		t.Fatalf("actor = %q, want system", recs[0].Actor)
	}
}

func TestHashIsStableAcrossReads(t *testing.T) {
	// Guards the storage-format decision: inputs and outcome are TEXT, not
	// JSONB, so what we hash is byte-identical to what we read back.
	db := testDB(t)
	c := New(db)
	c.SetClock(func() time.Time { return time.Date(2026, 8, 31, 6, 0, 0, 0, time.UTC) })
	ctx := context.Background()
	if err := c.Append(ctx, Entry{
		ArrivalID: "arr-5", Component: "test", DecisionType: "A",
		Inputs: map[string]any{"z": 1, "a": 2, "m": "x"},
	}); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 3; i++ {
		b, err := c.Verify(ctx, "arr-5")
		if err != nil {
			t.Fatal(err)
		}
		if b != nil {
			t.Fatalf("hash unstable on read %d: %+v", i, b)
		}
	}
}
