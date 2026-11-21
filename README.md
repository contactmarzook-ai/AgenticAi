# Star Dust

*(Formerly AgentOS. Technical identifiers - image names `agentos-api` / `agentos-web`, Kubernetes resource names, environment variables - keep the old name so existing deployments keep working.)*

A self-hosted, no-code **workflow automation** platform with built-in AI, running on **your own
models** (Ollama, vLLM or any OpenAI-compatible endpoint), with role-based access control,
encrypted connections, audit logging and a Kubernetes deployment.

- **Describe it, get it**: type what you want automated in plain words; the AI drafts the
  workflow (steps, branches, form) for you to review, test and publish.
- **Visual builder** in the style of n8n/Zapier: ready-made steps with plain forms (no code),
  *Insert data* to use results of earlier steps, If/else, Switch and **Repeat for each** (loop
  over a list), per-step retries and "keep going on error", undo/redo, versions with draft /
  publish / turn off, and a test run that shows each step's result on the canvas.
- **Ready-made steps**: AI (ask, summarize, classify, extract data, translate, run an agent),
  apps (HTTP request, email, Slack, Teams), data (set fields, compose text, read JSON, calculate,
  date & time, text tools, fill template), flow (wait, stop with error). Admins can switch any
  step off.
- **Templates**: support-ticket routing, invoice approval, meeting notes, lead qualification,
  health checks, daily briefings and more, one click away.
- **Connections**: saved accounts (SMTP, Slack/Teams webhooks, API keys) encrypted at rest and
  never shown again.
- **Start it any way**: its form in the app, a **public form link** anyone can fill in without
  signing in, chat, a schedule picked in plain words ("every weekday at 09:00"), or a webhook.
- **Operate it**: History per automation with re-run, **alerts when it fails** (Slack, Teams or
  email), duplicate, export/import as a file, run-history retention.
- **Agents**: a system prompt, a model and a set of tools. The tools are the same building blocks
  as automation steps (one catalogue, one set of admin switches). Agents call them through the
  standard OpenAI tool-calling protocol, so they work with local models that support it.
- **Chat**: each message is routed to the right agent or workflow (keyword match, then an LLM
  router), or answered directly by the default model.
- **Controls**: three roles, department/visibility scoping, per-role model allowlists, a tool
  allowlist per agent, step/time limits, rate limits, login lockout and a full audit trail.

```
            ┌──────────── Ingress (TLS) ────────────┐
            │  /        → web  (nginx, React SPA)   │
            │  /api     → api  (FastAPI)            │
            └───────────────────────────────────────┘
api ──► PostgreSQL          scheduler ──► PostgreSQL   (cron triggers)
api ──► LLM endpoint(s): Ollama / vLLM / any OpenAI-compatible /v1/chat/completions
```

## Roles and access

Each user belongs to one **organization**. Organizations never see each other's agents,
workflows, runs, triggers or connections; the API answers "not found" for another
organization's ids.

| Role | Can |
|---|---|
| `viewer` | See agents and workflows shared with them, and their own run history |
| `operator` | Everything above, plus chat and run agents and workflows |
| `developer` | Everything above, plus build automations, agents, schedules/webhooks and connections |
| `auditor` | Read-only view of everything in their organization, plus audit log and monitoring |
| `org_admin` | Full control of their organization, including its users |
| `platform_admin` | Everything, in every organization, plus organizations, models and platform settings |

