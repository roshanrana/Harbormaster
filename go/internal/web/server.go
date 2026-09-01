package web

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"log/slog"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"google.golang.org/protobuf/types/known/timestamppb"
	hmv1 "harbormaster.dev/hm/gen/hmv1"
	"harbormaster.dev/hm/internal/bus"
	"harbormaster.dev/hm/internal/logging"
)

// Server serves the board and the API.
type Server struct {
	store     *Store
	bus       bus.Producer
	log       *slog.Logger
	events    *EventHub
	templates *TemplateSet
	static    fs.FS
	started   time.Time
}

// Options configures a Server.
type Options struct {
	Store     *Store
	Bus       bus.Producer
	Log       *slog.Logger
	Templates *TemplateSet
	Static    fs.FS
}

// NewServer builds the HTTP server.
func NewServer(o Options) *Server {
	return &Server{
		store: o.Store, bus: o.Bus, log: o.Log,
		events: NewEventHub(), templates: o.Templates, static: o.Static,
		started: time.Now().UTC(),
	}
}

// Events exposes the hub so the projector can publish board deltas.
func (s *Server) Events() *EventHub { return s.events }

// Routes builds the router.
func (s *Server) Routes() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.Recoverer)
	r.Use(s.requestLog)

	r.Get("/healthz", s.health)
	r.Get("/readyz", s.ready)

	r.Route("/api", func(api chi.Router) {
		api.Get("/summary", s.getSummary)
		api.Get("/arrivals", s.getArrivals)
		api.Get("/arrivals/{id}", s.getArrival)
		api.Get("/slots", s.getSlots)
		api.Get("/assignments", s.getAssignments)
		api.Get("/alerts", s.getAlerts)
		api.Post("/alerts/{id}/acknowledge", s.postAcknowledge)
		api.Get("/quarantine", s.getQuarantine)
		api.Post("/quarantine/{id}/decision", s.postDecision)
		api.Get("/events", s.streamEvents)
	})

	if s.static != nil {
		r.Handle("/static/*", http.StripPrefix("/static/", http.FileServer(http.FS(s.static))))
	}
	if s.templates != nil {
		r.Get("/", s.pageBoard)
		r.Get("/arrivals/{id}", s.pageArrival)
		r.Get("/quarantine", s.pageQuarantine)
		r.Get("/slots", s.pageSlots)
	}
	return r
}

// --- API handlers ----------------------------------------------------------

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status": "ok", "uptime_seconds": int(time.Since(s.started).Seconds()),
	})
}

