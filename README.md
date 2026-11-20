# AgentOS

A self-hosted platform for building and running AI agents and workflows on **your own models**
(Ollama, vLLM or any OpenAI-compatible endpoint), with role-based access control, audit logging
and a Kubernetes deployment.

- **Agents**: a system prompt, a model and a set of tools. Agents call tools through the standard
  OpenAI tool-calling protocol, so they work with local models that support it.
- **Workflows**: a visual graph of agent, tool, condition and transform steps. Workflows are
  versioned: you edit a draft, test it, then activate it.
- **Triggers**: run a workflow on a cron schedule or from an authenticated webhook.
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
| `builder` | Everything above, plus create/edit agents, workflows and triggers |
| `admin` | Everything, plus users, models/providers, audit log, monitoring and all runs |

Every agent and workflow has a **visibility**: `private` (owner and admins), `department`
(same department as the owner) or `public`. Visibility is enforced on listing, on running
directly, and in chat routing. Builders always create resources in their own department;
only admins can choose another.

Roles, departments and the active flag are read from the database on every request. Changing a
user's role, deactivating them or resetting their password signs them out everywhere.

## Agents and tools

Tools are Python functions registered in code (`backend/app/tools/`), each with a JSON Schema for
its arguments. Users cannot upload code. At run time:

- the model only sees the tools attached to the agent, and can only call those;
- arguments are validated against the schema before the tool runs;
- each tool call has a timeout, each run has a step cap and an overall deadline;
- a model marked "no tool calling" never gets tools (the agent editor blocks the combination).

Built-in tools: `calculator` (safe arithmetic, no `eval`), `get_current_time`,
`render_template`, `http_get` (disabled unless `HTTP_TOOL_ALLOWED_HOSTS` is set, and no redirects).

To add a tool, create a module in `backend/app/tools/` and import it in `registry.py`:

```python
from .registry import tool

@tool(
    name="lookup_customer",
    description="Look up a customer by id in the CRM.",
    parameters={"type": "object", "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"], "additionalProperties": False},
    min_role="builder",          # lowest role allowed to attach it to an agent
)
def lookup_customer(customer_id: str) -> dict:
    ...
```

**Choosing a local model:** tool calling only works with models trained for it. With Ollama,
use e.g. `qwen2.5:7b-instruct` or `llama3.1:8b` (pull them first). Mark models that cannot call
tools as such on the Models page.

## Workflows

Node types: **Input**, **Agent** (sends a message, outputs `{"answer": ...}`), **Tool**,
**Condition** (true/false branches), **Transform** (build an object) and **End**.
Each input of a node is a *mapping*: a fixed value, a field of the workflow input, a field of an
earlier node's output, or a text template such as `Summarise {{node-2.answer}} for {{input.name}}`.

A node runs after all of its predecessors have finished, if at least one incoming branch was
taken; nodes on branches that were not taken are skipped.

Lifecycle: save a **draft** → **Validate** → **Test** (runs the draft) → **Activate** (validates
again and archives the previous active version). Editing an active version saves a new draft
version; the active one keeps serving until you activate the new one. Triggers and chat always
use the active version.

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
| `JWT_EXPIRE_MINUTES` | `480` | Session length |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` | — | Creates the first admin when no users exist |
| `LLM_BASE_URL` / `LLM_DEFAULT_MODEL` | Ollama on localhost | Seeds the first provider/model when none exist; manage them afterwards on the Models page |
| `AGENT_MAX_STEPS_CAP` | `15` | Upper bound for any agent's tool steps |
| `AGENT_TIMEOUT_SECONDS` / `TOOL_TIMEOUT_SECONDS` | `300` / `30` | Per agent run / per tool call |
| `WORKFLOW_TIMEOUT_SECONDS` / `WORKFLOW_MAX_NODES` | `900` / `50` | Per workflow run |
| `USER_RUNS_PER_MINUTE` | `30` | Per-user limit on runs and chat messages (0 = off) |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` | `5` / `15` | Account lockout |
| `PASSWORD_MIN_LENGTH` | `12` | Plus three character classes |
| `HTTP_TOOL_ALLOWED_HOSTS` | empty | Hosts `http_get` may call; empty disables it |
| `LOG_JSON` | `false` | JSON logs (on in the container images) |

LLM provider API keys are never stored in the database: a provider stores the *name* of an
environment variable (e.g. `VLLM_API_KEY`) that holds the key.

## API

Interactive docs at `/api/docs` outside production. Main routes:
`/api/auth/*`, `/api/agents`, `/api/workflows`, `/api/runs`, `/api/triggers`, `/api/chat/*`,
`/api/models`, `/api/tools`, `/api/admin/{users,audit,metrics}`, and `/api/hooks/{trigger_id}`
(webhooks, authenticated with the `X-Webhook-Token` header). Health: `/healthz`, `/readyz`.

## Not included (deliberately)

Single sign-on (SAML/OIDC) and LDAP, retrieval over documents (RAG), cost budgets, a message
queue and multi-tenant isolation are not part of this version. Sign-in is local email/password,
managed by admins. Runs started through the API, schedules and webhooks execute on a thread pool
inside the API pods; a run interrupted by a pod restart is marked failed by the scheduler.
