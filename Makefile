.DEFAULT_GOAL := help
SHELL := /bin/bash

GO      := cd go &&
PY      := cd python && uv run
COMPOSE := docker compose

.PHONY: help
help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# The gate. CI runs this exact target; it is never reimplemented in YAML.
# Runs fully offline: no broker, no network, no API key.
# ---------------------------------------------------------------------------
.PHONY: check
check: fmt-check lint typecheck proto-check test ## Run every static and unit gate

.PHONY: fmt
fmt: ## Format Go and Python in place
	$(GO) gofmt -w $$(find . -name '*.go' -not -path './gen/*')
	$(PY) ruff format .

.PHONY: fmt-check
fmt-check: ## Fail if anything is unformatted
	@out=$$(cd go && gofmt -l $$(find . -name '*.go' -not -path './gen/*')); \
	  if [ -n "$$out" ]; then echo "unformatted Go files:"; echo "$$out"; exit 1; fi
	$(PY) ruff format --check .

.PHONY: lint
lint: ## Lint both languages
	$(GO) go vet ./...
	$(GO) golangci-lint run
	$(PY) ruff check .

.PHONY: typecheck
typecheck: ## Static type check
	$(PY) mypy src

# ---------------------------------------------------------------------------
# Contracts. Generated code is committed, so a stale checkout is a diff.
# ---------------------------------------------------------------------------
.PHONY: proto
proto: ## Regenerate Go and Python types from proto/
	buf generate

.PHONY: proto-check
proto-check: ## Lint proto and fail if generated code is stale
	buf lint
	@$(MAKE) --no-print-directory proto
	@if [ -n "$$(git status --porcelain go/gen python/src/harbormaster 2>/dev/null)" ]; then \
	  echo "generated code is stale; run 'make proto' and commit"; \
	  git --no-pager diff --stat go/gen python/src/harbormaster; exit 1; fi

.PHONY: test
test: test-go test-py ## Unit, property and contract tests

.PHONY: test-go
test-go: ## Go tests (contract fixture is emitted here for the Python side)
	$(GO) go test ./... -count=1

.PHONY: test-py
test-py: test-go ## Python tests, including the cross-language contract check
	$(PY) pytest

.PHONY: test-store
test-store: ## Store tests against a live Postgres (set HM_TEST_POSTGRES_DSN)
	$(GO) go test ./internal/store/ -count=1 -v

.PHONY: test-scenarios
test-scenarios: ## The named adversarial scenarios from requirements section 8
	$(PY) pytest ../tests/scenarios -v

# ---------------------------------------------------------------------------
# Runtime. Requires Docker; not exercisable in the build container (ADR-018).
# ---------------------------------------------------------------------------
.PHONY: up
up: ## Start the full stack
	$(COMPOSE) up -d --wait
	@echo "board: http://localhost:8080"

.PHONY: down
down: ## Stop the stack and remove volumes
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail all service logs
	$(COMPOSE) logs -f

.PHONY: seed
seed: ## Generate the reference corpus into the landing directory
	$(PY) python -m corpus.generate --out ../data/landing

.PHONY: demo
demo: ## Drive the adversarial corpus through the running stack
	./scripts/demo.sh

.PHONY: test-e2e
test-e2e: ## End-to-end test against a running stack
	$(PY) pytest ../tests/integration -v

.PHONY: verify-audit
verify-audit: ## Walk every audit hash chain and report the first break
	$(GO) go run ./cmd/controlplane -verify-audit

.PHONY: migrate
migrate: ## Apply database migrations
	$(GO) go run ./cmd/controlplane -migrate

.PHONY: clean
clean: ## Remove build and runtime artefacts
	rm -rf data logs go/bin python/.venv
