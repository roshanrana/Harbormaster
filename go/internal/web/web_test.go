package web

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"google.golang.org/protobuf/types/known/timestamppb"
	hmv1 "harbormaster.dev/hm/gen/hmv1"
	"harbormaster.dev/hm/internal/bus"
	"harbormaster.dev/hm/internal/logging"
	"harbormaster.dev/hm/internal/masking"
	"harbormaster.dev/hm/internal/store"
)

func testStore(t *testing.T) (*Store, *sql.DB) {
	t.Helper()
	dsn := os.Getenv("HM_TEST_POSTGRES_DSN")
	if dsn == "" {
		t.Skip("set HM_TEST_POSTGRES_DSN to run web tests")
	}
	db, err := store.Open(dsn)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	if _, err := db.ExecContext(ctx, `DROP TABLE IF EXISTS projection_offset, alert, assignment,
		review, template_mapping, audit_record, slot, arrival, schema_migration CASCADE`); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Migrate(ctx, db); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return NewStore(db), db
}

func seedArrival(t *testing.T, db *sql.DB, id, name string) {
	t.Helper()
	if _, err := db.Exec(`
		INSERT INTO arrival (arrival_id, content_sha256, original_name, ingress, uri,
		                     size_bytes, detected_at)
		VALUES ($1,$2,$3,'FTP','fs://raw/x.csv',1024,NOW())`,
		id, "hash"+id, name); err != nil {
		t.Fatal(err)
	}
}

func classified(id string) *hmv1.ArrivalClassified {
	return &hmv1.ArrivalClassified{
		ArrivalId:    id,
		ClassifiedAt: timestamppb.Now(),
		Format:       hmv1.SourceFormat_SOURCE_FORMAT_CSV,
		SourceHint:   "CME",
		ClientId:     "CLNT004",
		AccountIds:   []string{"8842-00119"},
		Domain:       hmv1.ProductDomain_PRODUCT_DOMAIN_TRADE,
		ReconSide:    hmv1.ReconSide_RECON_SIDE_EXTERNAL_CLIENT,
		ValueDate: &hmv1.ValueDateResolution{
			Resolved: "2026-08-28", FromFilename: "2026-08-31",
			FromContent: []string{"2026-08-28"}, Method: "CONTENT_EXPLICIT",
			Confidence: 0.97, MismatchFlagged: true, CalendarId: "US_EQUITY",
			Notes: "filename says 2026-08-31 but the contents resolve to 2026-08-28",
		},
		RowCount: 42,
		FieldMappings: []*hmv1.FieldMapping{
			{SourceField: "Px_Sett", CanonicalField: "settlement_price",
				Tier: hmv1.ResolutionTier_RESOLUTION_TIER_ALIAS, Confidence: 1.0,
				Evidence: "alias:settleprice"},
			{SourceField: "Price", CanonicalField: "trade_price",
				Tier: hmv1.ResolutionTier_RESOLUTION_TIER_LOCAL, Confidence: 0.81,
				Evidence: "varies per row within instrument groups (ratio 0.93)"},
			{SourceField: "Zorblat", CanonicalField: "",
				Tier: hmv1.ResolutionTier_RESOLUTION_TIER_UNRESOLVED, Confidence: 0,
				Evidence: "no alias match; tier2: no local match above 0.72"},
		},
		OverallConfidence:   0.93,
		Disposition:         hmv1.ArrivalDisposition_ARRIVAL_DISPOSITION_DISPATCHED,
		TemplateFingerprint: "tf_9f2c1a",
	}
}

// --- projections -----------------------------------------------------------

func TestProjectClassifiedPopulatesTheBoard(t *testing.T) {
	s, db := testStore(t)
	ctx := context.Background()
	seedArrival(t, db, "arr-1", "MCP_TRD_20260831.csv")

	if err := s.ProjectClassified(ctx, classified("arr-1")); err != nil {
		t.Fatal(err)
	}
	rows, err := s.Arrivals(ctx, ArrivalFilter{})
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 1 {
		t.Fatalf("want 1 board row, got %d", len(rows))
	}
	r := rows[0]
	if r.ClientID != "CLNT004" || r.ValueDate != "2026-08-28" || !r.MismatchFlagged {
		t.Fatalf("projection lost detail: %+v", r)
	}
	if r.Disposition != "DISPATCHED" {
		t.Fatalf("disposition = %q", r.Disposition)
	}
}

