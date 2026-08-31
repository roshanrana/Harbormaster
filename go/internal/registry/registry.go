// Package registry loads and validates the client configuration that tells
// Harbormaster what to expect from whom.
//
// Two decisions shape this package.
//
// First, validation is strict and happens at load. An unknown key is an error,
// not a warning. Configuration is edited by an operations team under time
// pressure, and a silently ignored typo in "late_window_days" produces a system
// that behaves subtly wrongly for months. Failing at startup with a pointer to
// the offending file is the kinder outcome.
//
// Second, business-day arithmetic lives here rather than being reimplemented at
// each call site. Value-date resolution, late windows and deadlines all need
// "what is two business days before this date on this client's calendar", and
// three slightly different answers to that question is a bug factory.
package registry

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/goccy/go-yaml"
)

// Domain values, matching the proto enum.
const (
	DomainTrade      = "TRADE"
	DomainPosition   = "POSITION"
	DomainCash       = "CASH"
	DomainCollateral = "COLLATERAL"
)

// Recon sides.
const (
	SideInternalGL     = "INTERNAL_GL"
	SideExternalClient = "EXTERNAL_CLIENT"
)

var validDomains = map[string]bool{
	DomainTrade: true, DomainPosition: true, DomainCash: true, DomainCollateral: true,
}

var validCadences = map[string]bool{"DAILY": true, "WEEKLY": true, "MONTHLY": true}

// Account is one account belonging to a client.
type Account struct {
	ID     string   `yaml:"id"`
	Name   string   `yaml:"name"`
	Venues []string `yaml:"venues"`
}

// FilenameHint is a pattern that identifies a client's files by name.
// It is evidence, never proof: a filename date is routinely wrong, which is
// most of why this project exists.
type FilenameHint struct {
	Pattern    string            `yaml:"pattern"`
	DomainMap  map[string]string `yaml:"domain_map"`
	Domain     string            `yaml:"domain"`
	SourceHint string            `yaml:"source_hint"`

	compiled *regexp.Regexp
}

// Match reports whether a filename matches, and what the pattern revealed.
func (h *FilenameHint) Match(name string) (domain, dateText string, ok bool) {
	if h.compiled == nil {
		return "", "", false
	}
	m := h.compiled.FindStringSubmatch(name)
	if m == nil {
		return "", "", false
	}
	var rawDomain string
	for i, group := range h.compiled.SubexpNames() {
		switch group {
		case "domain":
			rawDomain = m[i]
		case "date":
			dateText = m[i]
		}
	}
	domain = h.Domain
	if rawDomain != "" {
		if mapped, found := h.DomainMap[rawDomain]; found {
			domain = mapped
		}
	}
	return domain, dateText, true
}

// SideSpec describes what is expected on one side of a reconciliation.
type SideSpec struct {
	SourceHint string   `yaml:"source_hint"`
	Formats    []string `yaml:"formats"`
}

// Sides holds both sides of an expectation.
type Sides struct {
	InternalGL     SideSpec `yaml:"internal_gl"`
	ExternalClient SideSpec `yaml:"external_client"`
}

// Expectation is one recurring reconciliation the client participates in.
type Expectation struct {
	ID     string `yaml:"id"`
	Domain string `yaml:"domain"`
	// Cadence is how often this reconciliation is expected. A weekly
	// expectation must not raise a missing-file alert on the six days it is
	// not due.
	Cadence string `yaml:"cadence"`
	// CutsPerDay is how many files of this type legitimately arrive each day.
	// This is what separates a genuine correction from an ordinary second cut
	// (FR-10), and it is configuration rather than inference because only the
	// client knows their own schedule.
	CutsPerDay          int      `yaml:"cuts_per_day"`
	Sides               Sides    `yaml:"sides"`
	ValueDateFieldHints []string `yaml:"value_date_field_hints"`
}

