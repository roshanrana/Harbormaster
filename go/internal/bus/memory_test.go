package bus

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	hmv1 "harbormaster.dev/hm/gen/hmv1"
)

func TestPerKeyOrderingIsPreserved(t *testing.T) {
	// The property the whole supersession design rests on (ADR-005): messages
	// sharing a slot key are delivered in publish order.
	b := NewMemory(8)
	defer b.Close()

	key := SlotKey("CLNT004", "TRADE", "2026-08-28")
	const n = 200
	ctx := context.Background()
	for i := 0; i < n; i++ {
		if err := b.Publish(ctx, Message{Topic: TopicBerthAssigned, Key: key,
			Value: []byte(fmt.Sprintf("%d", i))}); err != nil {
			t.Fatal(err)
		}
	}

	got := b.Messages(TopicBerthAssigned)
	if len(got) != n {
		t.Fatalf("want %d messages, got %d", n, len(got))
	}
	for i, m := range got {
		if string(m.Value) != fmt.Sprintf("%d", i) {
			t.Fatalf("ordering broken at %d: got %q", i, m.Value)
		}
	}
}

func TestDifferentKeysMayUseDifferentPartitions(t *testing.T) {
	// A fake that put everything in one partition would hide real ordering
	// bugs, so assert the fake actually spreads keys.
	b := NewMemory(8)
	defer b.Close()
	seen := map[int32]bool{}
	for i := 0; i < 64; i++ {
		seen[b.partitionFor(SlotKey("CLNT", "TRADE", fmt.Sprintf("2026-01-%02d", i%28+1)))] = true
	}
	if len(seen) < 2 {
		t.Fatalf("expected keys to spread across partitions, got %d", len(seen))
	}
}

func TestSameSlotKeyAlwaysSamePartition(t *testing.T) {
	b := NewMemory(8)
	defer b.Close()
	k := SlotKey("CLNT004", "TRADE", "2026-08-28")
	first := b.partitionFor(k)
	for i := 0; i < 100; i++ {
		if b.partitionFor(k) != first {
			t.Fatal("partition assignment is not stable for a key")
		}
	}
}

func TestConsumerReceivesPublished(t *testing.T) {
	b := NewMemory(4)
	defer b.Close()
	c, err := b.NewConsumer("g1", TopicArrivalsRaw)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	var mu sync.Mutex
	var got []string
	done := make(chan struct{})
	go func() {
		defer close(done)
		_ = c.Consume(ctx, func(_ context.Context, m Message) error {
			mu.Lock()
			got = append(got, string(m.Value))
			if len(got) == 3 {
				cancel()
			}
			mu.Unlock()
			return nil
		})
	}()

	for _, v := range []string{"a", "b", "c"} {
		if err := b.Publish(context.Background(), Message{Topic: TopicArrivalsRaw, Key: "k", Value: []byte(v)}); err != nil {
			t.Fatal(err)
		}
	}
	<-done
	mu.Lock()
	defer mu.Unlock()
	if len(got) != 3 || got[0] != "a" || got[2] != "c" {
		t.Fatalf("unexpected delivery: %v", got)
	}
}

func TestConsumerReplaysHistory(t *testing.T) {
	b := NewMemory(2)
	defer b.Close()
	_ = b.Publish(context.Background(), Message{Topic: TopicArrivalsRaw, Key: "k", Value: []byte("early")})

	c, err := b.NewConsumer("late", TopicArrivalsRaw)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	var got string
	_ = c.Consume(ctx, func(_ context.Context, m Message) error {
		got = string(m.Value)
		cancel()
		return nil
	})
	if got != "early" {
		t.Fatalf("history not replayed, got %q", got)
	}
}

func TestCodecRoundTrip(t *testing.T) {
	in := &hmv1.BerthAssigned{
		AssignmentId: "asg-1", ClientId: "CLNT004", ValueDate: "2026-08-28",
		Domain: hmv1.ProductDomain_PRODUCT_DOMAIN_TRADE, Confidence: 0.93,
	}
	b, err := Encode(in)
	if err != nil {
		t.Fatal(err)
	}
	var out hmv1.BerthAssigned
	if err := Decode(b, &out); err != nil {
		t.Fatal(err)
	}
	if out.GetAssignmentId() != "asg-1" || out.GetValueDate() != "2026-08-28" {
		t.Fatalf("round trip lost data: %+v", &out)
	}
}

func TestDecodeToleratesUnknownFields(t *testing.T) {
	// A consumer built against an older contract must not break when a
	// producer adds a field.
	var out hmv1.BerthAssigned
	if err := Decode([]byte(`{"assignmentId":"a","brandNewField":42}`), &out); err != nil {
		t.Fatalf("unknown field should be tolerated: %v", err)
	}
	if out.GetAssignmentId() != "a" {
		t.Fatal("known field lost")
	}
}

func TestPublishAfterCloseFails(t *testing.T) {
	b := NewMemory(1)
	_ = b.Close()
	if err := b.Publish(context.Background(), Message{Topic: TopicArrivalsRaw}); err == nil {
		t.Fatal("expected error publishing to a closed bus")
	}
}
