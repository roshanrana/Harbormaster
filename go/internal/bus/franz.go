package bus

import (
	"context"
	"fmt"
	"time"

	"github.com/twmb/franz-go/pkg/kgo"
)

// Franz is a Bus backed by a Kafka-compatible broker (Redpanda in the demo
// stack, ADR-008).
//
// Two behaviours here are load-bearing rather than incidental:
//
//   - Producing is synchronous. Publish returns only after the broker
//     acknowledges, because consumers commit their offset after a successful
//     downstream publish. Fire-and-forget producing would make that ordering a
//     lie and could lose a message on crash.
//
//   - Consuming disables auto-commit and commits explicitly after the handler
//     succeeds. At-least-once delivery combined with idempotent, content-hash
//     keyed consumers is the durability model (HLD section 8); auto-commit would
//     turn it into at-most-once without anyone noticing.
type Franz struct {
	cl      *kgo.Client
	brokers []string
}

// NewFranz connects a producer client to the given brokers.
func NewFranz(brokers []string) (*Franz, error) {
	cl, err := kgo.NewClient(
		kgo.SeedBrokers(brokers...),
		kgo.ProducerBatchMaxBytes(16<<20),
		kgo.RequiredAcks(kgo.AllISRAcks()),
		kgo.ProducerLinger(5*time.Millisecond),
		kgo.RetryTimeout(30*time.Second),
	)
	if err != nil {
		return nil, fmt.Errorf("bus: connect %v: %w", brokers, err)
	}
	return &Franz{cl: cl, brokers: brokers}, nil
}

// Topic provisioning is deliberately not done here. Topics are infrastructure,
// created once by a one-shot `rpk` step in the Compose stack (ADR-020), so the
// application needs no cluster-admin privilege at runtime. A service that can
// create topics is a service that can create the wrong topic after a typo in a
// constant.

// Publish sends messages and waits for broker acknowledgement.
func (f *Franz) Publish(ctx context.Context, msgs ...Message) error {
	records := make([]*kgo.Record, 0, len(msgs))
	for _, m := range msgs {
		r := &kgo.Record{Topic: m.Topic, Key: []byte(m.Key), Value: m.Value}
		for k, v := range m.Headers {
			r.Headers = append(r.Headers, kgo.RecordHeader{Key: k, Value: []byte(v)})
		}
		records = append(records, r)
	}
	if err := f.cl.ProduceSync(ctx, records...).FirstErr(); err != nil {
		return fmt.Errorf("bus: publish: %w", err)
	}
	return nil
}

// NewConsumer returns a consumer in the given group.
func (f *Franz) NewConsumer(group string, topics ...string) (Consumer, error) {
	cl, err := kgo.NewClient(
		kgo.SeedBrokers(f.brokers...),
		kgo.ConsumerGroup(group),
		kgo.ConsumeTopics(topics...),
		kgo.DisableAutoCommit(),
		kgo.FetchMaxBytes(16<<20),
		// Start from the beginning so a newly deployed consumer processes the
		// backlog rather than silently skipping it.
		kgo.ConsumeResetOffset(kgo.NewOffset().AtStart()),
	)
	if err != nil {
		return nil, fmt.Errorf("bus: consumer %s: %w", group, err)
	}
	return &franzConsumer{cl: cl}, nil
}

// Close shuts the producer client.
func (f *Franz) Close() error { f.cl.Close(); return nil }

type franzConsumer struct{ cl *kgo.Client }

func (c *franzConsumer) Consume(ctx context.Context, h Handler) error {
	for {
		// Cancellation is a clean shutdown signal, not a failure, so it
		// returns nil rather than context.Canceled: callers should not log a
		// stack trace every time the service stops.
		select {
		case <-ctx.Done():
			return nil
		default:
		}

		fetches := c.cl.PollFetches(ctx)
		if fetches.IsClientClosed() {
			return nil
		}
		select {
		case <-ctx.Done():
			return nil
		default:
		}
		if errs := fetches.Errors(); len(errs) > 0 {
			return fmt.Errorf("bus: fetch: %w", errs[0].Err)
		}

		var handlerErr error
		fetches.EachRecord(func(r *kgo.Record) {
			if handlerErr != nil {
				return // stop at the first failure; do not advance past it
			}
			m := Message{
				Topic: r.Topic, Key: string(r.Key), Value: r.Value,
				Partition: r.Partition, Offset: r.Offset,
			}
			if len(r.Headers) > 0 {
				m.Headers = make(map[string]string, len(r.Headers))
				for _, hd := range r.Headers {
					m.Headers[hd.Key] = string(hd.Value)
				}
			}
			handlerErr = h(ctx, m)
		})
		if handlerErr != nil {
			// Offsets are deliberately not committed: the message will be
			// redelivered. Idempotent consumers make that safe.
			return handlerErr
		}
		if err := c.cl.CommitUncommittedOffsets(ctx); err != nil {
			return fmt.Errorf("bus: commit: %w", err)
		}
	}
}

func (c *franzConsumer) Close() error { c.cl.Close(); return nil }