// Client is one counterparty's complete configuration.
type Client struct {
	ClientID       string            `yaml:"client_id"`
	ClientName     string            `yaml:"client_name"`
	Calendar       string            `yaml:"calendar"`
	LateWindowDays int               `yaml:"late_window_days"`
	Accounts       []Account         `yaml:"accounts"`
	FilenameHints  []FilenameHint    `yaml:"filename_hints"`
	Expectations   []Expectation     `yaml:"expectations"`
	FieldOverrides map[string]string `yaml:"field_overrides"`
}

// AccountByID returns an account, or false.
func (c *Client) AccountByID(id string) (Account, bool) {
	for _, a := range c.Accounts {
		if a.ID == id {
			return a, true
		}
	}
	return Account{}, false
}

// ExpectationFor returns the expectation covering a domain.
func (c *Client) ExpectationFor(domain string) (Expectation, bool) {
	for _, e := range c.Expectations {
		if e.Domain == domain {
			return e, true
		}
	}
	return Expectation{}, false
}

// Holiday is one non-business day.
type Holiday struct {
	Date string `yaml:"date"`
	Name string `yaml:"name"`
}

// Calendar is a market's business-day calendar.
type Calendar struct {
	CalendarID  string    `yaml:"calendar_id"`
	Description string    `yaml:"description"`
	Weekend     []string  `yaml:"weekend"`
	Holidays    []Holiday `yaml:"holidays"`

	weekendDays map[time.Weekday]bool
	holidaySet  map[string]string
}

// IsBusinessDay reports whether the market was open.
func (c *Calendar) IsBusinessDay(d time.Time) bool {
	if c.weekendDays[d.Weekday()] {
		return false
	}
	_, isHoliday := c.holidaySet[d.Format("2006-01-02")]
	return !isHoliday
}

// HolidayName returns the reason a date is closed, if it is a holiday.
func (c *Calendar) HolidayName(d time.Time) string { return c.holidaySet[d.Format("2006-01-02")] }

// PreviousBusinessDay returns the most recent business day strictly before d.
func (c *Calendar) PreviousBusinessDay(d time.Time) time.Time {
	for i := 0; i < 30; i++ {
		d = d.AddDate(0, 0, -1)
		if c.IsBusinessDay(d) {
			return d
		}
	}
	return d
}

// NextBusinessDay returns the first business day strictly after d.
func (c *Calendar) NextBusinessDay(d time.Time) time.Time {
	for i := 0; i < 30; i++ {
		d = d.AddDate(0, 0, 1)
		if c.IsBusinessDay(d) {
			return d
		}
	}
	return d
}

// AddBusinessDays moves n business days from d. Negative n moves backwards.
// Used for the T plus or minus 2 late window (ADR-010).
func (c *Calendar) AddBusinessDays(d time.Time, n int) time.Time {
	if n == 0 {
		return d
	}
	step := c.NextBusinessDay
	if n < 0 {
		step = c.PreviousBusinessDay
		n = -n
	}
	for i := 0; i < n; i++ {
		d = step(d)
	}
	return d
}

// BusinessDaysBetween counts business days from a to b, signed.
func (c *Calendar) BusinessDaysBetween(a, b time.Time) int {
	if a.Equal(b) {
		return 0
	}
	sign, cur, count := 1, a, 0
	if b.Before(a) {
		sign = -1
	}
	for i := 0; i < 400; i++ {
		if sign > 0 {
			cur = c.NextBusinessDay(cur)
		} else {
			cur = c.PreviousBusinessDay(cur)
		}
		count++
		if !cur.Before(b) && sign > 0 {
			break
		}
		if !cur.After(b) && sign < 0 {
			break
		}
	}
	return sign * count
}

// Registry is the loaded configuration set.
type Registry struct {
	clients   map[string]*Client
	calendars map[string]*Calendar
}

// Clients returns all clients, ordered by id for stable output.
func (r *Registry) Clients() []*Client {
	out := make([]*Client, 0, len(r.clients))
	for _, c := range r.clients {
		out = append(out, c)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ClientID < out[j].ClientID })
	return out
}

// Client returns one client by id.
func (r *Registry) Client(id string) (*Client, bool) { c, ok := r.clients[id]; return c, ok }

