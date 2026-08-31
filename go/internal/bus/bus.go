// Package bus is the messaging seam.
//
// Two implementations exist behind one interface (ADR-017): an in-memory bus
// used by unit tests, and a franz-go bus used against a real Kafka-compatible
// broker. The seam exists because the interesting logic in this system — slot
// transitions, supersession ordering, audit chaining — should be testable in
// milliseconds without infrastructure. A test suite that needs a broker running
// is a test suite that gets skipped.
//
// The memory implementation must preserve per-key ordering. Supersession
// correctness (FR-9) depends on a void being observed before its replacement,
// and that property comes from partitioning by slot identity (ADR-005). If the
// fake reordered messages, tests would pass on a false premise.
package bus

import (
	"context"
	"errors"
	"fmt"

	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

// Topic names. Kept here rather than as string literals at call sites so that
// a typo is a compile error rather than a message published into the void.
const (
	TopicArrivalsRaw        = "hm.arrivals.raw"
	TopicArrivalsClassified = "hm.arrivals.classified"
	TopicArrivalsQuarantine = "hm.arrivals.quarantined"
	TopicReviewDecisions    = "hm.review.decisions"
	TopicBerthAssigned      = "hm.berth.assigned"
	TopicBerthSuperseded    = "hm.berth.superseded"
	TopicAlertsMissing      = "hm.alerts.missing"
	TopicAuditDecisions     = "hm.audit.decisions"
)

// AllTopics is used at startup to create topics that do not yet exist.
func AllTopics() []string {
	return []string{
		TopicArrivalsRaw, TopicArrivalsClassified, TopicArrivalsQuarantine,
		TopicReviewDecisions, TopicBerthAssigned, TopicBerthSuperseded,
		TopicAlertsMissing, TopicAuditDecisions,
	}
}

// ErrClosed is returned by operations on a closed bus.
var ErrClosed = errors.New("bus: closed")

// Message is a single record. Key determines partition, and therefore ordering:
// every message for one reconciliation slot carries the same key.
type Message struct {
	Topic     string
	Key       string
	Value     []byte
	Headers   map[string]string
	Partition int32
	Offset    int64
}

// Handler processes one message. Returning an error means the message was not
// successfully handled and its offset must not be committed.
type Handler func(ctx context.Context, m Message) error

// Producer publishes messages.
type Producer interface {
	// Publish sends messages and returns only once the broker has acknowledged
	// them. Callers rely on this: an offset is committed after a downstream
	// publish succeeds, never before.
	Publish(ctx context.Context, msgs ...Message) error
	Close() error
}

// Consumer reads messages and commits offsets after successful handling.
type Consumer interface {
	// Consume blocks until ctx is cancelled. Offsets are committed only after
	// the handler returns nil, which is what makes at-least-once delivery
	// safe in combination with idempotent, content-hash-keyed consumers.
	Consume(ctx context.Context, h Handler) error
	Close() error
}

// Bus produces and creates consumers.
type Bus interface {
	Producer
	NewConsumer(group string, topics ...string) (Consumer, error)
}

// SlotKey builds the partition key that guarantees ordering within one
// reconciliation slot (ADR-005). Every downstream topic uses it.
func SlotKey(clientID, domain, valueDate string) string {
	return fmt.Sprintf("%s:%s:%s", clientID, domain, valueDate)
}

// --- codec -----------------------------------------------------------------
//
// protojson rather than binary proto (ADR-003). We trade throughput we do not
// need for topics that are readable during a demo and during incident triage.

var marshalOpts = protojson.MarshalOptions{EmitUnpopulated: false}

// Encode serialises a proto message for the wire.
func Encode(m proto.Message) ([]byte, error) {
	b, err := marshalOpts.Marshal(m)
	if err != nil {
		return nil, fmt.Errorf("bus: encode %T: %w", m, err)
	}
	return b, nil
}

// Decode parses a wire payload into m.
func Decode(b []byte, m proto.Message) error {
	// DiscardUnknown lets a consumer built against an older contract keep
	// working when a producer adds a field. Without it, every additive change
	// becomes a coordinated deployment.
	if err := (protojson.UnmarshalOptions{DiscardUnknown: true}).Unmarshal(b, m); err != nil {
		return fmt.Errorf("bus: decode %T: %w", m, err)
	}
	return nil
}
