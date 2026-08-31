// Package masking redacts account numbers on the way out of the process.
//
// The rule (ADR-011): account *numbers* are masked to their last four
// characters; account *names* are never masked. Operators need to recognise a
// client at a glance without account numbers ending up in logs, screenshots or
// a shared terminal.
//
// The important design property is that masking happens in one place, at
// serialisation, rather than at each call site. A rule applied at call sites is
// a rule that will eventually be forgotten in the one code path that mattered.
package masking

import (
	"os"
	"strings"
	"sync/atomic"
)

// enabled is read on every call so tests can flip it without reconstructing
// anything. HM_MASK_ACCOUNTS=false is a local-debugging escape hatch only.
var enabled atomic.Bool

func init() {
	enabled.Store(strings.ToLower(os.Getenv("HM_MASK_ACCOUNTS")) != "false")
}

// SetEnabled overrides the environment. Intended for tests.
func SetEnabled(v bool) { enabled.Store(v) }

// Enabled reports whether masking is active.
func Enabled() bool { return enabled.Load() }

const minRevealed = 4

// AccountNumber masks all but the trailing four alphanumeric characters,
// preserving any separators so the shape of the identifier stays recognisable.
//
//	"8842-00119" -> "****-***119" is wrong; we keep it simple and predictable:
//	"8842-00119" -> "******0119"
//
// Short identifiers (four characters or fewer) are masked entirely rather than
// being returned in the clear, because revealing all of a short account number
// reveals the account.
func AccountNumber(s string) string {
	if !enabled.Load() || s == "" {
		return s
	}
	runes := []rune(s)
	if len(runes) <= minRevealed {
		return strings.Repeat("*", len(runes))
	}
	tail := runes[len(runes)-minRevealed:]
	return strings.Repeat("*", len(runes)-minRevealed) + string(tail)
}

// AccountNumbers masks a slice, returning a new slice.
func AccountNumbers(in []string) []string {
	if len(in) == 0 {
		return in
	}
	out := make([]string, len(in))
	for i, s := range in {
		out[i] = AccountNumber(s)
	}
	return out
}

// AccountName is the counterpart to AccountNumber and deliberately does
// nothing. It exists so that call sites read symmetrically and so that the
// decision not to mask names is visible in the code rather than implied by its
// absence.
func AccountName(s string) string { return s }
