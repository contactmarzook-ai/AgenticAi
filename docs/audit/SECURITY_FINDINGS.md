# Security findings

> **Security phase (2026-11-21, later):** organizations with backend-enforced tenant isolation,
> six roles (viewer, operator, developer, auditor, org admin, platform admin), server-side sessions
> with 15-minute access tokens and rotating HttpOnly refresh cookies (reuse detection, logout,
> logout-all), Microsoft Entra ID OIDC sign-in, no hard-coded JWT secret, per-address limits on
> auth and public endpoints, request-size limit, stricter headers, log redaction. **L8 resolved.**
> Tests: `backend/tests/test_tenancy_auth.py` (38). Model: `docs/SECURITY_MODEL.md`.
>
> **Phase 1 status (2026-11-21):** fixed with regression tests in `backend/tests/test_phase1_security.py`: C1, H1, M1, M2, M3, M4, M5, L1, L2 (100.64/10), L3, L4 (per-address limit), L5, L6, L7, L9 (database password), and secret masking in run history. Partially addressed: M6 (per-user concurrency cap; durable queue in Phase 2). Open: L2 DNS-rebinding window, L4 email enumeration (accepted), L8, L9 SHA/digest pinning, Starlette upgrade - all scheduled in `PHASE_ROADMAP.md`.

Scope: working branch `claude/review-96bswd` (backend, frontend, deployment). Sources: an
independent security review (read-only, with proof-of-concept scripts against a separate instance)
and confirmation checks by the audit lead. `main` is covered at the end.

**Reproduced** = demonstrated against a running instance or unit test. **Code reading** = inferred
from the cited lines, not demonstrated.

## Critical

### C1 - Same-department builder can use another user's private connections (and an admin's reach)
- Evidence: `backend/app/rbac.py` `can_edit` lets any builder edit a `department`-visible resource
  of their department; `routers/workflows.py update_draft` replaces the definition but keeps
  `owner_id`; credentials/agents are then checked against the **owner** at validation
  (`services/workflow_validator.py _credential_ok`) and run time (`services/runs.py get_credential`).
- Exploit: Bob edits Alice's department draft, adds an HTTP step using Alice's private API-key
  connection (ids are sequential), runs Test → the secret header is sent where Bob chooses. If the
  draft belongs to an admin, every connection in the platform is reachable. Also works for email,
  Slack/Teams and failure-alert connections.
