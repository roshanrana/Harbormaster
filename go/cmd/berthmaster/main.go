// Command berthmaster turns classified arrivals into berth assignments.
//
// It owns the question the reconciliation engine cannot answer for itself:
// given a file, which reconciliation run does it belong to, and is that run now
// ready? Everything upstream produces evidence; this is where the evidence
// becomes an instruction.
package main

import (
	"context"
	"errors"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/oklog/ulid/v2"
	"google.golang.org/protobuf/types/known/timestamppb"
	hmv1 "harbormaster.dev/hm/gen/hmv1"
	"harbormaster.dev/hm/internal/audit"
	"harbormaster.dev/hm/internal/bus"
	"harbormaster.dev/hm/internal/logging"
	"harbormaster.dev/hm/internal/registry"
	"harbormaster.dev/hm/internal/slot"
	"harbormaster.dev/hm/internal/store"
)

func main() {
	sweepOnly := flag.Bool("sweep-once", false, "run one overdue sweep and exit")
	flag.Parse()

	log := logging.New("berthmaster")
	if err := run(*sweepOnly, log); err != nil {
		log.Error("fatal", slog.String("error", err.Error()))
		os.Exit(1)
	}
}

func run(sweepOnly bool, log *slog.Logger) error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	db, err := store.Open(env("HM_POSTGRES_DSN", "postgres://hm:hm@postgres:5432/hm?sslmode=disable"))
	if err != nil {
		return err
	}
	defer func() { _ = db.Close() }()

	reg, err := registry.Load(env("HM_CONFIG_DIR", "/config"))
	if err != nil {
		return err
	}
	log.Info("configuration loaded", slog.Int("clients", len(reg.Clients())))

	machine := slot.NewMachine(slot.NewSQLStore(db), reg, envInt("HM_LATE_WINDOW_DAYS", 2))
	chain := audit.New(db)

	b, err := bus.NewFranz(strings.Split(env("HM_KAFKA_BROKERS", "redpanda:9092"), ","))
	if err != nil {
		return err
	}
	defer func() { _ = b.Close() }()

	svc := &service{machine: machine, audit: chain, bus: b, log: log}

	if sweepOnly {
		return svc.sweep(ctx)
	}

	// The overdue sweep runs on its own timer rather than being driven by
	// arrivals. A missing file is defined by the absence of an event, so it
	// can never be detected by handling one.
	go svc.sweepLoop(ctx)

	consumer, err := b.NewConsumer("berthmaster", bus.TopicArrivalsClassified)
	if err != nil {
		return err
	}
	defer func() { _ = consumer.Close() }()

	log.Info("consuming", slog.String("topic", bus.TopicArrivalsClassified))
	return consumer.Consume(ctx, svc.handle)
}

type service struct {
	machine *slot.Machine
	audit   *audit.Chain
	bus     bus.Producer
	log     *slog.Logger
}

func (s *service) handle(ctx context.Context, m bus.Message) error {
	var c hmv1.ArrivalClassified
	if err := bus.Decode(m.Value, &c); err != nil {
		return err
	}
	ctx = logging.WithArrival(ctx, c.GetArrivalId())
	log := logging.From(ctx, s.log)

	// Only dispatched arrivals reach the slot machine. Quarantined ones are
	// waiting on a human, and rejected ones are not going anywhere (FR-32).
	if c.GetDisposition() != hmv1.ArrivalDisposition_ARRIVAL_DISPOSITION_DISPATCHED {
		log.Info("arrival not dispatched; no slot action",
			slog.String("disposition", c.GetDisposition().String()))
		return nil
	}

	arrival := slot.Arrival{
		ArrivalID: c.GetArrivalId(),
		ClientID:  c.GetClientId(),
		Domain:    domainName(c.GetDomain()),
		ValueDate: c.GetValueDate().GetResolved(),
		Side:      sideName(c.GetReconSide()),
	}

	out, err := s.machine.Apply(ctx, arrival)
	if err != nil {
		if errors.Is(err, slot.ErrOutsideWindow) {
			// Not a failure of this service. The file is real but too old or
			// too far ahead to belong to any open reconciliation, which is an
			// operator decision, not an automatic one.
			log.Warn("arrival outside the late window",
				slog.String("value_date", arrival.ValueDate))
			return s.audit.Append(ctx, audit.Entry{
				ArrivalID: c.GetArrivalId(), Component: "berthmaster",
				DecisionType: "SLOT_REJECTED",
				Inputs:       map[string]any{"value_date": arrival.ValueDate, "client_id": arrival.ClientID},
				Outcome:      map[string]any{"reason": err.Error()},
			})
		}
		return err
	}

	key := out.Slot.Key
	if err := s.audit.Append(ctx, audit.Entry{
		ArrivalID: c.GetArrivalId(), Component: "berthmaster", DecisionType: "SLOT_UPDATED",
		Inputs: map[string]any{"slot": key.String(), "side": arrival.Side},
		Outcome: map[string]any{
			"state": string(out.Slot.State), "reason": out.Reason,
			"ready": out.Assign, "deadline": out.Slot.Deadline.Format(time.RFC3339),
		},
	}); err != nil {
		return err
	}

	if !out.Assign {
		log.Info("slot waiting for the other side",
			slog.String("slot", key.String()),
			slog.String("missing_side", slot.MissingSide(out.Slot)),
			slog.String("deadline", out.Slot.Deadline.Format(time.RFC3339)))
		return nil
	}

	return s.assign(ctx, &c, out)
}

