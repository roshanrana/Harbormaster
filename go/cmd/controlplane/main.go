// Command controlplane projects events into read models and serves the
// operations board.
//
// It is the only component an operator interacts with, and the only one that
// writes nothing to the pipeline except review decisions. Everything it shows
// is a projection of the event log, so a corrupted board is rebuilt by replaying
// topics rather than by repairing rows.
package main

import (
	"context"
	"database/sql"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"

	hmv1 "harbormaster.dev/hm/gen/hmv1"
	"harbormaster.dev/hm/internal/audit"
	"harbormaster.dev/hm/internal/bus"
	"harbormaster.dev/hm/internal/logging"
	"harbormaster.dev/hm/internal/store"
	"harbormaster.dev/hm/internal/web"
)

func main() {
	migrateOnly := flag.Bool("migrate", false, "apply database migrations and exit")
	verifyAudit := flag.Bool("verify-audit", false, "verify every audit chain and exit")
	flag.Parse()

	log := logging.New("controlplane")
	if err := run(*migrateOnly, *verifyAudit, log); err != nil {
		log.Error("fatal", slog.String("error", err.Error()))
		os.Exit(1)
	}
}

func run(migrateOnly, verifyAudit bool, log *slog.Logger) error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	db, err := store.Open(env("HM_POSTGRES_DSN", "postgres://hm:hm@postgres:5432/hm?sslmode=disable"))
	if err != nil {
		return err
	}
	defer func() { _ = db.Close() }()

	if migrateOnly {
		applied, err := store.Migrate(ctx, db)
		if err != nil {
			return err
		}
		log.Info("migrations applied", slog.Any("versions", applied))
		return nil
	}

	if verifyAudit {
		return runVerifyAudit(ctx, db, log)
	}

	if _, err := store.Migrate(ctx, db); err != nil {
		return err
	}

	templates, err := web.Templates()
	if err != nil {
		return err
	}
	static, err := web.StaticAssets()
	if err != nil {
		return err
	}

	b, err := bus.NewFranz(strings.Split(env("HM_KAFKA_BROKERS", "redpanda:9092"), ","))
	if err != nil {
		return err
	}
	defer func() { _ = b.Close() }()

	readStore := web.NewStore(db)
	server := web.NewServer(web.Options{
		Store: readStore, Bus: b, Log: log, Templates: templates, Static: static,
	})

	projector := &projector{store: readStore, events: server.Events(), log: log}
	go projector.run(ctx, b)

	return server.Serve(ctx, env("HM_HTTP_ADDR", ":8080"))
}

// runVerifyAudit walks every hash chain and reports the first break in each.
//
// Exits non-zero on any break so it can be wired into a scheduled check: an
// audit log nobody verifies is a filing cabinet, not a control.
func runVerifyAudit(ctx context.Context, db *sql.DB, log *slog.Logger) error {
	chain := audit.New(db)
	breaks, err := chain.VerifyAll(ctx)
	if err != nil {
		return err
	}
	if len(breaks) == 0 {
		log.Info("audit chains verified", slog.String("result", "no breaks found"))
		return nil
	}
	for _, b := range breaks {
		log.Error("audit chain broken",
			slog.String("arrival_id", b.ArrivalID),
			slog.String("record_id", b.RecordID),
			slog.Int("position", b.Position),
			slog.String("reason", b.Reason))
	}
	return fmt.Errorf("controlplane: %d audit chain(s) failed verification", len(breaks))
}

// --- projector -------------------------------------------------------------

type projector struct {
	store  *web.Store
	events *web.EventHub
	log    *slog.Logger
}

// run consumes every board-relevant topic into the read models.
//
// A projection failure is logged and skipped rather than retried forever. The
// event log remains authoritative, so a missed projection costs a stale board
// row until the next replay; blocking the whole consumer on one bad message
// would cost the board entirely.
func (p *projector) run(ctx context.Context, b bus.Bus) {
	consumer, err := b.NewConsumer("controlplane-projector",
		bus.TopicArrivalsClassified,
		bus.TopicArrivalsQuarantine,
		bus.TopicBerthAssigned,
		bus.TopicBerthSuperseded,
		bus.TopicAlertsMissing,
	)
	if err != nil {
		p.log.Error("projector could not start", slog.String("error", err.Error()))
		return
	}
	defer func() { _ = consumer.Close() }()

	p.log.Info("projecting", slog.String("group", "controlplane-projector"))
	if err := consumer.Consume(ctx, p.handle); err != nil {
		p.log.Error("projector stopped", slog.String("error", err.Error()))
	}
}

func (p *projector) handle(ctx context.Context, m bus.Message) error {
	switch m.Topic {
	case bus.TopicArrivalsClassified, bus.TopicArrivalsQuarantine:
		var msg hmv1.ArrivalClassified
		if err := bus.Decode(m.Value, &msg); err != nil {
			return p.skip(m, err)
		}
		if err := p.store.ProjectClassified(ctx, &msg); err != nil {
			return p.skip(m, err)
		}
		p.events.Publish(web.Event{
			Kind: "arrival", ArrivalID: msg.GetArrivalId(), ClientID: msg.GetClientId(),
			Summary: fmt.Sprintf("%s for %s", msg.GetClientId(), msg.GetValueDate().GetResolved()),
		})

	case bus.TopicBerthAssigned:
		var msg hmv1.BerthAssigned
		if err := bus.Decode(m.Value, &msg); err != nil {
			return p.skip(m, err)
		}
		if err := p.store.ProjectAssignment(ctx, &msg); err != nil {
			return p.skip(m, err)
		}
		p.events.Publish(web.Event{Kind: "assignment", ClientID: msg.GetClientId()})

	case bus.TopicBerthSuperseded:
		var msg hmv1.BerthSuperseded
		if err := bus.Decode(m.Value, &msg); err != nil {
			return p.skip(m, err)
		}
		if err := p.store.ProjectSuperseded(ctx, &msg); err != nil {
			return p.skip(m, err)
		}
		p.events.Publish(web.Event{Kind: "superseded"})

	case bus.TopicAlertsMissing:
		var msg hmv1.MissingFileAlert
		if err := bus.Decode(m.Value, &msg); err != nil {
			return p.skip(m, err)
		}
		if err := p.store.ProjectAlert(ctx, &msg); err != nil {
			return p.skip(m, err)
		}
		p.events.Publish(web.Event{Kind: "alert", ClientID: msg.GetClientId()})
	}

	if err := p.store.SaveOffset(ctx, "controlplane-projector", m.Topic, m.Partition, m.Offset+1); err != nil {
		p.log.Warn("offset not saved", slog.String("error", err.Error()))
	}
	return nil
}

func (p *projector) skip(m bus.Message, err error) error {
	p.log.Warn("projection skipped",
		slog.String("topic", m.Topic), slog.Int64("offset", m.Offset),
		slog.String("error", err.Error()))
	return nil
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
