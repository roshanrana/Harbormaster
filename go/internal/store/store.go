// Package store owns database access and schema migration.
package store

import (
	"context"
	"database/sql"
	"embed"
	"errors"
	"fmt"
	"sort"
	"strings"

	_ "github.com/lib/pq" // database/sql driver
)

//go:embed migrations/*.sql
var migrationFS embed.FS

// Migration is one ordered, reversible schema change.
type Migration struct {
	Version int
	Name    string
	Up      string
	Down    string
}

// Open connects to Postgres. The caller owns closing the returned handle.
func Open(dsn string) (*sql.DB, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("store: open: %w", err)
	}
	// Bounded pool: four services sharing one Postgres should not be able to
	// exhaust its connection slots between them during a burst.
	db.SetMaxOpenConns(16)
	db.SetMaxIdleConns(4)
	return db, nil
}

// LoadMigrations reads the embedded migration set, ordered by version.
func LoadMigrations() ([]Migration, error) {
	entries, err := migrationFS.ReadDir("migrations")
	if err != nil {
		return nil, fmt.Errorf("store: read migrations: %w", err)
	}
	byVersion := map[int]*Migration{}
	for _, e := range entries {
		name := e.Name()
		var version int
		var label, direction string
		// Format: 001_init.up.sql
		if _, err := fmt.Sscanf(name, "%03d_", &version); err != nil {
			return nil, fmt.Errorf("store: bad migration filename %q: %w", name, err)
		}
		rest := strings.TrimSuffix(name[strings.Index(name, "_")+1:], ".sql")
		idx := strings.LastIndex(rest, ".")
		if idx < 0 {
			return nil, fmt.Errorf("store: bad migration filename %q", name)
		}
		label, direction = rest[:idx], rest[idx+1:]

		body, err := migrationFS.ReadFile("migrations/" + name)
		if err != nil {
			return nil, fmt.Errorf("store: read %s: %w", name, err)
		}
		m, ok := byVersion[version]
		if !ok {
			m = &Migration{Version: version, Name: label}
			byVersion[version] = m
		}
		switch direction {
		case "up":
			m.Up = string(body)
		case "down":
			m.Down = string(body)
		default:
			return nil, fmt.Errorf("store: unknown migration direction %q in %s", direction, name)
		}
	}

	out := make([]Migration, 0, len(byVersion))
	for _, m := range byVersion {
		if m.Up == "" || m.Down == "" {
			// A migration without a rollback is a migration you cannot undo at
			// 3am. Refuse to load rather than discover it under pressure.
			return nil, fmt.Errorf("store: migration %03d_%s is missing an up or down half", m.Version, m.Name)
		}
		out = append(out, *m)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Version < out[j].Version })
	return out, nil
}

const schemaTable = `
CREATE TABLE IF NOT EXISTS schema_migration (
    version     INT PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)`

// Migrate applies every migration not yet recorded, in version order.
//
// Each migration and its bookkeeping row commit in a single transaction, so a
// crash mid-migration cannot leave the recorded version disagreeing with the
// actual schema.
func Migrate(ctx context.Context, db *sql.DB) (applied []int, err error) {
	if _, err := db.ExecContext(ctx, schemaTable); err != nil {
		return nil, fmt.Errorf("store: create schema_migration: %w", err)
	}
	done, err := appliedVersions(ctx, db)
	if err != nil {
		return nil, err
	}
	migrations, err := LoadMigrations()
	if err != nil {
		return nil, err
	}
	for _, m := range migrations {
		if done[m.Version] {
			continue
		}
		if err := applyOne(ctx, db, m); err != nil {
			return applied, err
		}
		applied = append(applied, m.Version)
	}
	return applied, nil
}

func applyOne(ctx context.Context, db *sql.DB, m Migration) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("store: begin %03d: %w", m.Version, err)
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, m.Up); err != nil {
		return fmt.Errorf("store: apply %03d_%s: %w", m.Version, m.Name, err)
	}
	if _, err := tx.ExecContext(ctx,
		`INSERT INTO schema_migration (version, name) VALUES ($1, $2)`, m.Version, m.Name); err != nil {
		return fmt.Errorf("store: record %03d: %w", m.Version, err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("store: commit %03d: %w", m.Version, err)
	}
	return nil
}

// Rollback reverts the single most recently applied migration.
func Rollback(ctx context.Context, db *sql.DB) (version int, err error) {
	row := db.QueryRowContext(ctx, `SELECT version FROM schema_migration ORDER BY version DESC LIMIT 1`)
	if err := row.Scan(&version); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return 0, nil
		}
		return 0, fmt.Errorf("store: read latest migration: %w", err)
	}
	migrations, err := LoadMigrations()
	if err != nil {
		return 0, err
	}
	for _, m := range migrations {
		if m.Version != version {
			continue
		}
		tx, err := db.BeginTx(ctx, nil)
		if err != nil {
			return 0, fmt.Errorf("store: begin rollback: %w", err)
		}
		defer func() { _ = tx.Rollback() }()
		if _, err := tx.ExecContext(ctx, m.Down); err != nil {
			return 0, fmt.Errorf("store: rollback %03d: %w", m.Version, err)
		}
		if _, err := tx.ExecContext(ctx, `DELETE FROM schema_migration WHERE version = $1`, m.Version); err != nil {
			return 0, fmt.Errorf("store: unrecord %03d: %w", m.Version, err)
		}
		if err := tx.Commit(); err != nil {
			return 0, fmt.Errorf("store: commit rollback: %w", err)
		}
		return version, nil
	}
	return 0, fmt.Errorf("store: no migration found for applied version %d", version)
}

func appliedVersions(ctx context.Context, db *sql.DB) (map[int]bool, error) {
	rows, err := db.QueryContext(ctx, `SELECT version FROM schema_migration`)
	if err != nil {
		return nil, fmt.Errorf("store: read applied versions: %w", err)
	}
	defer func() { _ = rows.Close() }()

	out := map[int]bool{}
	for rows.Next() {
		var v int
		if err := rows.Scan(&v); err != nil {
			return nil, fmt.Errorf("store: scan version: %w", err)
		}
		out[v] = true
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("store: iterate versions: %w", err)
	}
	return out, nil
}