Sign-in is by password and/or Microsoft Entra ID. Sessions use a 15-minute access token and an
HttpOnly refresh cookie, and can be revoked server-side. Full details, the permission matrix and
Entra ID setup are in [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

Admin **Settings** control: which steps exist (for automations and agents alike; saving shows
which automations are affected), which hosts HTTP steps may call (with a separate switch for
private/intranet addresses), who may create connections, whether the AI builder is on, the
longest allowed Wait, and how long run history is kept.

Automations use agents and connections **with their owner's access**: someone running a shared
automation can only reach what its author was allowed to use, and an automation can never use
an agent or connection its owner cannot see.

Every agent and workflow has a **visibility**: `private` (owner and admins), `department`
(same department as the owner) or `public`. Visibility is enforced on listing, on running
directly, and in chat routing. Builders always create resources in their own department;
only admins can choose another.

Roles, departments and the active flag are read from the database on every request. Changing a
user's role, deactivating them or resetting their password signs them out everywhere.

## Agents and tools

Agent tools are generated from the automation step catalogue (`backend/app/nodes/`), so agents and
automations share one set of building blocks: Calculate, Date & time, Text tools, Read JSON, Fill
template, Compose text and HTTP request (the list is `AGENT_STEPS` in `backend/app/tools/builtin.py`).
Turning a step off in Settings turns it off for agents too, and HTTP requests obey the same host
allowlist. Older tool names (`calculator`, `get_current_time`, `http_get`, `render_template`) still
work as aliases. Users cannot upload code. At run time:

- the model only sees the tools attached to the agent, and can only call those;
- arguments are validated against the tool's JSON Schema before it runs;
- each tool call has a timeout, each run has a step cap and an overall deadline;
- a model marked "no tool calling" never gets tools (the agent editor blocks the combination).

To add a building block, add a step in `backend/app/nodes/` with the `@node(...)` decorator and a
form schema (`Field`s). The builder renders its form automatically; add its key to `AGENT_STEPS`
to offer it to agents as well.

### Agent contracts

Every agent has an **input contract** and an **output contract**, written in JSON Schema (object,
string, integer, number, boolean, array, nested objects, required/optional fields, allowed values,
defaults, descriptions). The default is `{message: text} → {answer: text}`. One implementation
(`backend/app/contracts.py`) checks schemas when they are saved and validates values everywhere an
agent runs (API, chat, workflow steps). The agent editor edits the same JSON Schema document,
with a field editor and a raw JSON view.

- **Before a run** the input is validated, and defaults are filled in. Invalid input is rejected
  with a list of `path: problem` items, and nothing runs.
- **After a run** the answer is parsed and validated against the output contract. A wrong
  answer gets one correction attempt, then the run fails. Every check is recorded as a step in
  run history.
- **Workflows:** a *Run an agent* step maps one value per input field, with variables allowed.
  Unknown fields, missing required fields and fixed values of the wrong type are refused when
  the workflow is published. Values that only become known while the workflow runs are checked
  at that point. The agent's output fields become variables for later steps.
- **Chat** passes the message to agents that take a message, or that have exactly one required
  text field. For other agents, chat explains which fields are needed.
- **Capabilities and tags:**
  - Capabilities (e.g. `order.lookup`) and tags (e.g. `sales`) describe what an agent can do.
  - The API adds derived ones: `tool:<name>` for each attached tool, plus `structured-input` and
    `structured-output`.
  - Filter agents with `GET /api/agents?capability=…&tag=…`.
  - The chat router sees capabilities, tags and required inputs when choosing an agent.

**Choosing a local model:** tool calling only works with models trained for it. With Ollama,
use e.g. `qwen2.5:7b-instruct` or `llama3.1:8b` (pull them first). Mark models that cannot call
tools as such on the Models page.

## Automations (workflows)

Variables use `{{input.<form field>}}` and `{{<step id>.<field>}}`; the builder inserts them for
you. A field that is exactly one variable keeps the value's type (numbers stay numbers).
New step types are added in `backend/app/nodes/` with a form schema; the UI renders them
automatically. (Older `agent`/`tool`/`transform` node types from earlier versions still run.)

**Execution.** Every step moves through these states:

`pending → running → success | failed | skipped | cancelled`

- **When a step runs:** only when *all* the steps leading into it have finished and at least
  one incoming branch was taken. Steps on branches that were not taken are skipped.
- **Parallelism:** independent branches run at the same time (`WORKFLOW_MAX_PARALLEL`).
- **Failures:** when a step fails, no new steps start; the remaining ones are recorded as
  *skipped (an earlier step failed)*.
- **Per-step settings:**
  - retries, up to 5, with a fixed or exponential delay
  - a time limit
  - "keep going", in which case the step's output is `{ "error": "..." }`
- **Whole-run time limit:** `WORKFLOW_TIMEOUT_SECONDS`.
- **Cancelling:** a queued run stops at once; a running one stops before its next step.

**Durable runs.**
- **Records:** each step is saved as it changes, in `run_nodes`, with its state, input, output,
  error, retry log, attempt count and timestamps.
- **The queue is the database:**
  - API pods execute runs.
  - A run holds a lease that is renewed every `RUN_HEARTBEAT_SECONDS`.
  - Every pod polls for queued runs and for runs whose lease expired (`RUN_STALE_SECONDS`).
- **After a restart:** an interrupted workflow resumes from its finished steps. A step that was
  running when the pod died runs again, so steps run *at least once*. Interrupted agent runs
  start over. After `RUN_MAX_RESUMES` interruptions the run fails.
- **Schedules** only queue runs; they never execute them inline.
- **Dedicated workers:** to run executions in their own deployment, set `RUN_WORKER_ENABLED=false`
  on the API and start `python -m app.worker`.

**Validation** (live in the builder, and again before testing or publishing):
- **Structure:**
  - duplicate step ids
  - connections to missing steps, self-loops, duplicate connections, anything after Finish
  - a missing Start or Finish step
  - loops, and steps that cannot be reached
- **Branches:** If/Switch branches, and If comparisons (missing values, numbers vs. text).
- **References and inputs:** unknown or disabled steps, missing required settings,
  agent/connection access, missing agent input mappings, references to steps that do not run
  earlier, and references to agent output fields that do not exist.
- **Types between steps:** e.g. a yes/no output mapped into a number input.
- **Robustness:** malformed definitions are reported, never crash.

**Repeat for each** runs one chosen step for every item of a list (up to 200), with `{{item}}`
and `{{index}}` available inside it; its output is `{ "results": [...], "count": n }`.

Inputs are checked on the server for every way an automation starts (required fields, numbers,
emails, choices, yes/no). A schedule must store values for required fields; a chat message fills
the first text field. References to steps that do not exist or do not run earlier are reported
before publishing.

Lifecycle: save a **draft** → **Test** (runs the draft; results appear on each step) →
**Publish** (validates and makes this version live, archiving the previous one). A published
version is immutable (`published_at`/`published_by` are recorded); earlier published versions
stay in the version history with their run counts, and builders can run one explicitly.
**Duplicate** copies any version into a new private draft. Editing a live
automation saves a new draft version; the live one keeps running until you publish the new one
(or *Discard draft*). **Turn off** stops schedules, form links, webhooks and chat from starting
it; it stays in the list with **Turn on**. Unsaved builder work is kept in the browser and offered
for restore after a refresh or an expired session.

**Public form links** (`/#/f/<id>/<token>`) need no account: the token is part of the link
(rotate it to revoke), submissions are rate limited (20/minute per link), and the run happens
with the automation owner's access. Optionally the submitter sees the result.

## Running locally (development)

Requirements: Python 3.12+, Node 22+.

```bash
# API (SQLite, tables created automatically)
cd backend
pip install -r requirements-dev.txt
export BOOTSTRAP_ADMIN_EMAIL=admin@example.com BOOTSTRAP_ADMIN_PASSWORD='Admin#Passw0rd!'
export LLM_BASE_URL=http://localhost:11434/v1 LLM_DEFAULT_MODEL=qwen2.5:7b-instruct   # your Ollama
uvicorn app.main:app --reload            # http://localhost:8000/api/docs

# No GPU / no Ollama? Use the mock model server instead (deterministic, not an AI):
uvicorn dev.mock_llm:app --port 9999 &   # then LLM_BASE_URL=http://localhost:9999/v1 LLM_DEFAULT_MODEL=mock-model

# Scheduler (only needed for cron triggers)
python -m app.scheduler

# Web UI
cd ../frontend && npm ci && npm run dev  # http://localhost:5173 (proxies /api to :8000)
```

Tests: `cd backend && pytest` (SQLite). Browser tests: `cd frontend && bash e2e/run.sh`
(see `frontend/e2e/README.md`). Against PostgreSQL:
`TEST_DATABASE_URL=postgresql+psycopg://user:pass@host/db pytest`.

## Deploying

- **One machine:** `docker compose` with PostgreSQL and Ollama. See [deploy/README.md](deploy/README.md#docker-compose).
- **Kubernetes:** Kustomize manifests in `deploy/k8s`. See [deploy/README.md](deploy/README.md#kubernetes).

## Configuration

All settings are environment variables (see `backend/app/config.py`). The important ones:

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | `production` refuses to start with a weak `JWT_SECRET`, SQLite, or auto-created tables, and hides `/api/docs` |
| `DATABASE_URL` | `sqlite:///./agentos.db` | Production: `postgresql+psycopg://user:pass@host:5432/db` |
| `JWT_SECRET` | random per process (dev) | Required in production: ≥ 32 random characters |
| `CREDENTIALS_KEY` | dev value | Encrypts saved connections; ≥ 32 random characters in production. Back it up |
| `JWT_EXPIRE_MINUTES` | `15` | Access-token lifetime (≤ 60 in production); renewed silently |
| `REFRESH_EXPIRE_HOURS` | `12` | Absolute session length |
| `COOKIE_SECURE` | `true` in production | HTTPS-only session cookie; `false` only for plain-HTTP trials |
| `LOCAL_LOGIN_ENABLED` | `true` | `false` = Microsoft sign-in only (platform admins keep passwords) |
| `OIDC_TENANT_ID` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` / `OIDC_REDIRECT_URI` | empty | Microsoft Entra ID sign-in (all four enable it) |
| `OIDC_ROLE_MAP` / `OIDC_DEFAULT_ROLE` / `OIDC_ORG_SLUG` / `OIDC_ALLOWED_DOMAINS` | `{}` / empty / `default` / empty | Entra app roles/groups → roles, and who may sign in; see `docs/SECURITY_MODEL.md` |
| `AUTH_REQUESTS_PER_MINUTE` | `60` | Per address: sign-in, refresh and Microsoft sign-in requests |
| `PUBLIC_REQUESTS_PER_MINUTE` | `60` | Per address: webhook and public form requests |
| `MAX_REQUEST_BYTES` | `2000000` | Larger request bodies are refused (413) |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` | — | Creates the first admin when no users exist |
| `LLM_BASE_URL` / `LLM_DEFAULT_MODEL` | Ollama on localhost | Seeds the first provider/model when none exist; manage them afterwards on the Models page |
| `AGENT_MAX_STEPS_CAP` | `15` | Upper bound for any agent's tool steps |
| `AGENT_TIMEOUT_SECONDS` / `TOOL_TIMEOUT_SECONDS` | `300` / `30` | Per agent run / per tool call |
| `WORKFLOW_TIMEOUT_SECONDS` / `WORKFLOW_MAX_NODES` | `900` / `50` | Per workflow run |
| `WORKFLOW_MAX_PARALLEL` | `4` | Steps of one run that may execute at the same time |
| `RUN_WORKER_ENABLED` / `RUN_WORKER_THREADS` | `true` / `4` | API pods execute runs, this many at a time per pod |
| `RUN_POLL_SECONDS` | `2` | How often each pod looks for queued or abandoned runs (0 = off) |
| `RUN_HEARTBEAT_SECONDS` / `RUN_STALE_SECONDS` | `10` / `60` | Lease renewal, and when a silent run is taken over |
| `RUN_MAX_RESUMES` | `3` | Interruptions after which a run fails instead of resuming |
| `USER_RUNS_PER_MINUTE` | `30` | Per-user limit on runs and chat messages (0 = off) |
| `USER_MAX_CONCURRENT_RUNS` | `5` | Runs a user may have queued or running at once (0 = off) |
| `LOGIN_IP_FAILURES_PER_10MIN` | `30` | Failed sign-ins allowed from one address per 10 minutes (0 = off) |
| `CHAT_HISTORY_MESSAGES` | `10` | Earlier chat messages sent to agents as context |
| `BCRYPT_ROUNDS` | `12` | Password hashing cost (tests use 4) |
| `LLM_API_KEY_ENV` | empty | Name of the `LLM_KEY_*` variable used by the seeded default provider |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` | `5` / `15` | Account lockout |
| `PASSWORD_MIN_LENGTH` | `12` | Plus three character classes |
| `HTTP_TOOL_ALLOWED_HOSTS` | empty | Initial outbound host allowlist; admins manage it under Settings |

Run-history retention (default 90 days), step switches, the outbound host list and similar
platform controls are changed by admins on the **Settings** page and stored in the database.
| `LOG_JSON` | `false` | JSON logs (on in the container images) |

LLM provider API keys are never stored in the database: a provider stores the *name* of an
environment variable that holds the key; its name must start with `LLM_KEY_` (e.g. `LLM_KEY_VLLM`), so providers cannot read other server secrets.

## API

Interactive docs at `/api/docs` outside production. Main routes:
`/api/auth/*`, `/api/agents`, `/api/workflows`, `/api/runs`, `/api/triggers`, `/api/chat/*`,
`/api/models`, `/api/tools`, `/api/nodes` (step catalog), `/api/credentials`, `/api/settings`,
`/api/templates`, `/api/workflows/generate` (AI builder), `/api/admin/{users,audit,metrics}`,
`/api/hooks/{trigger_id}` (webhooks, authenticated with the `X-Webhook-Token` header) and
`/api/public/forms/{trigger_id}` (public form links, `X-Form-Token` header).
Health: `/healthz`, `/readyz`.

## Not included (deliberately)

Single sign-on (SAML/OIDC) and LDAP, OAuth-based app connectors (Google, Microsoft 365,
Salesforce...), app-event triggers (new email, new file), a human-approval step, retrieval over documents (RAG), cost budgets, a
message queue and multi-tenant isolation are not part of this version. Sign-in is local email/password,
managed by admins. Runs started through the API, schedules and webhooks execute on a thread pool
inside the API pods; a run interrupted by a pod restart is marked failed by the scheduler.