- Status: **Reproduced** (two PoCs: header values arrived at an attacker sink).
- Fix (Phase 1): only the owner or an admin may edit a workflow/agent; anyone else can view,
  run, or duplicate (a duplicate is owned by the copier, so its access is the copier's).

## High

### H1 - A formula can freeze the API process (reachable from public form links)
- Evidence: `backend/app/safe_eval.py` limits only the exponent; nested powers such as
  `(((9**99)**99)**99)**99` are evaluated; Calculate interpolates `{{input.x}}` text into the formula
  (`workflow_engine.resolve_template`). Big-integer arithmetic holds the GIL.
- Status: **Reproduced** (`/healthz` timed out 3/3 after one submission).
- Fix (Phase 1): bound operand/result size and expression complexity before computing.

## Medium

| ID | Finding | Evidence | Status | Fix (phase) |
|---|---|---|---|---|
| M1 | Repeat-for-each ignores the workflow deadline (200 × 300 s Wait ≈ 16.7 h on one run thread) | `workflow_engine._run_loop` has no deadline check | Reproduced (5 s run with 1 s timeout) | Check deadline per item (1) |
| M2 | Public form / webhook submitters can override values fixed on the trigger | `routers/triggers.py` `{**trig.input, **payload}`; `form_input.check_input` keeps extra keys | Reproduced | Trigger defaults win; form links accept declared fields only (1) |
| M3 | SMTP connections bypass SSRF protection (raw sockets to any host/port) | `routers/credentials.py test_credential`, `nodes/app_nodes.py send_email` | Reproduced (signed in to 127.0.0.1 with private networks off) | Same IP checks as HTTP + port allowlist (1) |
| M4 | Admin can exfiltrate any environment secret via provider `api_key_env` | `schemas.ProviderIn` pattern `^[A-Z_][A-Z0-9_]*$`; `llm/client.resolve_api_key` | Reproduced (`CREDENTIALS_KEY` sent as Bearer token) | Only `LLM_KEY_*` variables (1) |
| M5 | Production image cannot start: `cryptography` not in `requirements.txt` | `crypto.py` imports it; clean venv install → `ModuleNotFoundError` | Reproduced (audit lead, clean venv) | Pin dependency (1) |
| M6 | Thread pools easy to exhaust: chat, agent run, Test, show-result forms run synchronously; tool timeouts do not kill threads | `routers/chat.py send_message`, `routers/agents.py run_agent_endpoint`, `tools/registry.execute` | Code reading | Per-user concurrency cap (1); durable worker queue (2) |

## Low

| ID | Finding | Evidence | Status | Fix (phase) |
|---|---|---|---|---|
| L1 | Slack/Teams connection URLs skip the host allowlist (any builder can POST anywhere public) | `nodes/app_nodes.py _post_webhook` `trusted_host=True` | Code reading | Restrict to Slack/Teams webhook domains + admin allowlist (1) |
| L2 | Outbound IP check: 100.64.0.0/10 allowed; DNS rebinding window between check and connect | `safe_http._check_ips`, `check_url` | Reproduced (100.64/10); rebinding: code reading | `not ip.is_global` (1); pin resolved IP (2) |
| L3 | Audit IP spoofable via left-most `X-Forwarded-For` | `audit.client_ip`; uvicorn `--forwarded-allow-ips='*'` | Reproduced (6.6.6.6 logged) | Use the proxy-appended (right-most) address (1) |
| L4 | Anyone can lock an account; 423 reveals that an email exists; no per-IP login limit | `routers/auth.py login` | Code reading | Per-IP failed-login limit (1); enumeration accepted and documented |
| L5 | Webhook body read before the token is checked | `routers/triggers.py _raw_body` dependency order | Code reading | Check token first (1) |
| L6 | Connection usage endpoint reveals names of workflows the caller cannot see; plain users can trigger connection tests | `routers/credentials.py usage, test_credential` | Code reading | Hide names; tests for owner/admin only (1) |
| L7 | Department editors can change others' agents/workflows (visibility, prompts, tools) | `rbac.can_edit` | Code reading (same root as C1) | Owner/admin-only edit (1) |
| L8 | No server-side logout; JWT kept 8 h in `localStorage` | `frontend/src/lib/auth.js`; no `/auth/logout` | Code reading (CSP `script-src 'self'` limits XSS) | **Resolved**: server-side sessions, `/auth/logout`, 15-min access token, HttpOnly refresh cookie |
| L9 | CI actions pinned to tags not SHAs; base images not pinned by digest; compose default `POSTGRES_PASSWORD=change-me` not rejected | `.github/workflows/ci.yml`, Dockerfiles, `.env.example` | Code reading | Reject `change-me` DB passwords (1); SHA/digest pinning (2) |

## Informational

- No egress NetworkPolicy; outbound protection relies on the application (`deploy/k8s/base/networkpolicy.yaml`).
- Production namespace enforces Pod Security `baseline` because the optional Ollama component runs as root.
- Secrets typed into plain step fields (e.g. a header value) are stored in `runs.steps[].input` and
  visible to anyone who can see the run. Phase 1 masks secret-looking keys in recorded inputs.
- Starlette 0.46.2 has published advisories for multipart parsing and FileResponse Range handling;
  the app uses neither feature. Exploitability **not verified**; upgrade in Phase 2.
- Frontend npm dependencies were **not** checked against advisories.

## Verified sound (evidence)

JWT: HS256 only, `sub`/`exp` required, role/department/active read from DB per request, token
version revokes on password/role/deactivation, production refuses dev or `change-me` secrets
(`config.validate`). Passwords: bcrypt, 72-byte limit, constant-time dummy hash, atomic lockout.
CORS: no credentials, explicit origins. Runs/chat/triggers: owner filters, trigger owner re-checked
at fire time, 32-byte tokens stored as SHA-256 and compared in constant time. All admin routes
require admin permissions (route scan: 67 routes, each with a dependency except 5 intentional public
ones). SQL via ORM only; `{{ }}` is a lookup, not evaluation; no `dangerouslySetInnerHTML`; strict CSP
with `frame-ancestors 'none'`. Outbound HTTP: no redirects, 1 MB cap, IPv4-mapped/decimal forms
blocked. Kubernetes: non-root, read-only root FS, capabilities dropped, seccomp, no service-account
token, ingress NetworkPolicies, secrets outside manifests.

## `main` branch (published)

> **Resolved:** `main` was fast-forwarded to the working branch (Phase 1). The mock SSO endpoint
> and the hard-coded JWT fallback below no longer exist anywhere; Microsoft sign-in is now real
> OIDC and disabled unless configured.

Re-verified on a running instance: unauthenticated admin token via `GET
/api/auth/sso/microsoft?role=admin` (**Critical**), hard-coded JWT fallback secret (**High**), full
tracebacks returned to clients (`services/executor.py`), no ownership checks on workflow
activate/test. **Do not deploy `main`.**
