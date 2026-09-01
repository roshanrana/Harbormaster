package web

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"sort"
	"time"

	"github.com/go-chi/chi/v5"
)

// pageData is what every template receives.
type pageData struct {
	Title   string
	Nav     string
	Summary Summary
	Data    any
}

// FieldMappingView is one row of the provenance table on the detail page.
//
// This view is the most useful screen in the product. It is where an operator
// answers "why did this column become the settlement price", and the answer has
// to be the recorded evidence rather than a plausible reconstruction.
type FieldMappingView struct {
	SourceField    string
	CanonicalField string
	Tier           string
	Confidence     float64
	Evidence       string
}

// Resolved reports whether this column was mapped at all.
func (f FieldMappingView) Resolved() bool { return f.CanonicalField != "" }

// TierClass is the CSS class for the tier badge, so the tier is legible at a
// glance rather than requiring the reader to parse text.
func (f FieldMappingView) TierClass() string {
	switch f.Tier {
	case "ALIAS":
		return "tier-alias"
	case "LOCAL":
		return "tier-local"
	case "LLM":
		return "tier-llm"
	case "HUMAN":
		return "tier-human"
	default:
		return "tier-unresolved"
	}
}

// ValueDateView is the value-date reasoning, laid out for a human.
type ValueDateView struct {
	Resolved     string
	FromFilename string
	FromContent  []string
	FromArrival  string
	Method       string
	Confidence   float64
	Mismatch     bool
	CalendarID   string
	Notes        string
}

// ArrivalDetailView is everything the detail page renders.
type ArrivalDetailView struct {
	Arrival       *ArrivalDetail
	ValueDate     ValueDateView
	Mappings      []FieldMappingView
	ReviewReasons []string
	AccountIDs    []string
	SourceHint    string
	RowCount      int64
	Fingerprint   string
	SubBatch      string
	Review        *ReviewDecision
	TierCounts    map[string]int
}

func (s *Server) render(w http.ResponseWriter, r *http.Request, name string, data pageData) {
	summary, err := s.store.Summary(r.Context())
	if err != nil {
		s.log.Error("summary failed", slog.String("error", err.Error()))
	}
	data.Summary = summary
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := s.templates.ExecuteTemplate(w, name, data); err != nil {
		s.log.Error("template failed",
			slog.String("template", name), slog.String("error", err.Error()))
	}
}

func (s *Server) pageBoard(w http.ResponseWriter, r *http.Request) {
	rows, err := s.store.Arrivals(r.Context(), s.arrivalFilter(r))
	if err != nil {
		s.fail(w, r, err)
		return
	}
	// HTMX swaps just the table body on a poll, so the page frame is not
	// re-sent every few seconds.
	if r.Header.Get("HX-Request") == "true" {
		s.renderPartial(w, r, "arrival_rows", rows)
		return
	}
	s.render(w, r, "board", pageData{Title: "Arrivals", Nav: "board", Data: rows})
}

func (s *Server) pageQuarantine(w http.ResponseWriter, r *http.Request) {
	rows, err := s.store.Quarantine(r.Context())
	if err != nil {
		s.fail(w, r, err)
		return
	}
	if r.Header.Get("HX-Request") == "true" {
		s.renderPartial(w, r, "quarantine_rows", rows)
		return
	}
	s.render(w, r, "quarantine", pageData{Title: "Review queue", Nav: "quarantine", Data: rows})
}

func (s *Server) pageSlots(w http.ResponseWriter, r *http.Request) {
	slots, err := s.store.Slots(r.Context(), r.URL.Query().Get("state"),
		r.URL.Query().Get("value_date"))
	if err != nil {
		s.fail(w, r, err)
		return
	}
	alerts, err := s.store.Alerts(r.Context(), false)
	if err != nil {
		s.fail(w, r, err)
		return
	}
	s.render(w, r, "slots", pageData{
		Title: "Slots", Nav: "slots",
		Data: struct {
			Slots  []SlotRow
			Alerts []AlertRow
		}{slots, alerts},
	})
}

func (s *Server) pageArrival(w http.ResponseWriter, r *http.Request) {
	detail, err := s.store.Arrival(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		s.fail(w, r, err)
		return
	}
	detail.Classification = MaskAccountsInClassification(detail.Classification)

	view := buildDetailView(detail)
	if review, err := s.store.Review(r.Context(), detail.ArrivalID); err == nil {
		view.Review = review
	}
	s.render(w, r, "arrival", pageData{
		Title: detail.OriginalName, Nav: "board", Data: view,
	})
}

func (s *Server) renderPartial(w http.ResponseWriter, r *http.Request, name string, data any) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := s.templates.ExecuteTemplate(w, name, data); err != nil {
		s.log.Error("partial failed",
			slog.String("template", name), slog.String("error", err.Error()))
	}
	_ = r
}

