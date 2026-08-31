# T-005 — Compose core profile

**Milestone:** G  **Depends on:** T-001  **Status:** `pending`

## Scope
Only these paths may be touched: `docker-compose.yml, */Dockerfile`

## Objective
Compose file with redpanda, postgres and the six service containers, each with a healthcheck and a dependency ordering.

## Acceptance criteria
- [ ] `docker compose up` reaches healthy for all services
- [ ] Cold start under 60 seconds on a developer machine
- [ ] Topics from HLD §4.1 auto-created on boot with the stated partition keys
- [ ] No Node, no JVM, no metrics stack (ADR-012, ADR-014)

## Validation
```
docker compose up -d --wait && docker compose ps
```

## Reference
02-hld.md §4.1, ADR-008 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
