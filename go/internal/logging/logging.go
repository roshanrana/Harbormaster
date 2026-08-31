// Package logging provides structured JSON logging with correlation IDs.
//
// Two properties matter here.
//
// First, correlation. An arrival passes through four services; when something
// goes wrong at 3am the question is always "what happened to *this* file", not
// "what happened in this service". Every log line therefore carries the
// arrival_id, propagated through context rather than threaded through every
// function signature.
//
// Second, masking. Account numbers must never reach a log file (ADR-011). The
// Account helper is the only sanctioned way to log an account identifier, and
// it masks by construction. There is deliberately no unmasked variant.
package logging

import (
	"context"
	"log/slog"
	"os"
	"strings"

	"harbormaster.dev/hm/internal/masking"
)

type ctxKey int

const (
	ctxArrivalID ctxKey = iota
	ctxCorrelationID
)

// New builds a JSON logger for a component.
func New(component string) *slog.Logger {
	level := slog.LevelInfo
	switch strings.ToLower(os.Getenv("HM_LOG_LEVEL")) {
	case "debug":
		level = slog.LevelDebug
	case "warn":
		level = slog.LevelWarn
	case "error":
		level = slog.LevelError
	}
	h := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: level})
	return slog.New(h).With(slog.String("component", component))
}

// WithArrival tags a context with the arrival being processed.
func WithArrival(ctx context.Context, arrivalID string) context.Context {
	return context.WithValue(ctx, ctxArrivalID, arrivalID)
}

// WithCorrelation tags a context with a correlation id that spans services.
func WithCorrelation(ctx context.Context, correlationID string) context.Context {
	return context.WithValue(ctx, ctxCorrelationID, correlationID)
}

// ArrivalID reads the arrival id from a context, or "" if absent.
func ArrivalID(ctx context.Context) string {
	v, _ := ctx.Value(ctxArrivalID).(string)
	return v
}

// CorrelationID reads the correlation id from a context, or "" if absent.
func CorrelationID(ctx context.Context) string {
	v, _ := ctx.Value(ctxCorrelationID).(string)
	return v
}

// From returns a logger carrying whatever identifiers the context holds, so
// call sites can write log.Info(...) without restating them each time.
func From(ctx context.Context, base *slog.Logger) *slog.Logger {
	l := base
	if id := ArrivalID(ctx); id != "" {
		l = l.With(slog.String("arrival_id", id))
	}
	if id := CorrelationID(ctx); id != "" {
		l = l.With(slog.String("correlation_id", id))
	}
	return l
}

// Account is the only sanctioned way to log an account identifier. It masks
// the number and leaves the name intact (ADR-011). There is no unmasked
// counterpart, by design: an escape hatch would eventually get used.
func Account(number, name string) slog.Attr {
	return slog.Group("account",
		slog.String("number", masking.AccountNumber(number)),
		slog.String("name", masking.AccountName(name)),
	)
}

// Accounts logs a set of account numbers, masked.
func Accounts(numbers []string) slog.Attr {
	return slog.Any("account_numbers", masking.AccountNumbers(numbers))
}