// buildDetailView unpacks the stored classification payload for rendering.
//
// The payload is protojson, so keys are camelCase. Decoding it here rather than
// in the template keeps the template free of conditionals about wire format.
func buildDetailView(detail *ArrivalDetail) ArrivalDetailView {
	view := ArrivalDetailView{Arrival: detail, TierCounts: map[string]int{}}
	if len(detail.Classification) == 0 {
		return view
	}

	var payload struct {
		SourceHint string   `json:"sourceHint"`
		AccountIDs []string `json:"accountIds"`
		RowCount   any      `json:"rowCount"`
		ValueDate  struct {
			Resolved        string   `json:"resolved"`
			FromFilename    string   `json:"fromFilename"`
			FromContent     []string `json:"fromContent"`
			FromArrival     string   `json:"fromArrival"`
			Method          string   `json:"method"`
			Confidence      float64  `json:"confidence"`
			MismatchFlagged bool     `json:"mismatchFlagged"`
			CalendarID      string   `json:"calendarId"`
			Notes           string   `json:"notes"`
		} `json:"valueDate"`
		FieldMappings []struct {
			SourceField    string  `json:"sourceField"`
			CanonicalField string  `json:"canonicalField"`
			Tier           string  `json:"tier"`
			Confidence     float64 `json:"confidence"`
			Evidence       string  `json:"evidence"`
		} `json:"fieldMappings"`
		ReviewReasons       []string `json:"reviewReasons"`
		TemplateFingerprint string   `json:"templateFingerprint"`
		SubBatchIndex       any      `json:"subBatchIndex"`
		SubBatchTotal       any      `json:"subBatchTotal"`
	}
	if err := json.Unmarshal(detail.Classification, &payload); err != nil {
		return view
	}

	view.SourceHint = payload.SourceHint
	view.AccountIDs = payload.AccountIDs
	view.RowCount = asInt64(payload.RowCount)
	view.ReviewReasons = payload.ReviewReasons
	view.Fingerprint = payload.TemplateFingerprint

	total := asInt64(payload.SubBatchTotal)
	if total > 1 {
		view.SubBatch = fmt.Sprintf("%d of %d", asInt64(payload.SubBatchIndex)+1, total)
	}

	view.ValueDate = ValueDateView{
		Resolved:     payload.ValueDate.Resolved,
		FromFilename: payload.ValueDate.FromFilename,
		FromContent:  payload.ValueDate.FromContent,
		FromArrival:  payload.ValueDate.FromArrival,
		Method:       payload.ValueDate.Method,
		Confidence:   payload.ValueDate.Confidence,
		Mismatch:     payload.ValueDate.MismatchFlagged,
		CalendarID:   payload.ValueDate.CalendarID,
		Notes:        payload.ValueDate.Notes,
	}

	for _, m := range payload.FieldMappings {
		tier := trimEnumPrefix(m.Tier, "RESOLUTION_TIER_")
		if tier == "" {
			tier = "UNRESOLVED"
		}
		view.TierCounts[tier]++
		view.Mappings = append(view.Mappings, FieldMappingView{
			SourceField:    m.SourceField,
			CanonicalField: m.CanonicalField,
			Tier:           tier,
			Confidence:     m.Confidence,
			Evidence:       m.Evidence,
		})
	}
	// Resolved columns first, then unresolved, so the gaps are visible at the
	// bottom rather than scattered through the table.
	sort.SliceStable(view.Mappings, func(i, j int) bool {
		a, b := view.Mappings[i], view.Mappings[j]
		if a.Resolved() != b.Resolved() {
			return a.Resolved()
		}
		return false
	})
	return view
}

func asInt64(v any) int64 {
	switch n := v.(type) {
	case float64:
		return int64(n)
	case string:
		var out int64
		_, _ = fmt.Sscanf(n, "%d", &out)
		return out
	case int64:
		return n
	default:
		return 0
	}
}

// TemplateFuncs are the helpers available to every template.
func TemplateFuncs() map[string]any {
	return map[string]any{
		"pct":  func(v float64) string { return fmt.Sprintf("%.0f%%", v*100) },
		"conf": func(v float64) string { return fmt.Sprintf("%.2f", v) },
		"shortID": func(s string) string {
			if len(s) <= 10 {
				return s
			}
			return s[:6] + "\u2026" + s[len(s)-4:]
		},
		"ago": func(t time.Time) string {
			d := time.Since(t)
			switch {
			case d < time.Minute:
				return "just now"
			case d < time.Hour:
				return fmt.Sprintf("%dm ago", int(d.Minutes()))
			case d < 24*time.Hour:
				return fmt.Sprintf("%dh ago", int(d.Hours()))
			default:
				return t.Format("2 Jan 15:04")
			}
		},
		"agoPtr": func(t *time.Time) string {
			if t == nil {
				return "—"
			}
			return t.Format("2 Jan 15:04")
		},
		"dispositionClass": func(s string) string {
			switch s {
			case "DISPATCHED":
				return "pill-ok"
			case "QUARANTINED":
				return "pill-warn"
			case "REJECTED":
				return "pill-bad"
			case "SUPPRESSED_DUPLICATE":
				return "pill-muted"
			default:
				return "pill-muted"
			}
		},
		"stateClass": func(s string) string {
			switch s {
			case "ASSIGNED":
				return "pill-ok"
			case "PARTIAL", "OPEN":
				return "pill-warn"
			case "MISSING":
				return "pill-bad"
			case "SUPERSEDED":
				return "pill-muted"
			default:
				return "pill-muted"
			}
		},
		"confClass": func(v float64) string {
			switch {
			case v >= 0.85:
				return "conf-high"
			case v >= 0.60:
				return "conf-mid"
			default:
				return "conf-low"
			}
		},
		"dash": func(s string) string {
			if s == "" {
				return "—"
			}
			return s
		},
	}
}
