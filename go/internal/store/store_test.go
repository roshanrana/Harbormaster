package store

import (
	"context"
	"database/sql"
	"os"
	"testing"
)

// dsn returns the test database, or skips. Integration tests must be skippable
// so `make check` stays runnable on a machine with no database.
func dsn(t *testing.T) string {
	t.Helper()
	v := os.Getenv("HM_TEST_POSTGRES_DSN")
	if v == "" {
		t.Skip("set HM_TEST_POSTGRES_DSN to run store tests")
	}
	return v
}

func freshDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := Open(dsn(t))
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	for _, stmt := range []string{
		`DROP TABLE IF EXISTS review, template_mapping, audit_record, slot, arrival, schema_migration CASCADE`,
	} {
		if _, err := db.ExecContext(ctx, stmt); err != nil {
			t.Fatal(err)
		}
	}
	t.Cleanup(func() { _ = db.Close() })
	return db
}

func TestLoadMigrationsRequiresBothHalves(t *testing.T) {
	ms, err := LoadMigrations()
	if err != nil {
		t.Fatal(err)
	}
	if len(ms) == 0 {
		t.Fatal("no migrations loaded")
	}
	for _, m := range ms {
		if m.Up == "" || m.Down == "" {
			t.Fatalf("migration %03d has no rollback path", m.Version)
		}
	}
}

func TestMigrateAppliesAllTables(t *testing.T) {
	db := freshDB(t)
	ctx := context.Background()
	applied, err := Migrate(ctx, db)
	if err != nil {
		t.Fatal(err)
	}
	if len(applied) == 0 {
		t.Fatal("expected at least one migration to apply")
	}
	for _, table := range []string{"arrival", "slot", "audit_record", "template_mapping", "review"} {
		var n int
		if err := db.QueryRowContext(ctx,
			`SELECT count(*) FROM information_schema.tables WHERE table_name = $1`, table).Scan(&n); err != nil {
			t.Fatal(err)
		}
		if n != 1 {
			t.Fatalf("table %q was not created", table)
		}
	}
}

func TestMigrateIsIdempotent(t *testing.T) {
	db := freshDB(t)
	ctx := context.Background()
	if _, err := Migrate(ctx, db); err != nil {
		t.Fatal(err)
	}
	second, err := Migrate(ctx, db)
	if err != nil {
		t.Fatalf("re-running migrations must be safe: %v", err)
	}
	if len(second) != 0 {
		t.Fatalf("second run should apply nothing, applied %v", second)
	}
}

func TestRollbackRevertsTheMostRecentMigration(t *testing.T) {
	db := freshDB(t)
	ctx := context.Background()
	applied, err := Migrate(ctx, db)
	if err != nil {
		t.Fatal(err)
	}
	latest := applied[len(applied)-1]

	v, err := Rollback(ctx, db)
	if err != nil {
		t.Fatal(err)
	}
	if v != latest {
		t.Fatalf("rolled back version %d, want the most recent (%d)", v, latest)
	}
	// The bookkeeping row must go with it, or a re-run would skip the
	// migration it just undid.
	var recorded int
	if err := db.QueryRowContext(ctx,
		`SELECT count(*) FROM schema_migration WHERE version = $1`, latest).Scan(&recorded); err != nil {
		t.Fatal(err)
	}
	if recorded != 0 {
		t.Fatal("rollback left its bookkeeping row behind")
	}
}

func TestRollingBackEveryMigrationRemovesTheSchema(t *testing.T) {
	db := freshDB(t)
	ctx := context.Background()
	applied, err := Migrate(ctx, db)
	if err != nil {
		t.Fatal(err)
	}
	for range applied {
		if _, err := Rollback(ctx, db); err != nil {
			t.Fatal(err)
		}
	}
	var n int
	if err := db.QueryRowContext(ctx,
		`SELECT count(*) FROM information_schema.tables WHERE table_name = 'arrival'`).Scan(&n); err != nil {
		t.Fatal(err)
	}
	if n != 0 {
		t.Fatal("unwinding every migration did not drop the schema")
	}
}

func TestRollbackOnAnEmptyDatabaseIsHarmless(t *testing.T) {
	db := freshDB(t)
	ctx := context.Background()
	if _, err := db.ExecContext(ctx, schemaTable); err != nil {
		t.Fatal(err)
	}
	v, err := Rollback(ctx, db)
	if err != nil {
		t.Fatalf("rolling back with nothing applied should be a no-op: %v", err)
	}
	if v != 0 {
		t.Fatalf("expected version 0, got %d", v)
	}
}

func TestRedeliveryUnderNewNameIsRecordableButDuplicateIsNot(t *testing.T) {
	// FR-6 and FR-7 in schema form: identical content under a *new* filename is
	// a distinct operational event, but the exact same file arriving twice must
	// be rejected by the database rather than relying on application code.
	db := freshDB(t)
	ctx := context.Background()
	if _, err := Migrate(ctx, db); err != nil {
		t.Fatal(err)
	}
	insert := `INSERT INTO arrival (arrival_id, content_sha256, original_name, ingress, uri, size_bytes, detected_at)
	           VALUES ($1,$2,$3,'FTP','fs:///x',10,NOW())`
	if _, err := db.ExecContext(ctx, insert, "a1", "deadbeef", "trades_A.csv"); err != nil {
		t.Fatal(err)
	}
	if _, err := db.ExecContext(ctx, insert, "a2", "deadbeef", "trades_B.csv"); err != nil {
		t.Fatalf("same content under a new name should be recordable: %v", err)
	}
	if _, err := db.ExecContext(ctx, insert, "a3", "deadbeef", "trades_A.csv"); err == nil {
		t.Fatal("exact duplicate should violate the uniqueness constraint")
	}
}

func TestSlotPrimaryKeyIsSlotIdentity(t *testing.T) {
	db := freshDB(t)
	ctx := context.Background()
	if _, err := Migrate(ctx, db); err != nil {
		t.Fatal(err)
	}
	ins := `INSERT INTO slot (client_id, domain, value_date, state, expectation_id, opened_at, deadline)
	        VALUES ($1,$2,$3,'OPEN','EXP-1',NOW(),NOW())`
	if _, err := db.ExecContext(ctx, ins, "CLNT004", "TRADE", "2026-08-28"); err != nil {
		t.Fatal(err)
	}
	if _, err := db.ExecContext(ctx, ins, "CLNT004", "TRADE", "2026-08-28"); err == nil {
		t.Fatal("a slot must be unique per client, domain and value date")
	}
	// A different value date is a different slot, which is what makes late
	// arrivals bind to history rather than colliding with today.
	if _, err := db.ExecContext(ctx, ins, "CLNT004", "TRADE", "2026-08-27"); err != nil {
		t.Fatalf("different value date must be a distinct slot: %v", err)
	}
}
