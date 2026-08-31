package arrival

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

// clock lets tests cross the quiet window without sleeping.
type clock struct{ t time.Time }

func (c *clock) now() time.Time { return c.t }

func newScanner(t *testing.T) (*Scanner, string, *clock) {
	t.Helper()
	dir := t.TempDir()
	p := DefaultPolicy()
	p.ScanInterval = time.Second
	p.QuietWindow = 3 * time.Second
	s := NewScanner(dir, p)
	c := &clock{t: time.Date(2026, 8, 31, 6, 0, 0, 0, time.UTC)}
	s.SetClock(c.now)
	return s, dir, c
}

func write(t *testing.T, dir, name, body string) string {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

func touch(t *testing.T, path string, at time.Time) {
	t.Helper()
	if err := os.Chtimes(path, at, at); err != nil {
		t.Fatal(err)
	}
}

func TestFileIsNotEmittedOnFirstSight(t *testing.T) {
	// The whole point: a file seen once might still be being written.
	s, dir, _ := newScanner(t)
	write(t, dir, "trades.csv", "a,b,c")
	got, err := s.Scan()
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Fatalf("emitted on first sight: %v", got)
	}
}

func TestStableFileIsEmittedOnce(t *testing.T) {
	s, dir, _ := newScanner(t)
	p := write(t, dir, "trades.csv", "a,b,c")
	fixed := time.Date(2026, 8, 31, 5, 59, 0, 0, time.UTC)
	touch(t, p, fixed)

	var total int
	for i := 0; i < 6; i++ {
		got, err := s.Scan()
		if err != nil {
			t.Fatal(err)
		}
		total += len(got)
	}
	if total != 1 {
		t.Fatalf("want exactly one emission, got %d", total)
	}
}

func TestSlowWriteIsNotEmittedMidStream(t *testing.T) {
	// A file growing in chunks must never be emitted while it is still
	// growing, however many scans elapse. This is the expensive silent bug.
	s, dir, _ := newScanner(t)
	p := filepath.Join(dir, "big.csv")
	f, err := os.Create(p)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()

	base := time.Date(2026, 8, 31, 5, 0, 0, 0, time.UTC)
	for chunk := 0; chunk < 8; chunk++ {
		if _, err := f.WriteString("row,row,row\n"); err != nil {
			t.Fatal(err)
		}
		_ = f.Sync()
		touch(t, p, base.Add(time.Duration(chunk)*time.Second))
		got, err := s.Scan()
		if err != nil {
			t.Fatal(err)
		}
		if len(got) != 0 {
			t.Fatalf("emitted a file that was still growing (chunk %d)", chunk)
		}
	}

	// Writer stops. Now it should settle and emit.
	final := base.Add(100 * time.Second)
	touch(t, p, final)
	var emitted bool
	for i := 0; i < 5 && !emitted; i++ {
		got, _ := s.Scan()
		emitted = len(got) == 1
	}
	if !emitted {
		t.Fatal("file never emitted after the writer stopped")
	}
}

func TestSentinelShortCircuitsQuietWindow(t *testing.T) {
	s, dir, _ := newScanner(t)
	p := write(t, dir, "trades.csv", "a,b,c")
	touch(t, p, time.Date(2026, 8, 31, 5, 0, 0, 0, time.UTC))
	write(t, dir, "trades.csv.done", "")

	if _, err := s.Scan(); err != nil { // first sight
		t.Fatal(err)
	}
	got, err := s.Scan()
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 {
		t.Fatalf("sentinel should emit immediately on second scan, got %d", len(got))
	}
}

func TestSentinelAndPartialFilesAreNeverEmitted(t *testing.T) {
	s, dir, _ := newScanner(t)
	fixed := time.Date(2026, 8, 31, 5, 0, 0, 0, time.UTC)
	for _, name := range []string{"a.csv.done", "b.csv.tmp", "c.csv.part", ".hidden.csv"} {
		touch(t, write(t, dir, name, "x"), fixed)
	}
	for i := 0; i < 6; i++ {
		got, err := s.Scan()
		if err != nil {
			t.Fatal(err)
		}
		for _, c := range got {
			t.Fatalf("emitted an ignored file: %s", c.Name)
		}
	}
}

func TestVanishedFilesAreForgotten(t *testing.T) {
	s, dir, _ := newScanner(t)
	p := write(t, dir, "trades.csv", "a")
	if _, err := s.Scan(); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(p); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Scan(); err != nil {
		t.Fatal(err)
	}
	if len(s.seen) != 0 {
		t.Fatalf("observation map leaked %d entries", len(s.seen))
	}
}

func TestForgetAllowsSameNameToBeTreatedAsNew(t *testing.T) {
	// Corrections often arrive under the identical filename. Once an arrival
	// is durably recorded we forget the path, so a replacement is seen afresh.
	s, dir, _ := newScanner(t)
	p := write(t, dir, "trades.csv", "v1")
	fixed := time.Date(2026, 8, 31, 5, 0, 0, 0, time.UTC)
	touch(t, p, fixed)
	for i := 0; i < 5; i++ {
		if got, _ := s.Scan(); len(got) == 1 {
			break
		}
	}
	s.Forget(p)

	write(t, dir, "trades.csv", "v2-corrected")
	touch(t, p, fixed.Add(time.Hour))
	var again bool
	for i := 0; i < 5 && !again; i++ {
		got, _ := s.Scan()
		again = len(got) == 1
	}
	if !again {
		t.Fatal("replacement under the same name was not re-emitted")
	}
}

func TestMissingDirectoryIsAnError(t *testing.T) {
	s := NewScanner(filepath.Join(t.TempDir(), "nope"), DefaultPolicy())
	if _, err := s.Scan(); err == nil {
		t.Fatal("expected an error for a missing landing directory")
	}
}
