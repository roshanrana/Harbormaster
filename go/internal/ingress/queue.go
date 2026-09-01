package ingress

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"harbormaster.dev/hm/internal/arrival"
	"harbormaster.dev/hm/internal/bus"
	"harbormaster.dev/hm/internal/logging"
)

// QueueConsumer turns upstream JSON messages into arrivals.
//
// Some counterparty data does not arrive as a file at all: an integration
// upstream publishes it as a JSON message. Rather than build a second pipeline
// for that, the payload is written to the object store and emitted as an
// ordinary arrival. Everything downstream is then identical, which means the
// dedupe, classification, audit and review paths get exercised by both ingress
// routes rather than one of them being a lightly-tested special case.
//
// The consequence worth stating: because the payload is hashed the same way a
// file is, a message redelivered after a consumer restart is recognised as a
// duplicate by content, not by any broker-level delivery guarantee.
type QueueConsumer struct {
	Bus       bus.Bus
	Processor *arrival.Processor
	Topic     string
	Group     string
	Log       *slog.Logger
	// StagingDir is where payloads are written before being stored, so the
	// processor can treat them exactly as it treats a landed file.
	StagingDir string
}

// Envelope is the minimum an upstream message must carry.
//
// Everything else is passed through untouched: the Inspector decides what the
// contents mean, and an ingress that pre-interprets them would be making a
// classification decision in the wrong place.
type Envelope struct {
	MessageID string          `json:"messageId"`
	Source    string          `json:"source"`
	Payload   json.RawMessage `json:"payload"`
}

// Run consumes the queue until ctx is cancelled.
func (q *QueueConsumer) Run(ctx context.Context) error {
	topic := q.Topic
	if topic == "" {
		topic = "hm.ingress.json"
	}
	group := q.Group
	if group == "" {
		group = "portwatch-queue"
	}

	consumer, err := q.Bus.NewConsumer(group, topic)
	if err != nil {
		return fmt.Errorf("ingress: consumer %s: %w", group, err)
	}
	defer func() { _ = consumer.Close() }()

	q.Log.Info("consuming queue ingress", slog.String("topic", topic))
	return consumer.Consume(ctx, q.handle)
}

func (q *QueueConsumer) handle(ctx context.Context, m bus.Message) error {
	name := q.filename(m)
	ctx = logging.WithCorrelation(ctx, name)

	// A malformed payload is dead-lettered rather than retried forever: it
	// will never become valid, and blocking the partition on it would stop
	// every well-formed message behind it.
	if !json.Valid(m.Value) {
		logging.From(ctx, q.Log).Warn("queue payload is not valid JSON; skipped",
			slog.String("message", name), slog.Int("bytes", len(m.Value)))
		return nil
	}

	candidate, err := q.stage(name, m.Value)
	if err != nil {
		return err
	}
	return q.Processor.HandleQueuePayload(ctx, candidate)
}

// stage writes the payload to a file so the processor's file path is reused.
func (q *QueueConsumer) stage(name string, payload []byte) (arrival.Candidate, error) {
	dir := q.StagingDir
	if dir == "" {
		dir = "/tmp/hm-queue"
	}
	path, err := arrival.WriteStaged(dir, name, payload)
	if err != nil {
		return arrival.Candidate{}, err
	}
	return arrival.Candidate{
		Path: path, Name: name, Size: int64(len(payload)),
		ModTime: time.Now().UTC(), StabilityMS: 0,
	}, nil
}

// filename derives a stable, filesystem-safe name for a message.
func (q *QueueConsumer) filename(m bus.Message) string {
	var env Envelope
	if err := json.Unmarshal(m.Value, &env); err == nil && env.MessageID != "" {
		source := env.Source
		if source == "" {
			source = "queue"
		}
		return sanitize(fmt.Sprintf("%s_%s.json", source, env.MessageID))
	}
	// No envelope: fall back to the broker coordinates, which are unique.
	return sanitize(fmt.Sprintf("%s_p%d_o%d.json", m.Topic, m.Partition, m.Offset))
}

func sanitize(name string) string {
	// Message ids come from an upstream system. Path separators are replaced
	// and parent-directory sequences collapsed, so a hostile or merely
	// careless id cannot reach outside the staging directory.
	var b strings.Builder
	for _, r := range name {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9':
			b.WriteRune(r)
		case r == '.' || r == '-' || r == '_':
			b.WriteRune(r)
		default:
			b.WriteRune('_')
		}
	}
	return strings.ReplaceAll(b.String(), "..", "_")
}