func (s *Server) ready(w http.ResponseWriter, r *http.Request) {
	// Readiness means the projection store answers, not merely that the
	// process is alive. A control plane that reports ready while its database
	// is unreachable is worse than one that reports nothing.
	if _, err := s.store.Summary(r.Context()); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "degraded"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (s *Server) getSummary(w http.ResponseWriter, r *http.Request) {
	summary, err := s.store.Summary(r.Context())
	if err != nil {
		s.fail(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, summary)
}

func (s *Server) getArrivals(w http.ResponseWriter, r *http.Request) {
	rows, err := s.store.Arrivals(r.Context(), s.arrivalFilter(r))
	if err != nil {
		s.fail(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

func (s *Server) arrivalFilter(r *http.Request) ArrivalFilter {
	q := r.URL.Query()
	f := ArrivalFilter{
		ClientID:    q.Get("client"),
		Disposition: q.Get("state"),
		ValueDate:   q.Get("value_date"),
	}
	if raw := q.Get("since"); raw != "" {
		if t, err := time.Parse(time.RFC3339, raw); err == nil {
			f.Since = t
		}
	}
	if raw := q.Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil {
			f.Limit = n
		}
	}
	return f
}

func (s *Server) getArrival(w http.ResponseWriter, r *http.Request) {
	detail, err := s.store.Arrival(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		s.fail(w, r, err)
		return
	}
	detail.Classification = MaskAccountsInClassification(detail.Classification)
	writeJSON(w, http.StatusOK, detail)
}

func (s *Server) getSlots(w http.ResponseWriter, r *http.Request) {
	rows, err := s.store.Slots(r.Context(), r.URL.Query().Get("state"),
		r.URL.Query().Get("value_date"))
	if err != nil {
		s.fail(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

func (s *Server) getAssignments(w http.ResponseWriter, r *http.Request) {
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	rows, err := s.store.Assignments(r.Context(), limit)
	if err != nil {
		s.fail(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

func (s *Server) getAlerts(w http.ResponseWriter, r *http.Request) {
	rows, err := s.store.Alerts(r.Context(), r.URL.Query().Get("all") == "true")
	if err != nil {
		s.fail(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

func (s *Server) postAcknowledge(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Reviewer string `json:"reviewer"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	if body.Reviewer == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "acknowledging an alert requires a named reviewer",
		})
		return
	}
	if err := s.store.AcknowledgeAlert(r.Context(), chi.URLParam(r, "id"), body.Reviewer); err != nil {
		s.fail(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "acknowledged"})
}

func (s *Server) getQuarantine(w http.ResponseWriter, r *http.Request) {
	rows, err := s.store.Quarantine(r.Context())
	if err != nil {
		s.fail(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

// postDecision records a four-eyes review and publishes it downstream.
//
// The decision is persisted before it is published. If publishing fails the
// decision still exists and can be republished; the reverse ordering would
// allow a released arrival with no record of who released it, which is the one
// outcome FR-32 exists to prevent.
func (s *Server) postDecision(w http.ResponseWriter, r *http.Request) {
	var decision ReviewDecision
	if err := json.NewDecoder(r.Body).Decode(&decision); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "malformed decision body"})
		return
	}
	decision.ArrivalID = chi.URLParam(r, "id")

	if err := s.store.RecordReview(r.Context(), decision); err != nil {
		if errors.Is(err, ErrAlreadyReviewed) {
			writeJSON(w, http.StatusConflict, map[string]string{
				"error": "this arrival has already been reviewed",
			})
			return
		}
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	msg := &hmv1.ReviewDecision{
		ArrivalId:           decision.ArrivalID,
		Reviewer:            decision.Reviewer,
		Decision:            decision.Decision,
		CorrectedClientId:   decision.CorrectedClientID,
		CorrectedValueDate:  decision.CorrectedValueDate,
		PromoteToDictionary: decision.PromoteToDictionary,
		Notes:               decision.Notes,
		DecidedAt:           timestamppb.Now(),
	}
	for source, canonical := range decision.CorrectedMappings {
		msg.CorrectedMappings = append(msg.CorrectedMappings, &hmv1.FieldMapping{
			SourceField:    source,
			CanonicalField: canonical,
			Tier:           hmv1.ResolutionTier_RESOLUTION_TIER_HUMAN,
			Confidence:     1.0,
			Evidence:       "corrected by " + decision.Reviewer,
		})
	}
	payload, err := bus.Encode(msg)
	if err != nil {
		s.fail(w, r, err)
		return
	}
	if err := s.bus.Publish(r.Context(), bus.Message{
		Topic: bus.TopicReviewDecisions, Key: decision.ArrivalID, Value: payload,
	}); err != nil {
		// The decision is durable, so this is recoverable rather than lost.
		s.log.Error("review recorded but not published",
			slog.String("arrival_id", decision.ArrivalID), slog.String("error", err.Error()))
		writeJSON(w, http.StatusAccepted, map[string]string{
			"status": "recorded", "warning": "decision saved but not yet published downstream",
		})
		return
	}

	s.events.Publish(Event{Kind: "review", ArrivalID: decision.ArrivalID})
	writeJSON(w, http.StatusOK, map[string]string{"status": "recorded"})
}

// --- SSE -------------------------------------------------------------------

// Event is a board delta pushed to connected browsers.
type Event struct {
	Kind      string `json:"kind"`
	ArrivalID string `json:"arrival_id,omitempty"`
	ClientID  string `json:"client_id,omitempty"`
	Summary   string `json:"summary,omitempty"`
}

// EventHub fans board deltas out to connected clients.
//
// Subscribers get a buffered channel and a slow one is dropped rather than
// allowed to block the publisher. A browser tab that stopped reading must not
// be able to stall the projector.
type EventHub struct {
	mu          sync.RWMutex
	subscribers map[chan Event]struct{}
}

// NewEventHub returns an empty hub.
func NewEventHub() *EventHub {
	return &EventHub{subscribers: make(map[chan Event]struct{})}
}

// Subscribe registers a listener and returns it with an unsubscribe function.
func (h *EventHub) Subscribe() (<-chan Event, func()) {
	ch := make(chan Event, 32)
	h.mu.Lock()
	h.subscribers[ch] = struct{}{}
	h.mu.Unlock()
	return ch, func() {
		h.mu.Lock()
		if _, ok := h.subscribers[ch]; ok {
			delete(h.subscribers, ch)
			close(ch)
		}
		h.mu.Unlock()
	}
}

// Publish sends an event to every subscriber, skipping any that are full.
func (h *EventHub) Publish(e Event) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	for ch := range h.subscribers {
		select {
		case ch <- e:
		default:
		}
	}
}

// Subscribers reports the current listener count. Used by tests.
func (h *EventHub) Subscribers() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.subscribers)
}

func (s *Server) streamEvents(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming unsupported", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	events, unsubscribe := s.events.Subscribe()
	defer unsubscribe()

	// An immediate comment so the client knows the stream is live rather than
	// merely accepted.
	_, _ = fmt.Fprint(w, ": connected\n\n")
	flusher.Flush()

	keepalive := time.NewTicker(20 * time.Second)
	defer keepalive.Stop()

	for {
		select {
		case <-r.Context().Done():
			return
		case <-keepalive.C:
			_, _ = fmt.Fprint(w, ": keepalive\n\n")
			flusher.Flush()
		case e, open := <-events:
			if !open {
				return
			}
			payload, err := json.Marshal(e)
			if err != nil {
				continue
			}
			_, _ = fmt.Fprintf(w, "event: %s\ndata: %s\n\n", e.Kind, payload)
			flusher.Flush()
		}
	}
}

// --- helpers ---------------------------------------------------------------

func (s *Server) requestLog(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		ctx := logging.WithCorrelation(r.Context(), middleware.GetReqID(r.Context()))
		next.ServeHTTP(w, r.WithContext(ctx))
		if r.URL.Path != "/healthz" && r.URL.Path != "/readyz" {
			logging.From(ctx, s.log).Debug("request",
				slog.String("method", r.Method), slog.String("path", r.URL.Path),
				slog.Duration("took", time.Since(start)))
		}
	})
}

func (s *Server) fail(w http.ResponseWriter, r *http.Request, err error) {
	if errors.Is(err, ErrNotFound) {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	logging.From(r.Context(), s.log).Error("request failed", slog.String("error", err.Error()))
	writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "internal error"})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

// Serve runs the HTTP server until ctx is cancelled.
func (s *Server) Serve(ctx context.Context, addr string) error {
	srv := &http.Server{
		Addr:              addr,
		Handler:           s.Routes(),
		ReadHeaderTimeout: 10 * time.Second,
	}
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdown)
	}()
	s.log.Info("serving", slog.String("addr", addr))
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return fmt.Errorf("web: serve: %w", err)
	}
	return nil
}
