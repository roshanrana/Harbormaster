package arrival

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"testing"
	"time"

	hmv1 "harbormaster.dev/hm/gen/hmv1"
	"harbormaster.dev/hm/internal/audit"
	"harbormaster.dev/hm/internal/bus"
	"harbormaster.dev/hm/internal/logging"
	"harbormaster.dev/hm/internal/store"
	"harbormaster.dev/hm/internal/store/objectstore"
)

func harness(t *testing.T) (*Processor, *bus.Memory, string, *sql.DB) {
	t.Helper()
	dsn := os.Getenv("HM_TEST_POSTGRES_DSN")
	if dsn == "" {
		t.Skip("set HM_TEST_POSTGRES_DSN to run processor tests")
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
	landing := t.TempDir()
	objects, err := objectstore.NewFS(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	b := bus.NewMemory(6)
	p := &Processor{
		Store: objects, Recorder: NewSQLDeduper(db), Bus: b,
		Audit: audit.New(db), Log: logging.New("test"),
		Scanner: NewScanner(landing, DefaultPolicy()),
	}
	t.Cleanup(func() { _ = db.Close(); _ = b.Close() })
	return p, b, landing, db
}

func drop(t *testing.T, dir, name, body string) Candidate {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return Candidate{Path: path, Name: name, Size: int64(len(body)),
		ModTime: time.Now(), StabilityMS: 5000}
}

func TestNewArrivalIsStoredRecordedAndPublished(t *testing.T) {
	p, b, landing, db := harness(t)
	ctx := context.Background()
	c := drop(t, landing, "MCP_TRD_20260828.csv", "TradeID,Qty,Price\nT1,100,42.5\n")

	if err := p.Handle(ctx, c); err != nil {
		t.Fatal(err)
	}

	msgs := b.Messages(bus.TopicArrivalsRaw)
	if len(msgs) != 1 {
		t.Fatalf("want 1 published message, got %d", len(msgs))
	}
	var raw hmv1.ArrivalRaw
	if err := bus.Decode(msgs[0].Value, &raw); err != nil {
		t.Fatal(err)
	}
	if raw.GetOriginalName() != c.Name {
		t.Fatalf("original_name = %q", raw.GetOriginalName())
	}
	if len(raw.GetContentSha256()) != 64 {
		t.Fatalf("expected a hex sha256, got %q", raw.GetContentSha256())
	}
	if raw.GetStabilityMs() != 5000 {
		t.Fatal("stability duration was not carried through")
	}
	// The message key is the content hash, which is what makes the downstream
	// consumer idempotent under redelivery.
	if msgs[0].Key != raw.GetContentSha256() {
		t.Fatal("message key is not the content hash")
	}

	var n int
	if err := db.QueryRow(`SELECT count(*) FROM arrival`).Scan(&n); err != nil || n != 1 {
		t.Fatalf("arrival row count = %d (%v)", n, err)
	}
	// The payload must be retrievable from the object store for replay.
	rc, err := p.Store.Get(ctx, raw.GetUri())
	if err != nil {
		t.Fatalf("stored payload not retrievable: %v", err)
	}
	_ = rc.Close()
}

func TestExactDuplicateIsSuppressedAndNotRepublished(t *testing.T) {
	p, b, landing, _ := harness(t)
	ctx := context.Background()
	body := "TradeID,Qty\nT1,100\n"
	c := drop(t, landing, "same.csv", body)

	if err := p.Handle(ctx, c); err != nil {
		t.Fatal(err)
	}
	if err := p.Handle(ctx, c); err != nil {
		t.Fatal(err)
	}
	if got := len(b.Messages(bus.TopicArrivalsRaw)); got != 1 {
		t.Fatalf("duplicate produced %d messages, want 1", got)
	}
}

func TestRedeliveryUnderNewNameIsSuppressedButAudited(t *testing.T) {
	// FR-7. The file is not reprocessed, but the fact that a client resent it
	// under a new name is recorded: that usually means a broken scheduler.
	p, b, landing, db := harness(t)
	ctx := context.Background()
	body := "TradeID,Qty\nT1,100\n"

	if err := p.Handle(ctx, drop(t, landing, "trades_A.csv", body)); err != nil {
		t.Fatal(err)
	}
	if err := p.Handle(ctx, drop(t, landing, "trades_B.csv", body)); err != nil {
		t.Fatal(err)
	}

	if got := len(b.Messages(bus.TopicArrivalsRaw)); got != 1 {
		t.Fatalf("redelivery produced %d messages, want 1", got)
	}
	var decisionType, outcome string
	if err := db.QueryRow(
		`SELECT decision_type, outcome FROM audit_record WHERE decision_type = 'ARRIVAL_SUPPRESSED'`,
	).Scan(&decisionType, &outcome); err != nil {
		t.Fatalf("suppression was not audited: %v", err)
	}
	if !contains(outcome, "REDELIVERY") {
		t.Fatalf("expected a REDELIVERY verdict, got %s", outcome)
	}
}

func TestDifferentContentSameNameIsANewArrival(t *testing.T) {
	// A correction usually arrives under the identical filename. It must not
	// be mistaken for a duplicate.
	p, b, landing, _ := harness(t)
	ctx := context.Background()
	if err := p.Handle(ctx, drop(t, landing, "trades.csv", "TradeID,Qty\nT1,100\n")); err != nil {
		t.Fatal(err)
	}
	if err := p.Handle(ctx, drop(t, landing, "trades.csv", "TradeID,Qty\nT1,250\n")); err != nil {
		t.Fatal(err)
	}
	if got := len(b.Messages(bus.TopicArrivalsRaw)); got != 2 {
		t.Fatalf("corrected file produced %d messages, want 2", got)
	}
}

func TestArrivalIsAudited(t *testing.T) {
	p, _, landing, db := harness(t)
	ctx := context.Background()
	if err := p.Handle(ctx, drop(t, landing, "trades.csv", "a,b\n1,2\n")); err != nil {
		t.Fatal(err)
	}
	var n int
	if err := db.QueryRow(
		`SELECT count(*) FROM audit_record WHERE decision_type = 'ARRIVAL_DETECTED'`).Scan(&n); err != nil {
		t.Fatal(err)
	}
	if n != 1 {
		t.Fatalf("want 1 audit record, got %d", n)
	}
	breaks, err := audit.New(db).VerifyAll(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(breaks) != 0 {
		t.Fatalf("audit chain broken: %+v", breaks)
	}
}

func contains(haystack, needle string) bool {
	return len(haystack) >= len(needle) && (func() bool {
		for i := 0; i+len(needle) <= len(haystack); i++ {
			if haystack[i:i+len(needle)] == needle {
				return true
			}
		}
		return false
	})()
}
