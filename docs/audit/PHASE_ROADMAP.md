# Phase roadmap

Ordering rule: fix what is unsafe, then what breaks at scale, then add capability. Every phase
ends with: backend tests (SQLite + PostgreSQL), frontend lint/build, browser tests, manifest
validation, updated docs, push.

## Phase 1 - Security and release hardening (now)

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

## Phase 3 - Enterprise identity

OIDC sign-in (Microsoft Entra ID first) with group → role/department mapping; option to disable
local passwords; HttpOnly cookie sessions with CSRF protection and server-side revocation (L8);
audit export.

## Phase 4 - Integrations and human-in-the-loop

Approval step (pause/resume), sub-workflows, IMAP inbox trigger, OAuth connections for
Microsoft 365 and Google Workspace with their app-event triggers.

## Phase 5 - Knowledge

Document collections with pgvector retrieval as an agent tool and a workflow step; per-collection
visibility using the same RBAC.

## Owner actions (cannot be done from this environment)

- Merge `claude/review-96bswd` into `main` (or retire `main`): `main` is unsafe (see
  `SECURITY_FINDINGS.md`). A pull request will be opened only when requested.
- Allow `www.vivriticapital.com` in the environment network settings to apply the brand palette.
- Provide a GPU/LLM endpoint for a real-model acceptance test (D5).