func TestProjectionIsIdempotent(t *testing.T) {
	// At-least-once delivery means this happens; a board that double-counts is
	// a board nobody trusts.
	s, db := testStore(t)
	ctx := context.Background()
	seedArrival(t, db, "arr-1", "a.csv")
	for i := 0; i < 3; i++ {
		if err := s.ProjectClassified(ctx, classified("arr-1")); err != nil {
			t.Fatal(err)
		}
	}
	rows, _ := s.Arrivals(ctx, ArrivalFilter{})
	if len(rows) != 1 {
		t.Fatalf("reprocessing produced %d rows", len(rows))
	}
}

func TestClassifiedAheadOfItsArrivalIsNotFatal(t *testing.T) {
	// Ordering across topics is not guaranteed. This is expected occasionally
	// and must not crash the projector.
	s, _ := testStore(t)
	err := s.ProjectClassified(context.Background(), classified("never-recorded"))
	if err == nil || !strings.Contains(err.Error(), "not yet recorded") {
		t.Fatalf("want a not-yet-recorded error, got %v", err)
	}
}

func TestSupersessionMarksRatherThanDeletes(t *testing.T) {
	// "This ran and was withdrawn" is a fact an auditor will ask about, and a
	// deleted row cannot answer it.
	s, _ := testStore(t)
	ctx := context.Background()
	assigned := &hmv1.BerthAssigned{
		AssignmentId: "asg-1", ClientId: "CLNT004",
		Domain: hmv1.ProductDomain_PRODUCT_DOMAIN_TRADE, ValueDate: "2026-08-28",
		ExpectationId: "EXP-1", Confidence: 0.93, EmittedAt: timestamppb.Now(),
	}
	if err := s.ProjectAssignment(ctx, assigned); err != nil {
		t.Fatal(err)
	}
	if err := s.ProjectSuperseded(ctx, &hmv1.BerthSuperseded{
		AssignmentId: "asg-1", SupersededBy: "arr-9", Reason: "correction",
		EmittedAt: timestamppb.Now(),
	}); err != nil {
		t.Fatal(err)
	}
	rows, _ := s.Assignments(ctx, 10)
	if len(rows) != 1 {
		t.Fatalf("assignment row disappeared: %d", len(rows))
	}
	if !rows[0].Voided() || rows[0].VoidedBy != "arr-9" {
		t.Fatalf("supersession not recorded: %+v", rows[0])
	}
}

func TestAlertIdIsDeterministicPerSlotAndSide(t *testing.T) {
	s, _ := testStore(t)
	ctx := context.Background()
	alert := &hmv1.MissingFileAlert{
		ClientId: "CLNT004", Domain: hmv1.ProductDomain_PRODUCT_DOMAIN_TRADE,
		ValueDate: "2026-08-28", ExpectationId: "EXP-1",
		MissingSide: hmv1.ReconSide_RECON_SIDE_EXTERNAL_CLIENT,
		Deadline:    timestamppb.Now(), EmittedAt: timestamppb.Now(),
	}
	for i := 0; i < 4; i++ {
		if err := s.ProjectAlert(ctx, alert); err != nil {
			t.Fatal(err)
		}
	}
	rows, _ := s.Alerts(ctx, false)
	if len(rows) != 1 {
		t.Fatalf("repeated sweeps produced %d alerts, want 1", len(rows))
	}
}

// --- review ----------------------------------------------------------------

func TestFourEyesRejectsASecondReviewer(t *testing.T) {
	// Enforced by the primary key, not by a check that could race.
	s, db := testStore(t)
	ctx := context.Background()
	seedArrival(t, db, "arr-q", "mystery.csv")

	first := ReviewDecision{ArrivalID: "arr-q", Reviewer: "r.chen", Decision: "APPROVE"}
	if err := s.RecordReview(ctx, first); err != nil {
		t.Fatal(err)
	}
	second := ReviewDecision{ArrivalID: "arr-q", Reviewer: "j.okafor", Decision: "REJECT"}
	if err := s.RecordReview(ctx, second); err == nil {
		t.Fatal("a second reviewer was allowed to overwrite the first decision")
	}
}

func TestReviewRequiresANamedReviewer(t *testing.T) {
	s, db := testStore(t)
	seedArrival(t, db, "arr-q", "x.csv")
	err := s.RecordReview(context.Background(),
		ReviewDecision{ArrivalID: "arr-q", Decision: "APPROVE"})
	if err == nil {
		t.Fatal("an anonymous decision was accepted")
	}
}