// assign publishes the void, if any, and then the assignment.
//
// Both messages carry the slot key, so they land on one partition and no
// consumer can see the replacement before the void it replaces (ADR-005).
// Publishing the void first is what makes that ordering meaningful.
func (s *service) assign(ctx context.Context, c *hmv1.ArrivalClassified, out slot.Outcome) error {
	key := out.Slot.Key
	partition := bus.SlotKey(key.ClientID, key.Domain, key.ValueDate)
	log := logging.From(ctx, s.log)

	if out.Supersedes != "" {
		void := &hmv1.BerthSuperseded{
			AssignmentId: out.Supersedes,
			SupersededBy: c.GetArrivalId(),
			Reason:       out.Reason,
			EmittedAt:    timestamppb.Now(),
		}
		payload, err := bus.Encode(void)
		if err != nil {
			return err
		}
		if err := s.bus.Publish(ctx, bus.Message{
			Topic: bus.TopicBerthSuperseded, Key: partition, Value: payload,
		}); err != nil {
			return err
		}
		log.Info("prior assignment voided", slog.String("assignment_id", out.Supersedes))
	}

	assignmentID := ulid.Make().String()
	assigned := &hmv1.BerthAssigned{
		AssignmentId:  assignmentID,
		EmittedAt:     timestamppb.Now(),
		ClientId:      key.ClientID,
		Domain:        domainEnum(key.Domain),
		ValueDate:     key.ValueDate,
		Side_1:        &hmv1.SideRef{ArrivalId: out.Slot.Side1Arrival},
		Side_2:        &hmv1.SideRef{ArrivalId: out.Slot.Side2Arrival},
		ExpectationId: out.Slot.ExpectationID,
		Confidence:    c.GetOverallConfidence(),
		Supersedes:    out.Supersedes,
		Notes:         out.Reason,
	}
	payload, err := bus.Encode(assigned)
	if err != nil {
		return err
	}
	if err := s.bus.Publish(ctx, bus.Message{
		Topic: bus.TopicBerthAssigned, Key: partition, Value: payload,
	}); err != nil {
		return err
	}
	if err := s.machine.RecordAssignment(ctx, key, assignmentID); err != nil {
		return err
	}

	log.Info("berth assigned",
		slog.String("assignment_id", assignmentID),
		slog.String("slot", key.String()),
		slog.String("supersedes", out.Supersedes))

	return s.audit.Append(ctx, audit.Entry{
		ArrivalID: c.GetArrivalId(), Component: "berthmaster", DecisionType: "BERTH_ASSIGNED",
		Inputs: map[string]any{"slot": key.String(), "expectation_id": out.Slot.ExpectationID},
		Outcome: map[string]any{
			"assignment_id": assignmentID, "supersedes": out.Supersedes,
			"side_1": out.Slot.Side1Arrival, "side_2": out.Slot.Side2Arrival,
		},
	})
}

func (s *service) sweepLoop(ctx context.Context) {
	t := time.NewTicker(envDuration("HM_SWEEP_INTERVAL", time.Minute))
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			if err := s.sweep(ctx); err != nil {
				s.log.Error("sweep failed", slog.String("error", err.Error()))
			}
		}
	}
}

func (s *service) sweep(ctx context.Context) error {
	overdue, err := s.machine.Overdue(ctx)
	if err != nil {
		return err
	}
	for _, sl := range overdue {
		missing := slot.MissingSide(sl)
		alert := &hmv1.MissingFileAlert{
			ClientId:      sl.Key.ClientID,
			Domain:        domainEnum(sl.Key.Domain),
			ValueDate:     sl.Key.ValueDate,
			ExpectationId: sl.ExpectationID,
			MissingSide:   sideEnum(missing),
			Deadline:      timestamppb.New(sl.Deadline),
			EmittedAt:     timestamppb.Now(),
		}
		payload, err := bus.Encode(alert)
		if err != nil {
			return err
		}
		if err := s.bus.Publish(ctx, bus.Message{
			Topic: bus.TopicAlertsMissing,
			Key:   bus.SlotKey(sl.Key.ClientID, sl.Key.Domain, sl.Key.ValueDate),
			Value: payload,
		}); err != nil {
			return err
		}
		// The alert names the specific unmet expectation rather than saying
		// "a file is missing", because the first thing an operator needs is
		// which client owes what (FR-35).
		s.log.Warn("expected file never arrived",
			slog.String("slot", sl.Key.String()),
			slog.String("expectation_id", sl.ExpectationID),
			slog.String("missing_side", missing))
	}
	return nil
}

func domainName(d hmv1.ProductDomain) string {
	return strings.TrimPrefix(d.String(), "PRODUCT_DOMAIN_")
}

func domainEnum(name string) hmv1.ProductDomain {
	return hmv1.ProductDomain(hmv1.ProductDomain_value["PRODUCT_DOMAIN_"+name])
}

func sideName(s hmv1.ReconSide) string {
	return strings.TrimPrefix(s.String(), "RECON_SIDE_")
}

func sideEnum(name string) hmv1.ReconSide {
	return hmv1.ReconSide(hmv1.ReconSide_value["RECON_SIDE_"+name])
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v, err := strconv.Atoi(os.Getenv(key)); err == nil && v > 0 {
		return v
	}
	return def
}

func envDuration(key string, def time.Duration) time.Duration {
	if d, err := time.ParseDuration(os.Getenv(key)); err == nil && d > 0 {
		return d
	}
	return def
}
