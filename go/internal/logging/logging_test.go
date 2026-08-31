package logging

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"strings"
	"testing"

	"harbormaster.dev/hm/internal/masking"
)

func capture(t *testing.T, fn func(l *slog.Logger)) map[string]any {
	t.Helper()
	var buf bytes.Buffer
	l := slog.New(slog.NewJSONHandler(&buf, nil)).With(slog.String("component", "test"))
	fn(l)
	var out map[string]any
	if err := json.Unmarshal(bytes.TrimSpace(buf.Bytes()), &out); err != nil {
		t.Fatalf("log line was not valid JSON: %v\n%s", err, buf.String())
	}
	return out
}

func TestAccountNumberNeverAppearsUnmaskedInLogs(t *testing.T) {
	masking.SetEnabled(true)
	out := capture(t, func(l *slog.Logger) {
		l.Info("classified", Account("8842-00119", "Meridian Global Macro"))
	})
	raw, _ := json.Marshal(out)
	if strings.Contains(string(raw), "8842-00119") {
		t.Fatalf("account number leaked into log line: %s", raw)
	}
	acct, ok := out["account"].(map[string]any)
	if !ok {
		t.Fatal("account group missing")
	}
	if acct["name"] != "Meridian Global Macro" {
		t.Fatalf("account name should not be masked, got %v", acct["name"])
	}
	if !strings.HasSuffix(acct["number"].(string), "0119") {
		t.Fatalf("masked number should retain last four, got %v", acct["number"])
	}
}

func TestContextIdentifiersArePropagated(t *testing.T) {
	ctx := WithCorrelation(WithArrival(context.Background(), "arr-1"), "corr-9")
	out := capture(t, func(l *slog.Logger) {
		From(ctx, l).Info("processing")
	})
	if out["arrival_id"] != "arr-1" || out["correlation_id"] != "corr-9" {
		t.Fatalf("identifiers not propagated: %v", out)
	}
}

func TestFromWithoutContextValuesIsHarmless(t *testing.T) {
	out := capture(t, func(l *slog.Logger) {
		From(context.Background(), l).Info("processing")
	})
	if _, present := out["arrival_id"]; present {
		t.Fatal("empty arrival_id should be omitted, not logged blank")
	}
}

func TestAccountsSliceIsMasked(t *testing.T) {
	masking.SetEnabled(true)
	out := capture(t, func(l *slog.Logger) {
		l.Info("accounts", Accounts([]string{"8842-00119", "8842-00204"}))
	})
	raw, _ := json.Marshal(out)
	for _, secret := range []string{"8842-00119", "8842-00204"} {
		if strings.Contains(string(raw), secret) {
			t.Fatalf("account number %s leaked: %s", secret, raw)
		}
	}
}
