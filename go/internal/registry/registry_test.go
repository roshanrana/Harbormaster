package registry

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// repoConfig loads the real configuration shipped with the project, so these
// tests fail if a committed client file stops being valid.
func repoConfig(t *testing.T) *Registry {
	t.Helper()
	r, err := Load(filepath.Join("..", "..", "..", "config"))
	if err != nil {
		t.Fatalf("shipped configuration failed to load: %v", err)
	}
	return r
}

func day(s string) time.Time {
	d, _ := time.Parse("2006-01-02", s)
	return d
}

func TestShippedConfigurationLoads(t *testing.T) {
	r := repoConfig(t)
	if got := len(r.Clients()); got < 6 {
		t.Fatalf("want at least 6 clients, got %d", got)
	}
	for _, id := range []string{"US_EQUITY", "UK_EQUITY", "EUR_DERIV", "HK_EQUITY"} {
		if _, ok := r.Calendar(id); !ok {
			t.Fatalf("calendar %s missing", id)
		}
	}
}

func TestCutsPerDayIsAvailableToDistinguishCorrections(t *testing.T) {
	// FR-10 lives on this field: two cuts a day is normal for CLNT004, so the
	// second file of the day is not a correction.
	r := repoConfig(t)
	c, _ := r.Client("CLNT004")
	e, ok := c.ExpectationFor(DomainTrade)
	if !ok {
		t.Fatal("CLNT004 has no TRADE expectation")
	}
	if e.CutsPerDay != 2 {
		t.Fatalf("cuts_per_day = %d, want 2", e.CutsPerDay)
	}
}

func TestFilenameHintExtractsDomainAndDate(t *testing.T) {
	r := repoConfig(t)
	c, _ := r.Client("CLNT004")
	domain, dateText, ok := c.FilenameHints[0].Match("MCP_TRD_20260828.csv")
	if !ok {
		t.Fatal("filename hint did not match")
	}
	if domain != DomainTrade || dateText != "20260828" {
		t.Fatalf("domain=%q date=%q", domain, dateText)
	}
}

func TestFilenameHintDoesNotMatchAnotherClient(t *testing.T) {
	r := repoConfig(t)
	c, _ := r.Client("CLNT004")
	for _, h := range c.FilenameHints {
		if _, _, ok := h.Match("NGAM_20260828_TRADES.xml"); ok {
			t.Fatal("CLNT004 matched a Northgate filename")
		}
	}
}

func TestAccountOwnerResolvesAcrossClients(t *testing.T) {
	r := repoConfig(t)
	c, acct, ok := r.AccountOwner("DE-77120-004")
	if !ok || c.ClientID != "CLNT011" {
		t.Fatalf("account owner = %v, %v", c, ok)
	}
	if acct.Name != "Northgate European Equity" {
		t.Fatalf("account name = %q", acct.Name)
	}
	if _, _, ok := r.AccountOwner("NOT-AN-ACCOUNT"); ok {
		t.Fatal("unknown account resolved to a client")
	}
}

func TestWeekendsAndHolidaysAreNotBusinessDays(t *testing.T) {
	r := repoConfig(t)
	cal, _ := r.Calendar("US_EQUITY")
	if cal.IsBusinessDay(day("2026-08-29")) { // Saturday
		t.Fatal("Saturday counted as a business day")
	}
	if cal.IsBusinessDay(day("2026-12-25")) {
		t.Fatal("Christmas counted as a business day")
	}
	if cal.HolidayName(day("2026-12-25")) == "" {
		t.Fatal("holiday name not recorded")
	}
	if !cal.IsBusinessDay(day("2026-08-28")) { // Friday
		t.Fatal("Friday should be a business day")
	}
}

func TestPreviousBusinessDaySkipsTheWeekend(t *testing.T) {
	r := repoConfig(t)
	cal, _ := r.Calendar("US_EQUITY")
	// A file landing Monday the 31st, containing Friday's business.
	got := cal.PreviousBusinessDay(day("2026-08-31"))
	if !got.Equal(day("2026-08-28")) {
		t.Fatalf("previous business day = %s, want 2026-08-28", got.Format("2006-01-02"))
	}
}

func TestLateWindowSpansBusinessDaysNotCalendarDays(t *testing.T) {
	// T minus 2 from Monday is the previous Thursday, not Saturday. Naive
	// date arithmetic here would open a slot on a day the market was shut.
	r := repoConfig(t)
	cal, _ := r.Calendar("US_EQUITY")
	got := cal.AddBusinessDays(day("2026-08-31"), -2)
	if !got.Equal(day("2026-08-27")) {
		t.Fatalf("T-2 = %s, want 2026-08-27", got.Format("2006-01-02"))
	}
	forward := cal.AddBusinessDays(day("2026-08-28"), 2)
	if !forward.Equal(day("2026-09-01")) {
		t.Fatalf("T+2 = %s, want 2026-09-01", forward.Format("2006-01-02"))
	}
}