// Calendar returns one calendar by id.
func (r *Registry) Calendar(id string) (*Calendar, bool) { c, ok := r.calendars[id]; return c, ok }

// CalendarFor returns the calendar a client uses.
func (r *Registry) CalendarFor(clientID string) (*Calendar, bool) {
	c, ok := r.clients[clientID]
	if !ok {
		return nil, false
	}
	return r.Calendar(c.Calendar)
}

// AccountOwner finds which client owns an account id. Used by attribution
// when a filename gives no clue but the contents carry an account number.
func (r *Registry) AccountOwner(accountID string) (*Client, Account, bool) {
	for _, c := range r.Clients() {
		if a, ok := c.AccountByID(accountID); ok {
			return c, a, true
		}
	}
	return nil, Account{}, false
}

// Load reads every client and calendar under dir.
func Load(dir string) (*Registry, error) {
	r := &Registry{clients: map[string]*Client{}, calendars: map[string]*Calendar{}}

	if err := r.loadCalendars(filepath.Join(dir, "calendars")); err != nil {
		return nil, err
	}
	if err := r.loadClients(filepath.Join(dir, "clients")); err != nil {
		return nil, err
	}
	if len(r.clients) == 0 {
		return nil, fmt.Errorf("registry: no client configuration found under %s", dir)
	}
	// Cross-file validation last, so a client referencing a missing calendar
	// fails at load rather than the first time a date needs resolving.
	for _, c := range r.clients {
		if _, ok := r.calendars[c.Calendar]; !ok {
			return nil, fmt.Errorf("registry: client %s references unknown calendar %q",
				c.ClientID, c.Calendar)
		}
	}
	return r, nil
}

func (r *Registry) loadCalendars(dir string) error {
	paths, err := filepath.Glob(filepath.Join(dir, "*.yaml"))
	if err != nil {
		return fmt.Errorf("registry: glob calendars: %w", err)
	}
	for _, p := range paths {
		body, err := os.ReadFile(p) //nolint:gosec // operator-supplied config path
		if err != nil {
			return fmt.Errorf("registry: read %s: %w", p, err)
		}
		var cal Calendar
		if err := yaml.UnmarshalWithOptions(body, &cal, yaml.Strict()); err != nil {
			return fmt.Errorf("registry: %s: %w", filepath.Base(p), err)
		}
		if cal.CalendarID == "" {
			return fmt.Errorf("registry: %s: calendar_id is required", filepath.Base(p))
		}
		cal.weekendDays = map[time.Weekday]bool{}
		for _, d := range cal.Weekend {
			wd, ok := weekdayByName(d)
			if !ok {
				return fmt.Errorf("registry: %s: unknown weekend day %q", filepath.Base(p), d)
			}
			cal.weekendDays[wd] = true
		}
		cal.holidaySet = map[string]string{}
		for _, h := range cal.Holidays {
			if _, err := time.Parse("2006-01-02", h.Date); err != nil {
				return fmt.Errorf("registry: %s: holiday %q is not a YYYY-MM-DD date",
					filepath.Base(p), h.Date)
			}
			cal.holidaySet[h.Date] = h.Name
		}
		r.calendars[cal.CalendarID] = &cal
	}
	return nil
}

func (r *Registry) loadClients(dir string) error {
	paths, err := filepath.Glob(filepath.Join(dir, "*.yaml"))
	if err != nil {
		return fmt.Errorf("registry: glob clients: %w", err)
	}
	for _, p := range paths {
		body, err := os.ReadFile(p) //nolint:gosec // operator-supplied config path
		if err != nil {
			return fmt.Errorf("registry: read %s: %w", p, err)
		}
		var c Client
		// Strict rejects unknown keys. A typo that is silently ignored gives a
		// system that behaves subtly wrongly for months.
		if err := yaml.UnmarshalWithOptions(body, &c, yaml.Strict()); err != nil {
			return fmt.Errorf("registry: %s: %w", filepath.Base(p), err)
		}
		if err := validateClient(&c, filepath.Base(p)); err != nil {
			return err
		}
		if existing, dup := r.clients[c.ClientID]; dup {
			return fmt.Errorf("registry: %s: client_id %s already defined by %s",
				filepath.Base(p), c.ClientID, existing.ClientName)
		}
		r.clients[c.ClientID] = &c
	}
	return nil
}

