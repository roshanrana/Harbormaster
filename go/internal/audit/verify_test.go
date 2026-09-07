package audit

import (
	"fmt"
	"testing"
	"time"
)

// chainOf builds a linked chain in memory with a fixed clock, so these tests
// need no database and produce the same hashes on every run.
func chainOf(t *testing.T, n int) []Record {
	t.Helper()
	at := time.Date(2026, 8, 31, 6, 0, 0, 0, time.UTC)
	prev := ""
	out := make([]Record, 0, n)
	for i := 0; i < n; i++ {
		r := Record{
			RecordID:     fmt.Sprintf("01TEST%020d", i),
			ArrivalID:    "arr-bench",
			At:           at.Add(time.Duration(i) * time.Second),
			Component:    "test",
			DecisionType: "STEP",
			InputsJSON:   fmt.Sprintf(`{"step":%d}`, i),
			OutcomeJSON:  `{"ok":true}`,
			Actor:        "system",
			PrevHash:     prev,
		}
		r.RecordHash = ComputeHash(r)
		prev = r.RecordHash
		out = append(out, r)
	}
	return out
}

func TestVerifyRecordsAcceptsAnIntactChain(t *testing.T) {
	if b := VerifyRecords("arr-bench", chainOf(t, 3)); b != nil {
		t.Fatalf("intact chain reported a break: %+v", b)
	}
}

func TestVerifyRecordsAcceptsAnEmptyChain(t *testing.T) {
	if b := VerifyRecords("arr-none", nil); b != nil {
		t.Fatalf("empty chain reported a break: %+v", b)
	}
}

func TestVerifyRecordsDetectsAnEditedOutcome(t *testing.T) {
	recs := chainOf(t, 3)
	recs[1].OutcomeJSON = `{"tampered":true}`
	b := VerifyRecords("arr-bench", recs)
	if b == nil {
		t.Fatal("edited outcome was not detected")
	}
	if b.Position != 1 || b.RecordID != recs[1].RecordID {
		t.Fatalf("break reported at the wrong record: %+v", b)
	}
}

func TestVerifyRecordsDetectsADeletedRecord(t *testing.T) {
	recs := chainOf(t, 3)
	recs = append(recs[:1], recs[2:]...)
	if b := VerifyRecords("arr-bench", recs); b == nil {
		t.Fatal("a deleted record left the chain looking valid")
	}
}

func TestVerifyRecordsDetectsARewrittenHash(t *testing.T) {
	// An attacker who edits a record and recomputes its own hash still breaks
	// the link from the record after it.
	recs := chainOf(t, 3)
	recs[1].Actor = "mallory"
	recs[1].RecordHash = ComputeHash(recs[1])
	b := VerifyRecords("arr-bench", recs)
	if b == nil {
		t.Fatal("rewritten hash was not detected")
	}
	if b.Position != 2 {
		t.Fatalf("expected the break at the successor record, got %+v", b)
	}
}
