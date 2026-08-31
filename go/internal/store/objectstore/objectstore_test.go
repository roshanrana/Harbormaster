package objectstore

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"strings"
	"testing"
)

func TestPutReturnsSizeAndHashComputedDuringWrite(t *testing.T) {
	s, err := NewFS(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	body := strings.Repeat("trade,row\n", 5000)
	uri, size, sum, err := s.Put(context.Background(), "raw/a.csv", strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	if size != int64(len(body)) {
		t.Fatalf("size %d, want %d", size, len(body))
	}
	want := sha256.Sum256([]byte(body))
	if sum != hex.EncodeToString(want[:]) {
		t.Fatalf("hash mismatch: %s", sum)
	}
	if !strings.HasPrefix(uri, "fs://") {
		t.Fatalf("unexpected uri %q", uri)
	}
}

func TestRoundTrip(t *testing.T) {
	s, _ := NewFS(t.TempDir())
	ctx := context.Background()
	uri, _, _, err := s.Put(ctx, "raw/b.csv", bytes.NewBufferString("hello"))
	if err != nil {
		t.Fatal(err)
	}
	rc, err := s.Get(ctx, uri)
	if err != nil {
		t.Fatal(err)
	}
	defer rc.Close()
	got, _ := io.ReadAll(rc)
	if string(got) != "hello" {
		t.Fatalf("got %q", got)
	}
	if n, err := s.Stat(ctx, uri); err != nil || n != 5 {
		t.Fatalf("stat = %d, %v", n, err)
	}
}

func TestKeysCannotEscapeRoot(t *testing.T) {
	// Keys derive from filenames on a shared FTP mount. That is exactly the
	// kind of input that should not be trusted to stay in its directory.
	s, _ := NewFS(t.TempDir())
	_, _, _, err := s.Put(context.Background(), "../../etc/passwd", strings.NewReader("x"))
	if err == nil {
		t.Fatal("path traversal was permitted")
	}
}

func TestGetMissingReturnsErrNotFound(t *testing.T) {
	s, _ := NewFS(t.TempDir())
	_, err := s.Get(context.Background(), "fs://raw/nope.csv")
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("want ErrNotFound, got %v", err)
	}
}

func TestGetRejectsForeignScheme(t *testing.T) {
	s, _ := NewFS(t.TempDir())
	if _, err := s.Get(context.Background(), "s3://bucket/key"); err == nil {
		t.Fatal("fs adapter accepted an s3 uri")
	}
}

func TestPartialWritesAreNeverVisible(t *testing.T) {
	// Put writes to a temp file and renames. A reader must never observe a
	// truncated object, because the store is the source of truth for replay.
	s, _ := NewFS(t.TempDir())
	ctx := context.Background()
	failing := io.MultiReader(strings.NewReader("good"), errReader{})
	if _, _, _, err := s.Put(ctx, "raw/c.csv", failing); err == nil {
		t.Fatal("expected the write to fail")
	}
	if _, err := s.Get(ctx, "fs://raw/c.csv"); !errors.Is(err, ErrNotFound) {
		t.Fatal("a failed write left a visible object behind")
	}
}

type errReader struct{}

func (errReader) Read([]byte) (int, error) { return 0, errors.New("boom") }