func TestEmptyCorrectionIsRefused(t *testing.T) {
	// Almost always a mis-click. Accepting it would dispatch an unchanged file
	// that a human believed they had fixed.
	s, db := testStore(t)
	seedArrival(t, db, "arr-q", "x.csv")
	err := s.RecordReview(context.Background(), ReviewDecision{
		ArrivalID: "arr-q", Reviewer: "r.chen", Decision: "CORRECT",
	})
	if err == nil {
		t.Fatal("a CORRECT with no corrections was accepted")
	}
}

func TestUnknownDecisionIsRefused(t *testing.T) {
	s, db := testStore(t)
	seedArrival(t, db, "arr-q", "x.csv")
	err := s.RecordReview(context.Background(),
		ReviewDecision{ArrivalID: "arr-q", Reviewer: "r", Decision: "MAYBE"})
	if err == nil {
		t.Fatal("an unknown decision verb was accepted")
	}
}

func TestReviewedItemLeavesTheQueue(t *testing.T) {
	s, db := testStore(t)
	ctx := context.Background()
	seedArrival(t, db, "arr-q", "mystery.csv")
	msg := classified("arr-q")
	msg.Disposition = hmv1.ArrivalDisposition_ARRIVAL_DISPOSITION_QUARANTINED
	if err := s.ProjectClassified(ctx, msg); err != nil {
		t.Fatal(err)
	}

	before, _ := s.Quarantine(ctx)
	if len(before) != 1 {
		t.Fatalf("quarantine should hold 1, got %d", len(before))
	}
	if err := s.RecordReview(ctx, ReviewDecision{
		ArrivalID: "arr-q", Reviewer: "r.chen", Decision: "APPROVE"}); err != nil {
		t.Fatal(err)
	}
	after, _ := s.Quarantine(ctx)
	if len(after) != 0 {
		t.Fatal("a reviewed item is still in the queue; two people could work it")
	}
}

// --- summary ---------------------------------------------------------------

