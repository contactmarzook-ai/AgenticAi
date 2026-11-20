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

| Role | Can |
|---|---|
| `user` | Chat; run agents and workflows shared with them; see their own runs |
| `builder` | Everything above, plus build automations, agents, schedules/webhooks and connections |
| `admin` | Everything, plus platform settings, users, models, audit log, monitoring and all runs |

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

**Choosing a local model:** tool calling only works with models trained for it. With Ollama,
use e.g. `qwen2.5:7b-instruct` or `llama3.1:8b` (pull them first). Mark models that cannot call
tools as such on the Models page.

## Automations (workflows)

Variables use `{{input.<form field>}}` and `{{<step id>.<field>}}`; the builder inserts them for
you. A field that is exactly one variable keeps the value's type (numbers stay numbers).
New step types are added in `backend/app/nodes/` with a form schema; the UI renders them
automatically. (Older `agent`/`tool`/`transform` node types from earlier versions still run.)

A step runs after all of the steps before it have finished, if at least one incoming branch was
taken; steps on branches that were not taken are skipped. A failing step can retry (up to 5
times) or "keep going", in which case its output is `{ "error": "..." }`.

**Repeat for each** runs one chosen step for every item of a list (up to 200), with `{{item}}`
and `{{index}}` available inside it; its output is `{ "results": [...], "count": n }`.

Inputs are checked on the server for every way an automation starts (required fields, numbers,
emails, choices, yes/no). A schedule must store values for required fields; a chat message fills
the first text field. References to steps that do not exist or do not run earlier are reported
before publishing.

Lifecycle: save a **draft** → **Test** (runs the draft; results appear on each step) →
**Publish** (validates and makes this version live, archiving the previous one). Editing a live
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

Tests: `cd backend && pytest` (SQLite). Against PostgreSQL:
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
| `JWT_SECRET` | dev value | ≥ 32 random characters in production |
| `CREDENTIALS_KEY` | dev value | Encrypts saved connections; ≥ 32 random characters in production. Back it up |
| `JWT_EXPIRE_MINUTES` | `480` | Session length |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` | — | Creates the first admin when no users exist |
| `LLM_BASE_URL` / `LLM_DEFAULT_MODEL` | Ollama on localhost | Seeds the first provider/model when none exist; manage them afterwards on the Models page |
| `AGENT_MAX_STEPS_CAP` | `15` | Upper bound for any agent's tool steps |
| `AGENT_TIMEOUT_SECONDS` / `TOOL_TIMEOUT_SECONDS` | `300` / `30` | Per agent run / per tool call |
| `WORKFLOW_TIMEOUT_SECONDS` / `WORKFLOW_MAX_NODES` | `900` / `50` | Per workflow run |
| `USER_RUNS_PER_MINUTE` | `30` | Per-user limit on runs and chat messages (0 = off) |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` | `5` / `15` | Account lockout |
| `PASSWORD_MIN_LENGTH` | `12` | Plus three character classes |
| `HTTP_TOOL_ALLOWED_HOSTS` | empty | Initial outbound host allowlist; admins manage it under Settings |

Run-history retention (default 90 days), step switches, the outbound host list and similar
platform controls are changed by admins on the **Settings** page and stored in the database.
| `LOG_JSON` | `false` | JSON logs (on in the container images) |

LLM provider API keys are never stored in the database: a provider stores the *name* of an
environment variable (e.g. `VLLM_API_KEY`) that holds the key.

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
