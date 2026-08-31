// Package objectstore abstracts where raw payloads and canonical output live.
//
// Two adapters exist (ADR-015). The filesystem adapter is the default and is
// what the demo stack runs on. The S3 adapter is implemented and unit-tested
// but deliberately unwired: it makes the production storage path visible in the
// code and reduces the migration to a configuration change, without adding a
// seventh container to a stack that gains nothing from one.
//
// URIs are opaque to callers. A URI produced by one adapter is only meaningful
// to that adapter, which is why Put returns one rather than expecting the
// caller to construct it.
package objectstore

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
)

// ErrNotFound is returned when a URI does not resolve to an object.
var ErrNotFound = errors.New("objectstore: not found")

// Store reads and writes immutable objects.
type Store interface {
	// Put streams r into the store under key and returns its URI, the number
	// of bytes written, and the lowercase hex SHA-256 of the content.
	//
	// Hashing during the write rather than in a second pass matters: a landing
	// directory file can be gigabytes, and reading it twice doubles the I/O on
	// the exact path that must keep up with arrivals.
	Put(ctx context.Context, key string, r io.Reader) (uri string, size int64, sha256Hex string, err error)
	Get(ctx context.Context, uri string) (io.ReadCloser, error)
	Stat(ctx context.Context, uri string) (size int64, err error)
}

// --- filesystem ------------------------------------------------------------

// FS stores objects under a root directory. URIs look like fs:///relative/key.
type FS struct {
	root string
	mu   sync.Mutex
}

// NewFS returns a filesystem-backed store rooted at root.
func NewFS(root string) (*FS, error) {
	if err := os.MkdirAll(root, 0o750); err != nil {
		return nil, fmt.Errorf("objectstore: create root %s: %w", root, err)
	}
	abs, err := filepath.Abs(root)
	if err != nil {
		return nil, fmt.Errorf("objectstore: resolve root: %w", err)
	}
	return &FS{root: abs}, nil
}

const fsScheme = "fs://"

func (f *FS) pathFor(key string) (string, error) {
	// Keys derive from filenames on a shared FTP mount, which is precisely the
	// kind of input that should not be trusted to stay in its directory.
	//
	// A traversal attempt is *rejected* rather than silently neutralised by
	// path cleaning. Both are safe, but a key containing ".." is anomalous and
	// an operator should see it in the audit log rather than have it quietly
	// rewritten into something harmless.
	for _, seg := range strings.Split(filepath.ToSlash(key), "/") {
		if seg == ".." {
			return "", fmt.Errorf("objectstore: key %q contains a parent-directory segment", key)
		}
	}
	full := filepath.Join(f.root, filepath.Clean("/"+strings.TrimPrefix(key, "/")))
	if !strings.HasPrefix(full, f.root+string(os.PathSeparator)) && full != f.root {
		return "", fmt.Errorf("objectstore: key %q escapes root", key)
	}
	return full, nil
}

// Put writes the object, hashing as it streams.
func (f *FS) Put(_ context.Context, key string, r io.Reader) (string, int64, string, error) {
	full, err := f.pathFor(key)
	if err != nil {
		return "", 0, "", err
	}
	if err := os.MkdirAll(filepath.Dir(full), 0o750); err != nil {
		return "", 0, "", fmt.Errorf("objectstore: mkdir: %w", err)
	}

	f.mu.Lock()
	defer f.mu.Unlock()

	// Write to a temporary file and rename, so a reader can never observe a
	// half-written object. The store is the source of truth for replay; a
	// truncated object there would be worse than no object at all.
	tmp, err := os.CreateTemp(filepath.Dir(full), ".hm-*")
	if err != nil {
		return "", 0, "", fmt.Errorf("objectstore: temp file: %w", err)
	}
	tmpName := tmp.Name()
	defer func() { _ = os.Remove(tmpName) }()

	h := sha256.New()
	size, err := io.Copy(io.MultiWriter(tmp, h), r)
	if err != nil {
		_ = tmp.Close()
		return "", 0, "", fmt.Errorf("objectstore: write %s: %w", key, err)
	}
	if err := tmp.Close(); err != nil {
		return "", 0, "", fmt.Errorf("objectstore: close temp: %w", err)
	}
	if err := os.Rename(tmpName, full); err != nil {
		return "", 0, "", fmt.Errorf("objectstore: rename: %w", err)
	}
	return fsScheme + strings.TrimPrefix(filepath.ToSlash(strings.TrimPrefix(full, f.root)), "/"), size,
		hex.EncodeToString(h.Sum(nil)), nil
}

// Get opens an object for reading.
func (f *FS) Get(_ context.Context, uri string) (io.ReadCloser, error) {
	full, err := f.resolve(uri)
	if err != nil {
		return nil, err
	}
	rc, err := os.Open(full) //nolint:gosec // path validated by resolve
	if err != nil {
		if os.IsNotExist(err) {
			return nil, fmt.Errorf("%w: %s", ErrNotFound, uri)
		}
		return nil, fmt.Errorf("objectstore: open %s: %w", uri, err)
	}
	return rc, nil
}

// Stat returns the object size.
func (f *FS) Stat(_ context.Context, uri string) (int64, error) {
	full, err := f.resolve(uri)
	if err != nil {
		return 0, err
	}
	fi, err := os.Stat(full)
	if err != nil {
		if os.IsNotExist(err) {
			return 0, fmt.Errorf("%w: %s", ErrNotFound, uri)
		}
		return 0, fmt.Errorf("objectstore: stat %s: %w", uri, err)
	}
	return fi.Size(), nil
}

func (f *FS) resolve(uri string) (string, error) {
	if !strings.HasPrefix(uri, fsScheme) {
		return "", fmt.Errorf("objectstore: not an fs uri: %q", uri)
	}
	return f.pathFor(strings.TrimPrefix(uri, fsScheme))
}
