# Phase roadmap

Ordering rule: fix what is unsafe, then what breaks at scale, then add capability. Every phase
ends with: backend tests (SQLite + PostgreSQL), frontend lint/build, browser tests, manifest
validation, updated docs, push.

## Phase 1 - Security and release hardening (done 2026-11-21)

Goal: the working branch is safe to deploy and its quality gates run in CI.

| Item | Addresses | Done when |
|---|---|---|
| Owner/admin-only editing of workflows, agents, triggers; others view/run/duplicate | C1, L7 | PoC flow returns 403; regression test |
| Safe formula evaluation with size/complexity limits | H1 | Nested-power input rejected fast; test |
| Deadline checks inside Repeat loops | M1 | Loop stops at the workflow timeout; test |
| Trigger defaults win; form links accept declared fields only | M2 | Override attempt ignored; test |
| SMTP host IP check + port allowlist | M3 | Loopback SMTP refused when private networks are off; test |
| Provider keys only from `LLM_KEY_*` variables | M4 | Other names rejected at save and at runtime; test |
| Pin `cryptography` | M5 | Clean venv install imports the app |
| Per-user concurrent-run cap | M6 (partial) | Excess requests get 429; test |
| Slack/Teams URLs limited to their webhook domains or the admin allowlist | L1 | Arbitrary host refused; test |
| `is_global` IP check | L2 (partial) | 100.64.0.0/10 refused; test |
| Right-most forwarded address in audit | L3 | Spoofed left-most entry ignored; test |
| Per-IP failed-login limit | L4 | Excess attempts from one IP get 429; test |
| Webhook token checked before the body is read | L5 | Code order + test |
| Connection usage hides invisible names; tests owner/admin only | L6 | Test |
| Refuse `change-me` database passwords in production | L9 (partial) | `config.validate` test |
| Mask secret-looking keys in recorded step inputs | Info | Test |
| Browser tests in the repository and in CI (mock LLM) | D2 | `frontend/e2e/`, CI job |
| Document the 3 undocumented settings | C4 | README/configmap |

## Phase 2 - Reliability and scale

Durable PostgreSQL-backed run queue and worker deployment (A1, A2, A8, M6); SQL-side visibility
filters and pagination (A3); SQL metrics (A4); step-output caps (A5); scheduler/worker health
probes and schema wait (A7); Prometheus metrics; pin resolved IPs for outbound HTTP (L2); CI action
SHAs and image digests (L9); Starlette upgrade; split `FlowBuilder.jsx` and add component tests
(C1/D3 in technical debt).

## Security phase (done 2026-11-21) - tenants, roles, identity

Organizations with tenant isolation on every endpoint; roles viewer / operator / developer /
auditor / org admin / platform admin; server-side sessions with rotating HttpOnly refresh cookies
(SameSite=Strict, scoped to `/api/auth`; the API itself uses bearer tokens, so no CSRF surface),
logout and logout-all (L8); Microsoft Entra ID OIDC with app-role/group → role mapping and an
option to disable local passwords; per-address rate limits on auth and public endpoints. See
`docs/SECURITY_MODEL.md`.

## Agent framework phase (done 2026-11-21) - standardized agent contracts

JSON Schema input/output contracts on every agent (default `{message} -> {answer}`), validated
by one backend implementation before and after each run (with one repair attempt for output),
workflow mappings checked against the contract at publish time, chat input mapping, capability
metadata and tags for discovery. Note: the brief referenced `AgentManagement.jsx` and handler /
input / output schema fields from the old `main`; that code was removed when the frontend was
rebuilt, so contracts were added to the current agents (system prompt + trusted step/tool
registry) rather than restored. Workflow *start forms* still use their own field list (not JSON
Schema); converting them is a follow-up.

## Workflow engine phase (2026-11-21) - reliable, durable execution

Explicit step states (pending/running/success/failed/skipped/cancelled), dependency-correct
scheduling with parallel branches, failure propagation, retries with backoff, step and run time
limits, cancellation, durable per-step records (`run_nodes`) with worker leases, heartbeats and
resume after restarts, immutable published versions with history and explicit version runs,
stronger validation (structure, branches, types between steps, malformed input), and builder
support for live validation, run status on the canvas, node logs and run history. Known limits:
a step that was running when a pod died runs again (at-least-once); a timed-out or cancelled
step's thread cannot be killed (its result is ignored).

## Phase 3 - Enterprise identity (remaining)

Group → department mapping from Entra ID; organization chosen per Entra tenant (multi-tenant
SSO); audit export; acceptance test against a real Entra tenant.

## Phase 4 - Integrations and human-in-the-loop

Approval step (pause/resume), sub-workflows, IMAP inbox trigger, OAuth connections for
Microsoft 365 and Google Workspace with their app-event triggers.

## Phase 5 - Knowledge

Document collections with pgvector retrieval as an agent tool and a workflow step; per-collection
visibility using the same RBAC.

## Owner actions (cannot be done from this environment)

- ~~Merge `claude/review-96bswd` into `main`~~ - done at the owner's request (fast-forward).
- Allow `www.vivriticapital.com` in the environment network settings to apply the brand palette.
- Provide a GPU/LLM endpoint for a real-model acceptance test (D5).
- Register the app in Entra ID and try Microsoft sign-in end to end (only tested against a
  simulated identity provider here).
