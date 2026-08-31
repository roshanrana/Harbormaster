package masking

import (
	"strings"
	"testing"
)

func TestAccountNumber(t *testing.T) {
	SetEnabled(true)
	t.Cleanup(func() { SetEnabled(true) })

	cases := []struct{ name, in, want string }{
		{"typical hyphenated", "8842-00119", "******0119"},
		{"plain digits", "123456789", "*****6789"},
		{"exactly four", "0119", "****"},
		{"shorter than four", "42", "**"},
		{"empty", "", ""},
		{"unicode safe", "ACCT-Ω-7781", "*******7781"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := AccountNumber(c.in); got != c.want {
				t.Fatalf("AccountNumber(%q) = %q, want %q", c.in, got, c.want)
			}
		})
	}
}

func TestShortIdentifiersFullyMasked(t *testing.T) {
	SetEnabled(true)
	// A four-character account number must not be returned in the clear:
	// revealing "the last four" of a four-character value reveals all of it.
	got := AccountNumber("8842")
	if strings.ContainsAny(got, "0123456789") {
		t.Fatalf("short identifier leaked digits: %q", got)
	}
}

func TestDisabledPassesThrough(t *testing.T) {
	SetEnabled(false)
	t.Cleanup(func() { SetEnabled(true) })
	if got := AccountNumber("8842-00119"); got != "8842-00119" {
		t.Fatalf("masking disabled should pass through, got %q", got)
	}
}

func TestAccountNamesAreNeverMasked(t *testing.T) {
	SetEnabled(true)
	const name = "Meridian Global Macro"
	if got := AccountName(name); got != name {
		t.Fatalf("account name was altered: %q", got)
	}
}

func TestAccountNumbersSliceDoesNotAliasInput(t *testing.T) {
	SetEnabled(true)
	in := []string{"8842-00119", "8842-00204"}
	out := AccountNumbers(in)
	if in[0] != "8842-00119" {
		t.Fatal("input slice was mutated")
	}
	if out[0] == in[0] {
		t.Fatal("output was not masked")
	}
}