func TestSummaryReportsTheQuarantineRate(t *testing.T) {
	s, db := testStore(t)
	ctx := context.Background()
	for i, disposition := range []hmv1.ArrivalDisposition{
		hmv1.ArrivalDisposition_ARRIVAL_DISPOSITION_DISPATCHED,
		hmv1.ArrivalDisposition_ARRIVAL_DISPOSITION_DISPATCHED,
		hmv1.ArrivalDisposition_ARRIVAL_DISPOSITION_DISPATCHED,
		hmv1.ArrivalDisposition_ARRIVAL_DISPOSITION_QUARANTINED,
	} {
		id := string(rune('a' + i))
		seedArrival(t, db, id, id+".csv")
		msg := classified(id)
		msg.Disposition = disposition
		if err := s.ProjectClassified(ctx, msg); err != nil {
			t.Fatal(err)
		}
	}
	summary, err := s.Summary(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if summary.Dispatched != 3 || summary.Quarantined != 1 {
		t.Fatalf("counts wrong: %+v", summary)
	}
	if summary.QuarantineRate < 0.24 || summary.QuarantineRate > 0.26 {
		t.Fatalf("quarantine rate = %f, want 0.25", summary.QuarantineRate)
	}
}

func TestSummaryPosturePrioritizesMissingFileAlerts(t *testing.T) {
	summary := Summary{
		Arrivals:       12,
		Dispatched:     8,
		Quarantined:    2,
		OpenAlerts:     1,
		Mismatches:     3,
		QuarantineRate: 0.20,
	}

	posture := summary.Posture()
	if posture.Level != "INCIDENT" || posture.Label != "Action required" {
		t.Fatalf("posture = %+v", posture)
	}
	if !strings.Contains(posture.Action, "missing-file alerts") {
		t.Fatalf("posture action does not point to alerts: %+v", posture)
	}
	if len(posture.Rationale) < 3 {
		t.Fatalf("posture should explain its inputs: %+v", posture)
	}
}

func TestSummaryPostureCallsOutQuarantineRate(t *testing.T) {
	summary := Summary{Arrivals: 20, Dispatched: 18, Quarantined: 2, QuarantineRate: 0.10}

	posture := summary.Posture()
	if posture.Level != "ATTENTION" || posture.Label != "Rate above target" {
		t.Fatalf("posture = %+v", posture)
	}
	if posture.QuarantineRateTarget != 0.05 {
		t.Fatalf("target = %f", posture.QuarantineRateTarget)
	}
	if !strings.Contains(strings.Join(posture.Rationale, " "), "target 5%") {
		t.Fatalf("posture should name the target: %+v", posture)
	}
}

// --- HTTP ------------------------------------------------------------------

func newServer(t *testing.T, s *Store) (*Server, *bus.Memory) {
	t.Helper()
	b := bus.NewMemory(4)
	templates, err := Templates()
	if err != nil {
		t.Fatal(err)
	}
	static, err := StaticAssets()
	if err != nil {
		t.Fatal(err)
	}
	srv := NewServer(Options{
		Store: s, Bus: b, Log: logging.New("test"), Templates: templates, Static: static,
	})
	t.Cleanup(func() { _ = b.Close() })
	return srv, b
}

func TestBoardPageRenders(t *testing.T) {
	s, db := testStore(t)
	seedArrival(t, db, "arr-1", "MCP_TRD_20260831.csv")
	if err := s.ProjectClassified(context.Background(), classified("arr-1")); err != nil {
		t.Fatal(err)
	}
	srv, _ := newServer(t, s)

	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	body := rec.Body.String()
	for _, want := range []string{
		"Harbormaster", "MCP_TRD_20260831.csv", "CLNT004", "2026-08-28",
		"Operational posture", "Schedule drift",
	} {
		if !strings.Contains(body, want) {
			t.Fatalf("board is missing %q", want)
		}
	}
}

func TestArrivalPageShowsProvenanceAndTheDisagreement(t *testing.T) {
	// The screen the whole project is for.
	s, db := testStore(t)
	seedArrival(t, db, "arr-1", "MCP_TRD_20260831.csv")
	if err := s.ProjectClassified(context.Background(), classified("arr-1")); err != nil {
		t.Fatal(err)
	}
	srv, _ := newServer(t, s)

	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/arrivals/arr-1", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	body := rec.Body.String()

	for _, want := range []string{
		"disagree about the value date", // the banner
		"Px_Sett", "settlement_price",   // provenance rows
		"alias:settleprice",                // recorded evidence
		"varies per row within instrument", // structural evidence
		"Zorblat", "not mapped",            // the unresolved column is shown, not hidden
		"CONTENT_EXPLICIT", "US_EQUITY", // value-date reasoning
		"tf_9f2c1a", // template fingerprint
	} {
		if !strings.Contains(body, want) {
			t.Fatalf("arrival page is missing %q", want)
		}
	}
}

func TestAccountNumbersAreMaskedInTheApi(t *testing.T) {
	s, db := testStore(t)
	seedArrival(t, db, "arr-1", "a.csv")
	if err := s.ProjectClassified(context.Background(), classified("arr-1")); err != nil {
		t.Fatal(err)
	}
	masking.SetEnabled(true)
	srv, _ := newServer(t, s)

	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/arrivals/arr-1", nil))
	body := rec.Body.String()
	if strings.Contains(body, "8842-00119") {
		t.Fatal("a full account number reached the API response")
	}
	if !strings.Contains(body, "0119") {
		t.Fatal("the masked tail should still be present for recognition")
	}
}

func TestDecisionEndpointPublishesDownstream(t *testing.T) {
	s, db := testStore(t)
	seedArrival(t, db, "arr-q", "mystery.csv")
	srv, b := newServer(t, s)

	body := strings.NewReader(`{"reviewer":"r.chen","decision":"APPROVE","notes":"checked"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/quarantine/arr-q/decision", body)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status %d: %s", rec.Code, rec.Body.String())
	}
	msgs := b.Messages(bus.TopicReviewDecisions)
	if len(msgs) != 1 {
		t.Fatalf("want 1 published decision, got %d", len(msgs))
	}
	var decoded hmv1.ReviewDecision
	if err := bus.Decode(msgs[0].Value, &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded.GetReviewer() != "r.chen" || decoded.GetDecision() != "APPROVE" {
		t.Fatalf("decision lost detail: %+v", &decoded)
	}
}

func TestOpsEndpointReturnsOperationalPosture(t *testing.T) {
	s, db := testStore(t)
	ctx := context.Background()
	seedArrival(t, db, "arr-q", "mystery.csv")
	msg := classified("arr-q")
	msg.Disposition = hmv1.ArrivalDisposition_ARRIVAL_DISPOSITION_QUARANTINED
	if err := s.ProjectClassified(ctx, msg); err != nil {
		t.Fatal(err)
	}
	srv, _ := newServer(t, s)

	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/ops", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d: %s", rec.Code, rec.Body.String())
	}

	var got OpsSnapshot
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if got.Status != "ready" || got.Posture.Level != "ATTENTION" {
		t.Fatalf("unexpected ops snapshot: %+v", got)
	}
	if got.Summary.Quarantined != 1 || got.Posture.QuarantineRateTarget != 0.05 {
		t.Fatalf("snapshot lost operational context: %+v", got)
	}
}

func TestMalformedAlertAcknowledgeBodyReturnsBadRequest(t *testing.T) {
	srv := NewServer(Options{Log: logging.New("test")})
	body := strings.NewReader(`{"reviewer":`)
	rec := httptest.NewRecorder()

	srv.Routes().ServeHTTP(rec,
		httptest.NewRequest(http.MethodPost, "/api/alerts/alert-1/acknowledge", body))

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status %d: %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "malformed alert acknowledgement body") {
		t.Fatalf("response should explain the malformed body: %s", rec.Body.String())
	}
}

func TestSecondDecisionReturnsConflict(t *testing.T) {
	s, db := testStore(t)
	seedArrival(t, db, "arr-q", "x.csv")
	srv, _ := newServer(t, s)

	post := func() int {
		body := strings.NewReader(`{"reviewer":"r.chen","decision":"APPROVE"}`)
		rec := httptest.NewRecorder()
		srv.Routes().ServeHTTP(rec,
			httptest.NewRequest(http.MethodPost, "/api/quarantine/arr-q/decision", body))
		return rec.Code
	}
	if code := post(); code != http.StatusOK {
		t.Fatalf("first decision returned %d", code)
	}
	if code := post(); code != http.StatusConflict {
		t.Fatalf("second decision returned %d, want 409", code)
	}
}

func TestUnknownArrivalIsNotFound(t *testing.T) {
	s, _ := testStore(t)
	srv, _ := newServer(t, s)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/arrivals/nope", nil))
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status %d, want 404", rec.Code)
	}
}

func TestReadinessFailsWhenTheStoreIsUnreachable(t *testing.T) {
	// A control plane that reports ready while its database is down is worse
	// than one that reports nothing.
	s, db := testStore(t)
	srv, _ := newServer(t, s)
	_ = db.Close()

	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("readyz returned %d with a dead database", rec.Code)
	}
}

func TestFiltersNarrowTheBoard(t *testing.T) {
	s, db := testStore(t)
	ctx := context.Background()
	for i, client := range []string{"CLNT004", "CLNT011"} {
		id := string(rune('a' + i))
		seedArrival(t, db, id, id+".csv")
		msg := classified(id)
		msg.ClientId = client
		if err := s.ProjectClassified(ctx, msg); err != nil {
			t.Fatal(err)
		}
	}
	srv, _ := newServer(t, s)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec,
		httptest.NewRequest(http.MethodGet, "/api/arrivals?client=CLNT011", nil))

	var rows []ArrivalRow
	if err := json.Unmarshal(rec.Body.Bytes(), &rows); err != nil {
		t.Fatal(err)
	}
	if len(rows) != 1 || rows[0].ClientID != "CLNT011" {
		t.Fatalf("filter returned %+v", rows)
	}
}

// --- SSE -------------------------------------------------------------------

func TestEventHubDropsSlowSubscribersRatherThanBlocking(t *testing.T) {
	// A browser tab that stopped reading must not stall the projector.
	hub := NewEventHub()
	_, unsubscribe := hub.Subscribe()
	defer unsubscribe()

	done := make(chan struct{})
	go func() {
		for i := 0; i < 5000; i++ {
			hub.Publish(Event{Kind: "arrival"})
		}
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("publishing blocked on a subscriber that was not reading")
	}
}

func TestEventHubUnsubscribeIsIdempotent(t *testing.T) {
	hub := NewEventHub()
	_, unsubscribe := hub.Subscribe()
	unsubscribe()
	unsubscribe()
	if hub.Subscribers() != 0 {
		t.Fatal("subscriber was not removed")
	}
}
