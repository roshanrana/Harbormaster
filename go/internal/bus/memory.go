package bus

import (
	"context"
	"hash/fnv"
	"sync"
)

// Memory is an in-process Bus for unit tests.
//
// It deliberately models the one property the real broker gives us that the
// design depends on: messages sharing a key are delivered in publish order.
// It does this the same way Kafka does, by hashing the key to a partition and
// keeping each partition strictly ordered, rather than by pretending a single
// global queue is equivalent. A fake that is ordered *everywhere* would hide
// bugs that a real broker would expose.
type Memory struct {
	mu         sync.Mutex
	partitions int32
	// topic -> partition -> messages
	log    map[string]map[int32][]Message
	subs   []*memConsumer
	closed bool
}

// NewMemory returns an in-memory bus with the given partition count.
func NewMemory(partitions int32) *Memory {
	if partitions < 1 {
		partitions = 1
	}
	return &Memory{
		partitions: partitions,
		log:        make(map[string]map[int32][]Message),
	}
}

func (m *Memory) partitionFor(key string) int32 {
	if key == "" {
		return 0
	}
	h := fnv.New32a()
	_, _ = h.Write([]byte(key))
	return int32(h.Sum32() % uint32(m.partitions)) //nolint:gosec // bounded by partitions
}

// Publish appends messages to their partition and fans them out to consumers.
func (m *Memory) Publish(ctx context.Context, msgs ...Message) error {
	m.mu.Lock()
	if m.closed {
		m.mu.Unlock()
		return ErrClosed
	}
	delivered := make([]deliveryTarget, 0, len(msgs))
	for _, msg := range msgs {
		p := m.partitionFor(msg.Key)
		if m.log[msg.Topic] == nil {
			m.log[msg.Topic] = make(map[int32][]Message)
		}
		msg.Partition = p
		msg.Offset = int64(len(m.log[msg.Topic][p]))
		m.log[msg.Topic][p] = append(m.log[msg.Topic][p], msg)
		for _, c := range m.subs {
			if c.subscribed(msg.Topic) {
				delivered = append(delivered, deliveryTarget{c: c, msg: msg})
			}
		}
	}
	m.mu.Unlock()

	// Delivered outside the lock so a handler cannot deadlock the bus, but
	// still in publish order so per-key ordering survives.
	for _, d := range delivered {
		select {
		case d.c.ch <- d.msg:
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	return nil
}

type deliveryTarget struct {
	c   *memConsumer
	msg Message
}

// NewConsumer returns a consumer subscribed to the given topics. Messages
// published before the consumer existed are replayed, so tests do not have to
// order their setup around subscription timing.
func (m *Memory) NewConsumer(_ string, topics ...string) (Consumer, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.closed {
		return nil, ErrClosed
	}
	c := &memConsumer{
		topics: make(map[string]bool, len(topics)),
		ch:     make(chan Message, 1024),
	}
	for _, t := range topics {
		c.topics[t] = true
	}
	// Replay history in offset order, partition by partition.
	for _, t := range topics {
		for p := int32(0); p < m.partitions; p++ {
			for _, msg := range m.log[t][p] {
				select {
				case c.ch <- msg:
				default: // buffer full; a test publishing >1024 backlog messages should say so
				}
			}
		}
	}
	m.subs = append(m.subs, c)
	return c, nil
}

// Messages returns everything published to a topic, in partition then offset
// order. Test helper.
func (m *Memory) Messages(topic string) []Message {
	m.mu.Lock()
	defer m.mu.Unlock()
	var out []Message
	for p := int32(0); p < m.partitions; p++ {
		out = append(out, m.log[topic][p]...)
	}
	return out
}

// Close shuts the bus and all its consumers.
func (m *Memory) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.closed {
		return nil
	}
	m.closed = true
	for _, c := range m.subs {
		c.closeOnce.Do(func() { close(c.ch) })
	}
	return nil
}

type memConsumer struct {
	topics    map[string]bool
	ch        chan Message
	closeOnce sync.Once
}

func (c *memConsumer) subscribed(topic string) bool { return c.topics[topic] }

func (c *memConsumer) Consume(ctx context.Context, h Handler) error {
	for {
		select {
		case <-ctx.Done():
			return nil
		case msg, ok := <-c.ch:
			if !ok {
				return nil
			}
			if err := h(ctx, msg); err != nil {
				// Mirrors the real consumer: a failed handler does not advance
				// the offset. In memory that means we surface it immediately
				// rather than silently dropping the message.
				return err
			}
		}
	}
}

func (c *memConsumer) Close() error {
	c.closeOnce.Do(func() { close(c.ch) })
	return nil
}
