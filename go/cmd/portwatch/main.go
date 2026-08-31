// Command portwatch watches the FTP landing directory and the upstream JSON
// queue, and publishes an arrival event for every genuinely new payload.
//
// It does as little as possible on purpose. Everything it does is on the path
// that must never fall behind or lose a file, so parsing, classification and
// any model call happen downstream in Inspector where being slow is safe.
package main

import (
	"context"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"harbormaster.dev/hm/internal/arrival"
	"harbormaster.dev/hm/internal/audit"
	"harbormaster.dev/hm/internal/bus"
	"harbormaster.dev/hm/internal/logging"
	"harbormaster.dev/hm/internal/store"
	"harbormaster.dev/hm/internal/store/objectstore"
)

func main() {
	scanOnce := flag.Bool("scan-once", false, "perform a single scan and exit (used by tests)")
	flag.Parse()

	log := logging.New("portwatch")
	if err := run(*scanOnce, log); err != nil {
		log.Error("fatal", slog.String("error", err.Error()))
		os.Exit(1)
	}
}

func run(scanOnce bool, log *slog.Logger) error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	landing := env("HM_LANDING_DIR", "/data/landing")
	objectRoot := env("HM_OBJECT_STORE_ROOT", "/data/objects")

	db, err := store.Open(env("HM_POSTGRES_DSN", "postgres://hm:hm@postgres:5432/hm?sslmode=disable"))
	if err != nil {
		return err
	}
	defer func() { _ = db.Close() }()

	// Portwatch runs migrations at startup so a fresh stack needs no separate
	// step. Migrations are idempotent, so every service could safely do this;
	// only one does, to keep the ordering obvious.
	if applied, err := store.Migrate(ctx, db); err != nil {
		return err
	} else if len(applied) > 0 {
		log.Info("migrations applied", slog.Any("versions", applied))
	}

	objects, err := objectstore.NewFS(objectRoot)
	if err != nil {
		return err
	}
	producer, err := bus.NewFranz(envList("HM_KAFKA_BROKERS", "redpanda:9092"))
	if err != nil {
		return err
	}
	defer func() { _ = producer.Close() }()

	policy := arrival.DefaultPolicy()
	policy.ScanInterval = envDuration("HM_SCAN_INTERVAL", policy.ScanInterval)
	policy.QuietWindow = envDuration("HM_STABILITY_WINDOW", policy.QuietWindow)

	scanner := arrival.NewScanner(landing, policy)
	proc := &arrival.Processor{
		Store:    objects,
		Recorder: arrival.NewSQLDeduper(db),
		Bus:      producer,
		Audit:    audit.New(db),
		Log:      log,
		Scanner:  scanner,
	}

	log.Info("watching",
		slog.String("landing_dir", landing),
		slog.Duration("scan_interval", policy.ScanInterval),
		slog.Duration("quiet_window", policy.QuietWindow))

	if scanOnce {
		candidates, err := scanner.Scan()
		if err != nil {
			return err
		}
		for _, c := range candidates {
			if err := proc.Handle(ctx, c); err != nil {
				return err
			}
		}
		return nil
	}

	candidates := make(chan arrival.Candidate, 64)
	go func() {
		if err := scanner.Run(ctx, candidates); err != nil {
			log.Error("scanner stopped", slog.String("error", err.Error()))
			stop()
		}
		close(candidates)
	}()

	for c := range candidates {
		if err := proc.Handle(ctx, c); err != nil {
			// One bad file must not stop the watcher. It is logged, and the
			// next scan will see it again because it was never recorded.
			log.Error("arrival failed",
				slog.String("file", c.Name), slog.String("error", err.Error()))
		}
	}
	log.Info("shutdown complete")
	return nil
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envList(key, def string) []string {
	return splitComma(env(key, def))
}

func envDuration(key string, def time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	if d, err := time.ParseDuration(v); err == nil {
		return d
	}
	if n, err := strconv.Atoi(v); err == nil {
		return time.Duration(n) * time.Second
	}
	return def
}

func splitComma(s string) []string {
	var out []string
	start := 0
	for i := 0; i <= len(s); i++ {
		if i == len(s) || s[i] == ',' {
			if i > start {
				out = append(out, s[start:i])
			}
			start = i + 1
		}
	}
	return out
}
