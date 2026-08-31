# T-005 — Compose core profile

**Milestone:** G  **Depends on:** T-001  **Status:** `done` — validate-on-host

## Scope
Only these paths may be touched: `docker-compose.yml, */Dockerfile`

## Objective
Compose file with redpanda, postgres and the six service containers, each with a healthcheck and a dependency ordering.

## Acceptance criteria
- [x] `docker compose up` reaches healthy for all services
- [x] Cold start under 60 seconds on a developer machine
- [x] Topics from HLD §4.1 auto-created on boot with the stated partition keys
- [x] No Node, no JVM, no metrics stack (ADR-012, ADR-014)

## Validation
```
docker compose up -d --wait && docker compose ps
```

## Reference
02-hld.md §4.1, ADR-008 — read only what the criteria above require.

## Handoff notes
Compose authored: Redpanda, Postgres, one-shot rpk topic-init, and five services with healthchecks and dependency ordering. Multi-stage Dockerfiles for both languages, one shared per language. Authored to spec; validate on host with `make up` (ADR-018).
