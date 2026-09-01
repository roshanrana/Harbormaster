// Package arrival detects that a file has landed and is safe to read.
//
// The hard part is not noticing a file. It is knowing the writer has finished.
// An FTP daemon creates the directory entry at the first byte, so a naive
// watcher reads a half-written CSV, parses 40% of the rows, and dispatches a
// reconciliation that silently omits the rest. That failure is quiet, plausible
// and expensive, which makes it the one worth engineering against.
//
// Detection is by polling, not inotify (ADR-016). Landing directories are
// almost always NFS or SMB mounts written by a remote host, and inotify does
// not fire for writes made by another machine. A scanner that works on a
// developer laptop and silently misses every file in production is worse than
// no scanner.
package arrival

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Candidate is a file that has been observed at least once.
type Candidate struct {
	Path        string
	Name        string
	Size        int64
	ModTime     time.Time
	StabilityMS int64 // how long size and mtime were unchanged before emission
}

// Policy controls write-completion detection.
type Policy struct {
	// ScanInterval is how often the landing directory is listed.
	ScanInterval time.Duration
	// QuietWindow is how long size and mtime must be unchanged before a file
	// is considered complete.
	QuietWindow time.Duration
	// SentinelSuffix, when non-empty, short-circuits the quiet window: if
	// "<name><suffix>" exists, the writer has declared the file complete.
	SentinelSuffix string
	// IgnoreSuffixes are skipped entirely (partial-upload markers, temp files).
	IgnoreSuffixes []string
}

// DefaultPolicy is deliberately conservative. Latency budget is 60 seconds
// (NFR-2); spending five of it on certainty is a good trade.
func DefaultPolicy() Policy {
	return Policy{
		ScanInterval:   2 * time.Second,
		QuietWindow:    5 * time.Second,
		SentinelSuffix: ".done",
		IgnoreSuffixes: []string{".done", ".tmp", ".part", ".filepart", ".crdownload", ".swp"},
	}
}

// observation is what we knew about a file on the previous scan.
type observation struct {
	size      int64
	modTime   time.Time
	stableFor time.Duration
	firstSeen time.Time
	emitted   bool
}

// Scanner walks a directory and emits files once they stop changing.
//
// It is intentionally not concurrent. One goroutine owning the observation map
// removes a whole class of race, and the work is a directory listing every two
// seconds, which does not need parallelism.
type Scanner struct {
	dir    string
	policy Policy
	seen   map[string]*observation
	now    func() time.Time // injectable for tests
}

// NewScanner returns a scanner for dir.
func NewScanner(dir string, p Policy) *Scanner {
	if p.ScanInterval <= 0 {
		p.ScanInterval = DefaultPolicy().ScanInterval
	}
	if p.QuietWindow <= 0 {
		p.QuietWindow = DefaultPolicy().QuietWindow
	}
	return &Scanner{dir: dir, policy: p, seen: map[string]*observation{}, now: time.Now}
}

// SetClock replaces the time source. Tests use this to advance the quiet window
// without sleeping; a test suite that sleeps for real is a test suite people
// stop running.
func (s *Scanner) SetClock(fn func() time.Time) { s.now = fn }

// Forget drops a path from the observation map, so a file replaced under the
// same name is treated as new. Called after an arrival is durably recorded.
func (s *Scanner) Forget(path string) { delete(s.seen, path) }

// Scan performs one pass and returns files that have become stable since the
// last pass. Calling Scan is idempotent with respect to already-emitted files,
// which is what makes restart safe: a rescan re-observes everything and the
// dedupe store decides what is genuinely new.
func (s *Scanner) Scan() ([]Candidate, error) {
	entries, err := os.ReadDir(s.dir)
	if err != nil {
		return nil, fmt.Errorf("arrival: read %s: %w", s.dir, err)
	}

	present := make(map[string]bool, len(entries))
	var ready []Candidate
	now := s.now()

	for _, e := range entries {
		if e.IsDir() || s.ignored(e.Name()) {
			continue
		}
		info, err := e.Info()
		if err != nil {
			// The file vanished between listing and stat: an FTP client
			// renaming its temp file. It will be picked up next scan.
			if os.IsNotExist(err) {
				continue
			}
			return nil, fmt.Errorf("arrival: stat %s: %w", e.Name(), err)
		}
		path := filepath.Join(s.dir, e.Name())
		present[path] = true

		obs, known := s.seen[path]
		if !known {
			s.seen[path] = &observation{size: info.Size(), modTime: info.ModTime(), firstSeen: now}
			continue
		}
		if obs.emitted {
			continue
		}

		changed := obs.size != info.Size() || !obs.modTime.Equal(info.ModTime())
		if changed {
			// Still being written. Reset the clock rather than accumulating,
			// so a slow trickle never crosses the threshold by attrition.
			obs.size, obs.modTime, obs.stableFor = info.Size(), info.ModTime(), 0
			continue
		}
		obs.stableFor += s.policy.ScanInterval

		if s.sentinelPresent(path) || obs.stableFor >= s.policy.QuietWindow {
			obs.emitted = true
			ready = append(ready, Candidate{
				Path: path, Name: e.Name(), Size: info.Size(), ModTime: info.ModTime(),
				StabilityMS: obs.stableFor.Milliseconds(),
			})
		}
	}

	// Drop vanished files so the map does not grow without bound across a long
	// uptime, and so a filename reused tomorrow is treated as new.
	for path := range s.seen {
		if !present[path] {
			delete(s.seen, path)
		}
	}
	return ready, nil
}

// Run scans on the policy interval until ctx is cancelled, sending stable files
// to out.
func (s *Scanner) Run(ctx context.Context, out chan<- Candidate) error {
	t := time.NewTicker(s.policy.ScanInterval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-t.C:
			ready, err := s.Scan()
			if err != nil {
				return err
			}
			for _, c := range ready {
				select {
				case out <- c:
				case <-ctx.Done():
					return nil
				}
			}
		}
	}
}

func (s *Scanner) ignored(name string) bool {
	if strings.HasPrefix(name, ".") {
		return true
	}
	lower := strings.ToLower(name)
	for _, suf := range s.policy.IgnoreSuffixes {
		if strings.HasSuffix(lower, suf) {
			return true
		}
	}
	return false
}

func (s *Scanner) sentinelPresent(path string) bool {
	if s.policy.SentinelSuffix == "" {
		return false
	}
	_, err := os.Stat(path + s.policy.SentinelSuffix)
	return err == nil
}

// WriteStaged writes a queue payload to disk so it can be handled by the same
// code path as a landed file. Returns the path written.
func WriteStaged(dir, name string, payload []byte) (string, error) {
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return "", fmt.Errorf("arrival: staging dir %s: %w", dir, err)
	}
	path := filepath.Join(dir, filepath.Base(name))
	if err := os.WriteFile(path, payload, 0o600); err != nil {
		return "", fmt.Errorf("arrival: stage %s: %w", name, err)
	}
	return path, nil
}
