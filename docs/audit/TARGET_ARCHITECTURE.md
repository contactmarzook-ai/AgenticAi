# Target architecture

Principle: **evolve, do not replace.** The FastAPI backend, React/Vite frontend, SQLAlchemy data
layer, the trusted step/tool registry, the orchestrator, the workflow builder, the workflow engine,
and chat/sessions all stay. Changes below address the verified debt (`TECHNICAL_DEBT.md`) and
security findings (`SECURITY_FINDINGS.md`). No framework change is justified by the evidence.

## Kept as is

| Component | Where | Why keep |
|---|---|---|
| FastAPI app, routers, RBAC dependencies | `backend/app/main.py`, `routers/`, `rbac.py` | Every route already declares a permission; 115 tests pass |
| SQLAlchemy 2 models + Alembic | `models.py`, `alembic/` | Clean migration chain, no drift, works on SQLite and PostgreSQL |
| Trusted handler registry | `nodes/` (`@node`), `tools/registry.py`, `tools/builtin.py` | Code-registered steps/tools; definitions hold keys + config only (no user code) |
| Orchestrator (chat routing) | `services/orchestrator.py` | Pinned → keywords → LLM router → general answer; tested |
| Workflow engine + validator | `services/workflow_engine.py`, `workflow_validator.py` | Branch/join/loop semantics tested, including regressions |
| Builder UI | `frontend/src/pages/automation/` | Verified end to end; refactor internally only (C1) |
| LLM client | `llm/client.py` | Provider-agnostic OpenAI-compatible client |

## Changes

### 1. Durable run execution (addresses A1, A2, A8)

```
API pod ──INSERT runs(status=queued)──► PostgreSQL ◄──SELECT ... FOR UPDATE SKIP LOCKED── worker pods (N)
   ▲                                                       │
   └──── GET /api/runs/{id} (poll) / later: server-sent events ◄┘
```

- New `worker` process (`python -m app.worker`, same image) claims queued runs with
  `SELECT ... FOR UPDATE SKIP LOCKED`, heartbeats `runs.heartbeat_at`, and executes via the
  existing `services/runs.execute_run`. No new infrastructure (no Redis/Kafka): PostgreSQL is
  already required.
- API endpoints that today run synchronously (`/agents/{id}/run`, `/workflows/{id}/test`, chat)
  enqueue and wait with a bounded poll (keeps the current response shape), so request threads are
  not tied up and capacity scales with worker replicas.
- The scheduler only enqueues (no inline execution). Stale-run detection uses the heartbeat instead
  of `created_at`.
- SQLite/dev keeps an in-process fallback worker so local development stays one command.

### 2. Data access at scale (A3, A4, A5)

- Visibility filters move into SQL (`WHERE owner_id = :me OR visibility='public' OR
  (visibility='department' AND department=:dept)`), shared by agents, workflows and connections;
  `limit/offset` on list endpoints.
- Metrics use SQL aggregates (`percentile_cont` on PostgreSQL, Python fallback on SQLite).
- Step outputs capped (e.g. 20 kB per step in `runs.steps`, full output kept only for the final
  result), with a "truncated" marker in the UI.

### 3. Identity (product gap; enterprise requirement)

- OIDC sign-in (Microsoft Entra ID first) alongside local accounts; just-in-time provisioning with
  role/department mapping from groups/claims; local login can be disabled by admins.
- Session token stays a short-lived JWT; move from `localStorage` to an `HttpOnly; Secure;
  SameSite=Strict` cookie with a CSRF header for state-changing requests (see security findings).

### 4. Operations

- Scheduler and worker expose `/healthz` on a small HTTP port (liveness/readiness probes); both
  wait for the schema version before starting.
- Prometheus metrics endpoint (runs started/finished/failed, durations, LLM latency, queue depth).
- Browser tests (Playwright) committed under `frontend/e2e/` and run in CI against the mock LLM.

### 5. Integrations (later phases)

App-event triggers (IMAP mailbox, Microsoft 365/Google via OAuth connections), human-approval step
(pauses a run; resumes on approve/reject), sub-workflows, retrieval over documents for agents
(pgvector). Each is a new step/trigger type in the existing registries, not a new subsystem.

## Non-goals

Replacing FastAPI/React, introducing a message broker, multi-tenant database isolation, or a
plugin system that executes user-supplied code.
