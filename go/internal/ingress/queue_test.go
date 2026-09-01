package ingress

import (
	"context"
	"encoding/json"
	"os"
	"testing"
	"time"

	hmv1 "harbormaster.dev/hm/gen/hmv1"
	"harbormaster.dev/hm/internal/arrival"
	"harbormaster.dev/hm/internal/audit"
	"harbormaster.dev/hm/internal/bus"
	"harbormaster.dev/hm/internal/logging"
	"harbormaster.dev/hm/internal/store"
	"harbormaster.dev/hm/internal/store/objectstore"
)

func harness(t *testing.T) (*QueueConsumer, *bus.Memory) {
	t.Helper()
	dsn := os.Getenv("HM_TEST_POSTGRES_DSN")
	if dsn == "" {
		t.Skip("set HM_TEST_POSTGRES_DSN to run queue ingress tests")
	}
	db, err := store.Open(dsn)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	if _, err := db.ExecContext(ctx, `DROP TABLE IF EXISTS projection_offset, alert, assignment,
		review, template_mapping, audit_record, slot, arrival, schema_migration CASCADE`); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Migrate(ctx, db); err != nil {
		t.Fatal(err)
	}
	objects, err := objectstore.NewFS(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	b := bus.NewMemory(4)
	proc := &arrival.Processor{
		Store: objects, Recorder: arrival.NewSQLDeduper(db), Bus: b,
		Audit: audit.New(db), Log: logging.New("test"),
		Scanner: arrival.NewScanner(t.TempDir(), arrival.DefaultPolicy()),
	}
	t.Cleanup(func() { _ = db.Close(); _ = b.Close() })
	return &QueueConsumer{
		Bus: b, Processor: proc, Topic: "hm.ingress.json", Group: "test",
		Log: logging.New("test"), StagingDir: t.TempDir(),
	}, b
}

func msg(value string) bus.Message {
	return bus.Message{Topic: "hm.ingress.json", Key: "k", Value: []byte(value), Offset: 1}
}

const payload = `{"messageId":"M-1001","source":"NYSE","payload":{"records":[{"a":1}]}}`

func TestQueuePayloadBecomesAnOrdinaryArrival(t *testing.T) {
	q, b := harness(t)
	if err := q.handle(context.Background(), msg(payload)); err != nil {
		t.Fatal(err)
	}
	msgs := b.Messages(bus.TopicArrivalsRaw)
	if len(msgs) != 1 {
		t.Fatalf("want 1 arrival, got %d", len(msgs))
	}
	var raw hmv1.ArrivalRaw
	if err := bus.Decode(msgs[0].Value, &raw); err != nil {
		t.Fatal(err)
	}
	// The ingress label is the only thing that differs from a landed file.
	if raw.GetIngress() != arrival.IngressQueue {
		t.Fatalf("ingress = %q, want QUEUE", raw.GetIngress())
	}
	if len(raw.GetContentSha256()) != 64 {
		t.Fatal("queue payload was not hashed like a file")
	}
	if raw.GetOriginalName() != "NYSE_M-1001.json" {
		t.Fatalf("name = %q", raw.GetOriginalName())
	}
}

func TestRedeliveredMessageIsDeduplicatedByContent(t *testing.T) {
	// Recognised by content rather than by any broker delivery guarantee, so a
	// consumer restart cannot double-count a reconciliation.
	q, b := harness(t)
	ctx := context.Background()
	for i := 0; i < 3; i++ {
		if err := q.handle(ctx, msg(payload)); err != nil {
			t.Fatal(err)
		}
	}
	if got := len(b.Messages(bus.TopicArrivalsRaw)); got != 1 {
		t.Fatalf("redelivery produced %d arrivals, want 1", got)
	}
}

func TestMalformedPayloadIsSkippedNotRetriedForever(t *testing.T) {
	// It will never become valid, and blocking the partition on it would stop
	// every well-formed message behind it.
	q, b := harness(t)
	if err := q.handle(context.Background(), msg(`{"unclosed":`)); err != nil {
		t.Fatalf("malformed payload should be skipped, not returned as an error: %v", err)
	}
	if got := len(b.Messages(bus.TopicArrivalsRaw)); got != 0 {
		t.Fatalf("malformed payload produced %d arrivals", got)
	}
}

func TestMessageWithoutAnEnvelopeStillGetsAUniqueName(t *testing.T) {
	q, b := harness(t)
	m := bus.Message{Topic: "hm.ingress.json", Key: "k",
		Value: []byte(`{"records":[{"a":1}]}`), Partition: 2, Offset: 77}
	if err := q.handle(context.Background(), m); err != nil {
		t.Fatal(err)
	}
	var raw hmv1.ArrivalRaw
	if err := bus.Decode(b.Messages(bus.TopicArrivalsRaw)[0].Value, &raw); err != nil {
		t.Fatal(err)
	}
	if raw.GetOriginalName() != "hm.ingress.json_p2_o77.json" {
		t.Fatalf("fallback name = %q", raw.GetOriginalName())
	}
}

func TestFilenameIsSanitised(t *testing.T) {
	// Message ids come from an upstream system; they must not be able to
	// escape the staging directory.
	q, _ := harness(t)
	name := q.filename(msg(`{"messageId":"../../etc/passwd","source":"a/b"}`))
	for _, bad := range []string{"..", "/", "\\"} {
		if contains(name, bad) {
			t.Fatalf("unsafe filename %q", name)
		}
	}
}

func TestPayloadContentSurvivesStaging(t *testing.T) {
	q, _ := harness(t)
	candidate, err := q.stage("t.json", []byte(payload))
	if err != nil {
		t.Fatal(err)
	}
	body, err := os.ReadFile(candidate.Path)
	if err != nil {
		t.Fatal(err)
	}
	var decoded Envelope
	if err := json.Unmarshal(body, &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded.MessageID != "M-1001" {
		t.Fatalf("payload altered in staging: %s", body)
	}
	if time.Since(candidate.ModTime) > time.Minute {
		t.Fatal("staged candidate has a stale timestamp")
	}
}

func contains(haystack, needle string) bool {
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}
