package contract

import (
	"os"
	"testing"
	"time"

	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/types/known/timestamppb"
	hmv1 "harbormaster.dev/hm/gen/hmv1"
)

// Emits a protojson fixture that the Python side reads back and compares.
// This is the guard that makes ADR-003 real: if the two languages ever disagree
// about the contract, this test fails at build time rather than in production.
func TestEmitFixture(t *testing.T) {
	msg := &hmv1.ArrivalClassified{
		ArrivalId:        "01JCTESTARRIVAL0000000001",
		ClassifiedAt:     timestamppb.New(time.Date(2026, 8, 31, 6, 40, 0, 0, time.UTC)),
		Format:           hmv1.SourceFormat_SOURCE_FORMAT_CSV,
		SourceHint:       "CME",
		ClientId:         "CLNT004",
		ClientConfidence: 0.94,
		AccountIds:       []string{"8842-00119"},
		Domain:           hmv1.ProductDomain_PRODUCT_DOMAIN_TRADE,
		ReconSide:        hmv1.ReconSide_RECON_SIDE_EXTERNAL_CLIENT,
		ValueDate: &hmv1.ValueDateResolution{
			Resolved:        "2026-08-28",
			FromFilename:    "2026-08-31",
			FromContent:     []string{"2026-08-28"},
			Method:          "CONTENT_EXPLICIT",
			Confidence:      0.97,
			MismatchFlagged: true,
			CalendarId:      "US_EQUITY",
		},
		RowCount: 1421,
		FieldMappings: []*hmv1.FieldMapping{
			{SourceField: "Px_Sett", CanonicalField: "settlement_price",
				Tier: hmv1.ResolutionTier_RESOLUTION_TIER_ALIAS, Confidence: 1.0, Evidence: "alias:settleprice"},
			{SourceField: "Price", CanonicalField: "trade_price",
				Tier: hmv1.ResolutionTier_RESOLUTION_TIER_LOCAL, Confidence: 0.81, Evidence: "structural:varies-per-row"},
		},
		CanonicalUri:        "fs:///data/canonical/01JCTESTARRIVAL0000000001.parquet",
		OverallConfidence:   0.91,
		Disposition:         hmv1.ArrivalDisposition_ARRIVAL_DISPOSITION_DISPATCHED,
		TemplateFingerprint: "tf_9f2c1a",
		SubBatchIndex:       0,
		SubBatchTotal:       1,
	}
	b, err := protojson.Marshal(msg)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if err := os.WriteFile("fixture_arrival_classified.json", b, 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}

	var back hmv1.ArrivalClassified
	if err := protojson.Unmarshal(b, &back); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if back.GetValueDate().GetResolved() != "2026-08-28" || !back.GetValueDate().GetMismatchFlagged() {
		t.Fatal("go round-trip lost value-date detail")
	}
	if len(back.GetFieldMappings()) != 2 {
		t.Fatalf("want 2 mappings, got %d", len(back.GetFieldMappings()))
	}
}
