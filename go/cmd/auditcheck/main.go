// Command auditcheck builds and verifies a recorded audit chain on disk.
//
// It exists for the offline bench (bench/onboard.py). The control plane's
// -verify-audit walks chains in Postgres; this walks the same records from a
// JSON file using the same ComputeHash and VerifyRecords, so a tamper check
// can run in CI with no database. Exit codes: 0 intact, 2 broken, 1 error.
package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"time"

	"harbormaster.dev/hm/internal/audit"
)

// A fixed clock and fixed record ids keep the recorded fixture byte-stable
// across builds, so a changed fixture means a changed hash contract.
var buildClock = time.Date(2026, 8, 31, 6, 0, 0, 0, time.UTC)

type buildStep struct {
	component string
	decision  string
	inputs    map[string]any
	outcome   map[string]any
}

var buildSteps = []buildStep{
	{
		component: "portwatch", decision: "ARRIVAL_DETECTED",
		inputs:  map[string]any{"name": "MCP_TRD_20260831.csv"},
		outcome: map[string]any{"sha256": "3f1c"},
	},
	{
		component: "inspector", decision: "CLASSIFIED",
		inputs:  map[string]any{"filename_date": "2026-08-31"},
		outcome: map[string]any{"value_date": "2026-08-28", "disposition": "DISPATCHED"},
	},
	{
		component: "berthmaster", decision: "BERTH_ASSIGNED",
		inputs:  map[string]any{"slot": "CLNT004/TRADE/2026-08-28"},
		outcome: map[string]any{"instruction_id": "bi-0001"},
	},
}

func main() {
	build := flag.String("build", "", "write a freshly built reference chain to this path")
	verify := flag.String("verify", "", "verify the chain recorded at this path")
	flag.Parse()

	switch {
	case *build != "":
		if err := writeChain(*build); err != nil {
			fmt.Fprintln(os.Stderr, "auditcheck:", err)
			os.Exit(1)
		}
	case *verify != "":
		code, err := verifyChain(*verify)
		if err != nil {
			fmt.Fprintln(os.Stderr, "auditcheck:", err)
			os.Exit(1)
		}
		os.Exit(code)
	default:
		fmt.Fprintln(os.Stderr, "auditcheck: pass -build <path> or -verify <path>")
		os.Exit(1)
	}
}

func writeChain(path string) error {
	prev := ""
	records := make([]audit.Record, 0, len(buildSteps))
	for i, step := range buildSteps {
		inputs, err := json.Marshal(step.inputs)
		if err != nil {
			return err
		}
		outcome, err := json.Marshal(step.outcome)
		if err != nil {
			return err
		}
		r := audit.Record{
			RecordID:     fmt.Sprintf("01BENCH%019d", i+1),
			ArrivalID:    "arr-bench-0001",
			At:           buildClock.Add(time.Duration(i) * time.Minute),
			Component:    step.component,
			DecisionType: step.decision,
			InputsJSON:   string(inputs),
			OutcomeJSON:  string(outcome),
			Actor:        "system",
			PrevHash:     prev,
		}
		r.RecordHash = audit.ComputeHash(r)
		prev = r.RecordHash
		records = append(records, r)
	}
	body, err := json.MarshalIndent(records, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(body, '\n'), 0o644)
}

// verifyChain prints a one-line JSON verdict and returns the exit code.
func verifyChain(path string) (int, error) {
	body, err := os.ReadFile(path)
	if err != nil {
		return 1, err
	}
	var records []audit.Record
	if err := json.Unmarshal(body, &records); err != nil {
		return 1, fmt.Errorf("decode %s: %w", path, err)
	}
	if len(records) == 0 {
		return 1, errors.New("recorded chain is empty; refusing to call that verified")
	}
	arrival := records[0].ArrivalID
	b := audit.VerifyRecords(arrival, records)
	verdict := map[string]any{"ok": b == nil, "records": len(records), "arrival_id": arrival}
	if b != nil {
		verdict["position"] = b.Position
		verdict["record_id"] = b.RecordID
		verdict["reason"] = b.Reason
	}
	out, err := json.Marshal(verdict)
	if err != nil {
		return 1, err
	}
	fmt.Println(string(out))
	if b != nil {
		return 2, nil
	}
	return 0, nil
}