func TestCalendarsDifferBetweenMarkets(t *testing.T) {
	// UK has a Summer Bank Holiday on 2026-08-31; the US does not. A client
	// on the wrong calendar resolves to a day their market was closed.
	r := repoConfig(t)
	uk, _ := r.Calendar("UK_EQUITY")
	us, _ := r.Calendar("US_EQUITY")
	if uk.IsBusinessDay(day("2026-08-31")) {
		t.Fatal("UK Summer Bank Holiday counted as a business day")
	}
	if !us.IsBusinessDay(day("2026-08-31")) {
		t.Fatal("US market should be open on 2026-08-31")
	}
}

// --- validation ------------------------------------------------------------

func writeConfig(t *testing.T, client string) string {
	t.Helper()
	dir := t.TempDir()
	if err := os.MkdirAll(filepath.Join(dir, "clients"), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(dir, "calendars"), 0o750); err != nil {
		t.Fatal(err)
	}
	cal := "calendar_id: TEST\nweekend: [SATURDAY, SUNDAY]\nholidays: []\n"
	if err := os.WriteFile(filepath.Join(dir, "calendars", "t.yaml"), []byte(cal), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "clients", "c.yaml"), []byte(client), 0o600); err != nil {
		t.Fatal(err)
	}
	return dir
}

const validClient = `
client_id: TEST1
client_name: Test
calendar: TEST
late_window_days: 2
accounts:
  - {id: "A-1", name: One, venues: [CME]}
expectations:
  - id: EXP-1
    domain: TRADE
    cadence: DAILY
    cuts_per_day: 1
    sides:
      internal_gl: {source_hint: GL_EXTRACT, formats: [CSV]}
      external_client: {source_hint: CME, formats: [CSV]}
`

func TestValidConfigLoads(t *testing.T) {
	if _, err := Load(writeConfig(t, validClient)); err != nil {
		t.Fatal(err)
	}
}

func TestUnknownKeyIsRejected(t *testing.T) {
	// A silently ignored typo produces a system that behaves subtly wrongly
	// for months. Failing at load is the kinder outcome.
	bad := strings.Replace(validClient, "late_window_days: 2", "late_window_dayz: 2", 1)
	_, err := Load(writeConfig(t, bad))
	if err == nil {
		t.Fatal("unknown key was accepted")
	}
	if !strings.Contains(err.Error(), "c.yaml") {
		t.Fatalf("error does not name the offending file: %v", err)
	}
}

func TestErrorsPointAtTheOffendingPath(t *testing.T) {
	cases := map[string]string{
		"cuts_per_day":     strings.Replace(validClient, "cuts_per_day: 1", "cuts_per_day: 0", 1),
		"domain":           strings.Replace(validClient, "domain: TRADE", "domain: TRADEZ", 1),
		"cadence":          strings.Replace(validClient, "cadence: DAILY", "cadence: HOURLY", 1),
		"late_window_days": strings.Replace(validClient, "late_window_days: 2", "late_window_days: 99", 1),
	}
	for path, body := range cases {
		t.Run(path, func(t *testing.T) {
			_, err := Load(writeConfig(t, body))
			if err == nil {
				t.Fatalf("invalid %s was accepted", path)
			}
			if !strings.Contains(err.Error(), path) {
				t.Fatalf("error should name %q, got: %v", path, err)
			}
		})
	}
}

func TestUnknownCalendarReferenceIsRejected(t *testing.T) {
	bad := strings.Replace(validClient, "calendar: TEST", "calendar: NOPE", 1)
	_, err := Load(writeConfig(t, bad))
	if err == nil || !strings.Contains(err.Error(), "unknown calendar") {
		t.Fatalf("want an unknown-calendar error, got %v", err)
	}
}

func TestInvalidRegexIsRejectedAtLoad(t *testing.T) {
	bad := validClient + "filename_hints:\n  - {pattern: '^((unclosed', domain: TRADE}\n"
	_, err := Load(writeConfig(t, bad))
	if err == nil {
		t.Fatal("invalid regular expression was accepted")
	}
}

func TestDuplicateAccountIsRejected(t *testing.T) {
	bad := strings.Replace(validClient,
		`  - {id: "A-1", name: One, venues: [CME]}`,
		"  - {id: \"A-1\", name: One, venues: [CME]}\n  - {id: \"A-1\", name: Two, venues: [ICE]}", 1)
	if _, err := Load(writeConfig(t, bad)); err == nil {
		t.Fatal("duplicate account id was accepted")
	}
}
