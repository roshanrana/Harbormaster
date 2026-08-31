package masking

import (
	"encoding/json"
	"os"
	"testing"
)

// The masking rule is implemented twice, in Go and in Python. Two
// implementations of one rule will drift unless something forces them to
// agree. This emits the Go answers for a shared case table; the Python suite
// reads the same file and asserts identical output.
func TestEmitParityTable(t *testing.T) {
	SetEnabled(true)
	inputs := []string{
		"8842-00119", "123456789", "0119", "42", "", "ACCT-Ω-7781",
		"GB29NWBK60161331926819", "A", "0000", "00001",
	}
	out := make(map[string]string, len(inputs))
	for _, in := range inputs {
		out[in] = AccountNumber(in)
	}
	b, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile("testdata/masking_parity.json", b, 0o644); err != nil {
		t.Fatal(err)
	}
}
