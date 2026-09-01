package arrival

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"time"

	"github.com/oklog/ulid/v2"
	"google.golang.org/protobuf/types/known/timestamppb"
	hmv1 "harbormaster.dev/hm/gen/hmv1"
	"harbormaster.dev/hm/internal/audit"
	"harbormaster.dev/hm/internal/bus"
	"harbormaster.dev/hm/internal/logging"
	"harbormaster.dev/hm/internal/store/objectstore"
)

// Record is the durable row written for every arrival.
type Record struct {
	ArrivalID    string
	SHA256       string
	OriginalName string
	Ingress      string
	URI          string
	Size         int64
	DetectedAt   time.Time
}

// Recorder persists arrivals and reports duplicates.
type Recorder interface {
	Deduper
	Record(ctx context.Context, a Record) error
}

// Ingress labels where an arrival came from.
const (
	IngressFTP   = "FTP"
	IngressQueue = "QUEUE"
)

// Processor turns a stable candidate into a published ArrivalRaw.
//
// Order of operations is deliberate and worth stating, because getting it
// wrong is how a system loses files:
//
//  1. Store the payload first. Once it is in the object store, the arrival is
//     recoverable even if everything after this crashes.
//  2. Check for duplicates using the hash computed during that write.
//  3. Record the arrival row. The database constraint, not this code, is what
//     actually arbitrates a race between two instances.
//  4. Publish last. If publishing fails, the row is already durable and a
//     restart can re-publish; the alternative ordering loses the file.
type Processor struct {
	Store    objectstore.Store
	Recorder Recorder
	Bus      bus.Producer
	Audit    *audit.Chain
	Log      *slog.Logger
	Scanner  *Scanner
}

// Handle processes one candidate file end to end.
func (p *Processor) Handle(ctx context.Context, c Candidate) error {
	return p.handle(ctx, c, IngressFTP)
}

func (p *Processor) handle(ctx context.Context, c Candidate, ingress string) error {
	arrivalID := ulid.Make().String()
	ctx = logging.WithArrival(ctx, arrivalID)
	log := logging.From(ctx, p.Log)

	f, err := os.Open(c.Path) //nolint:gosec // path came from our own scanner
	if err != nil {
		return fmt.Errorf("portwatch: open %s: %w", c.Name, err)
	}
	defer func() { _ = f.Close() }()

	key := fmt.Sprintf("raw/%s/%s", time.Now().UTC().Format("2006/01/02"), arrivalID+"_"+c.Name)
	uri, size, sum, err := p.Store.Put(ctx, key, f)
	if err != nil {
		return fmt.Errorf("portwatch: store %s: %w", c.Name, err)
	}

	decision, err := p.Recorder.Check(ctx, sum, c.Name)
	if err != nil {
		return err
	}
	if decision.Suppress() {
		// Suppressed arrivals are still audited. Silently discarding them
		// would hide evidence that a client's scheduler is resending, which
		// is a real operational signal rather than noise.
		log.Info("arrival suppressed",
			slog.String("verdict", string(decision.Verdict)),
			slog.String("prior_arrival_id", decision.PriorArrivalID),
			slog.String("prior_name", decision.PriorName),
			slog.Int("seen_count", decision.SeenCount),
			slog.String("file", c.Name))
		return p.auditSuppression(ctx, arrivalID, c, sum, decision)
	}

	rec := Record{
		ArrivalID: arrivalID, SHA256: sum, OriginalName: c.Name,
		Ingress: ingress, URI: uri, Size: size, DetectedAt: time.Now().UTC(),
	}
	if err := p.Recorder.Record(ctx, rec); err != nil {
		if errors.Is(err, ErrAlreadyRecorded) {
			log.Info("arrival won by another instance", slog.String("file", c.Name))
			return nil
		}
		return err
	}

	msg := &hmv1.ArrivalRaw{
		ArrivalId:     arrivalID,
		DetectedAt:    timestamppb.New(rec.DetectedAt),
		Ingress:       ingress,
		Uri:           uri,
		OriginalName:  c.Name,
		SizeBytes:     size,
		ContentSha256: sum,
		LandingDir:    p.Scanner.dir,
		StabilityMs:   c.StabilityMS,
	}
	payload, err := bus.Encode(msg)
	if err != nil {
		return err
	}
	if err := p.Bus.Publish(ctx, bus.Message{
		Topic: bus.TopicArrivalsRaw, Key: sum, Value: payload,
	}); err != nil {
		return err
	}

	if err := p.Audit.Append(ctx, audit.Entry{
		ArrivalID: arrivalID, Component: "portwatch", DecisionType: "ARRIVAL_DETECTED",
		Inputs:  map[string]any{"file": c.Name, "size_bytes": size, "stability_ms": c.StabilityMS},
		Outcome: map[string]any{"arrival_id": arrivalID, "sha256": sum, "uri": uri},
	}); err != nil {
		return err
	}

	// Forget the path so a correction arriving under the same filename later
	// is treated as a fresh sighting rather than an already-emitted one.
	p.Scanner.Forget(c.Path)

	log.Info("arrival published",
		slog.String("file", c.Name), slog.Int64("size_bytes", size),
		slog.Int64("stability_ms", c.StabilityMS))
	return nil
}

func (p *Processor) auditSuppression(ctx context.Context, arrivalID string, c Candidate, sum string, d Decision) error {
	inputs, _ := json.Marshal(map[string]any{"file": c.Name, "sha256": sum})
	_ = inputs
	return p.Audit.Append(ctx, audit.Entry{
		ArrivalID:    d.PriorArrivalID,
		Component:    "portwatch",
		DecisionType: "ARRIVAL_SUPPRESSED",
		Inputs:       map[string]any{"file": c.Name, "sha256": sum, "candidate_arrival_id": arrivalID},
		Outcome: map[string]any{
			"verdict": string(d.Verdict), "prior_arrival_id": d.PriorArrivalID,
			"prior_name": d.PriorName, "seen_count": d.SeenCount,
		},
	})
}

// HandleQueuePayload processes an arrival that came from the queue rather than
// the landing directory.
//
// Identical to Handle apart from the recorded ingress label. Keeping one code
// path means dedupe, audit and classification behave the same for both routes,
// rather than the second route being a lightly-tested special case.
func (p *Processor) HandleQueuePayload(ctx context.Context, c Candidate) error {
	return p.handle(ctx, c, IngressQueue)
}