func validateClient(c *Client, file string) error {
	where := func(path string) string { return fmt.Sprintf("registry: %s: %s", file, path) }

	if c.ClientID == "" {
		return fmt.Errorf("%s is required", where("client_id"))
	}
	if c.Calendar == "" {
		return fmt.Errorf("%s is required", where("calendar"))
	}
	if c.LateWindowDays < 0 || c.LateWindowDays > 10 {
		return fmt.Errorf("%s must be between 0 and 10, got %d",
			where("late_window_days"), c.LateWindowDays)
	}
	if len(c.Accounts) == 0 {
		return fmt.Errorf("%s must list at least one account", where("accounts"))
	}
	seenAccounts := map[string]bool{}
	for i, a := range c.Accounts {
		if a.ID == "" {
			return fmt.Errorf("%s is required", where(fmt.Sprintf("accounts[%d].id", i)))
		}
		if seenAccounts[a.ID] {
			return fmt.Errorf("%s duplicates account id %s",
				where(fmt.Sprintf("accounts[%d]", i)), a.ID)
		}
		seenAccounts[a.ID] = true
	}

	for i := range c.FilenameHints {
		h := &c.FilenameHints[i]
		re, err := regexp.Compile(h.Pattern)
		if err != nil {
			return fmt.Errorf("%s is not a valid regular expression: %w",
				where(fmt.Sprintf("filename_hints[%d].pattern", i)), err)
		}
		h.compiled = re
		if h.Domain != "" && !validDomains[h.Domain] {
			return fmt.Errorf("%s has unknown domain %q",
				where(fmt.Sprintf("filename_hints[%d]", i)), h.Domain)
		}
		for k, v := range h.DomainMap {
			if !validDomains[v] {
				return fmt.Errorf("%s maps %q to unknown domain %q",
					where(fmt.Sprintf("filename_hints[%d].domain_map", i)), k, v)
			}
		}
	}

	if len(c.Expectations) == 0 {
		return fmt.Errorf("%s must list at least one expectation", where("expectations"))
	}
	seenExp := map[string]bool{}
	for i, e := range c.Expectations {
		path := fmt.Sprintf("expectations[%d]", i)
		if e.ID == "" {
			return fmt.Errorf("%s is required", where(path+".id"))
		}
		if seenExp[e.ID] {
			return fmt.Errorf("%s duplicates expectation id %s", where(path), e.ID)
		}
		seenExp[e.ID] = true
		if !validDomains[e.Domain] {
			return fmt.Errorf("%s has unknown domain %q", where(path+".domain"), e.Domain)
		}
		if !validCadences[e.Cadence] {
			return fmt.Errorf("%s has unknown cadence %q", where(path+".cadence"), e.Cadence)
		}
		if e.CutsPerDay < 1 {
			return fmt.Errorf("%s must be at least 1", where(path+".cuts_per_day"))
		}
		if e.Sides.InternalGL.SourceHint == "" || e.Sides.ExternalClient.SourceHint == "" {
			return fmt.Errorf("%s must define both internal_gl and external_client",
				where(path+".sides"))
		}
	}

	for raw, canonical := range c.FieldOverrides {
		if strings.TrimSpace(canonical) == "" {
			return fmt.Errorf("%s maps %q to an empty canonical field",
				where("field_overrides"), raw)
		}
	}
	return nil
}

func weekdayByName(s string) (time.Weekday, bool) {
	switch strings.ToUpper(strings.TrimSpace(s)) {
	case "SUNDAY":
		return time.Sunday, true
	case "MONDAY":
		return time.Monday, true
	case "TUESDAY":
		return time.Tuesday, true
	case "WEDNESDAY":
		return time.Wednesday, true
	case "THURSDAY":
		return time.Thursday, true
	case "FRIDAY":
		return time.Friday, true
	case "SATURDAY":
		return time.Saturday, true
	}
	return 0, false
}
