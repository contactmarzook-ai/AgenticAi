# Current state report

Audit date: 2026-11-21. Method: source code read, tests and builds run, application run and driven
in a browser (Playwright), plus an independent security review (see `SECURITY_FINDINGS.md`).
**Verified** = observed by running code or reading the exact lines cited. **Assumption** = not
verifiable in this environment; stated as such.

> **Update after Phase 1 (2026-11-21):** at the owner's request `main` was fast-forwarded to the
> working branch (`e1da880..7b316c1`), so the defects below no longer exist on `main`. All Phase 1
> security fixes are in; see `SECURITY_FINDINGS.md` (Status column) and `PHASE_ROADMAP.md`.

## 1. Two codebases existed at audit time - read this first

| | `main` (GitHub default branch) | `claude/review-96bswd` (working branch) |
|---|---|---|
| Head | `e1da880` "Merge pull request #4" | `6fb7d03` "QA round 2 fixes" (16 commits ahead of `main`) |
| Backend layout | `backend/app/auth.py`, `backend/app/agents/{registry,handlers}.py`, `backend/main.py` | `backend/app/{rbac,security,audit,config}.py`, `backend/app/nodes/`, `backend/app/tools/`, `backend/app/main.py` |
| Product name in UI | AgentOS | Star Dust (technical identifiers still `agentos`) |
| Status | Published, has critical defects (below) | Not merged; no pull request open |

**Verified**: `git ls-tree origin/main` contains `backend/app/auth.py` and `backend/app/agents/*`;
`HEAD` contains neither (`git ls-tree HEAD | grep -c ...` → 0). The files named in the Phase 0 brief
(`auth.py`, `agents/`) describe `main`. The rest of this report describes the working branch unless
it says `main`.

### `main`, re-verified 2026-11-21 (worktree at `origin/main`, server on :8400)

- Tests: **15 passed** (`backend/tests`, 0.77 s). Frontend: **builds**; oxlint 1 warning.
- `GET /api/auth/sso/microsoft?role=admin` with no credentials returns an admin JWT (HTTP 200), and
  that token lists users (HTTP 200). Evidence: `backend/app/auth.py` `mock_microsoft_sso`.
- JWT secret falls back to `"fallback-secret-for-local-dev-only"` (`backend/app/auth.py` line 11).
- Creating an agent drops `output_schema` (returned `None`) - `routers/agents.py create_agent`.
- Workflow versioning broken: a second version with the same `group_id` gets a new group and
  version 1; new drafts are `is_active: true` - `routers/workflows.py create_workflow`.
- Workflow builder calls `GET /api/admin/agents` → **404**, so its agent dropdown is always empty -
  `frontend/src/components/management/WorkflowBuilder.jsx`.
- Trigger keywords `"noc,"` route the unrelated message "what is the weather" to the agent without
  the LLM - `services/orchestrator.py fast_path_route`.
- Leftover `*.orig`, `*.rej`, `patch_*.py`, `verification/*.png` files are committed.

**Conclusion**: `main` is not deployable as is. The working branch supersedes it.

## 2. Working branch: build, test and run results

| Check | Result | Evidence |
|---|---|---|
| Backend tests (SQLite) | **115 passed**, 0 failed | `pytest -q` in `backend/` |
| Backend tests (PostgreSQL 16) | **115 passed**, 0 failed | `TEST_DATABASE_URL=postgresql+psycopg://...` |
| Coverage | **86 %** of 3,767 statements | `coverage report --include='app/*'`; lowest: `nodes/flow_nodes.py` 44 %, `routers/llm_models.py` 59 %, `nodes/app_nodes.py` 63 % |
| Lint / format | ruff: all checks passed; 67 files formatted | `ruff check app tests dev`, `ruff format --check` |
| Migrations | `alembic upgrade head` from empty DB OK; `alembic check`: no drift; downgrade to base OK | revisions `74f79f69ec0d` → `6ca3b6d9fda9` → `f8f52cef6e2e` |
| Frontend lint | 0 errors, 2 warnings (fast-refresh exports in `StepForm.jsx`, `RunForm.jsx`) | `npm run lint` |
| Frontend build | **OK** (main chunk 373 kB / 116 kB gzip; builder chunk lazy-loaded 235 kB) | `npm run build` |
| Kubernetes manifests | 18 resources render and validate (strict, k8s 1.31) | `kubectl kustomize deploy/k8s/overlays/production` + `kubernetes-validate` |
| Browser walkthroughs | 4 of 5 pass; the 5th (`e2e.js`) targets the pre-redesign UI and is obsolete | `e2e2/3/4/5.js` all checks `ok`, no console errors |
| Scheduler process | Starts and polls; on an **unmigrated** DB every tick fails until migrations run | `python -m app.scheduler`, log `no such table: triggers` |
| Docker images | **Not built here** (no Docker daemon). Assumption: CI builds them | `.github/workflows/ci.yml` job `images` |
| Real LLM | **Not exercised** (Ollama/Hugging Face blocked by network policy). All AI paths ran against `backend/dev/mock_llm.py` | - |

## 3. Architecture as implemented

```
React/Vite SPA (frontend/src) ──/api──► FastAPI (backend/app/main.py, 67 routes, 13 routers)
                                            │
     rbac.py (roles user<builder<admin, permission strings, can_view/can_edit)
     services/orchestrator.py  (chat routing: pinned agent → keywords → LLM router → general)
     services/agent_runtime.py (OpenAI-style tool loop; tools = tools/registry.py)
     tools/builtin.py          (agent tools generated from the step catalogue in nodes/)
     services/workflow_engine.py + workflow_validator.py (graph runner, Kahn order, branches, loops)
     services/runs.py          (Run rows; in-process ThreadPoolExecutor for async runs)
     services/scheduler.py     (separate process: cron triggers, stale-run sweep, retention)
     SQLAlchemy 2 models (models.py, 12 tables) ── Alembic ── PostgreSQL (SQLite for dev/tests)
     llm/client.py ──► any OpenAI-compatible /v1/chat/completions (Ollama, vLLM, hosted)
```

The "trusted handler architecture" of `main` (`agents/registry.py` mapping names to Python
functions; DB stores only handler names) is preserved in evolved form: code-registered **step
handlers** (`nodes/*.py`, `@node(...)`) and **tools** generated from them (`tools/builtin.py`). Users
still cannot upload code; definitions store step keys and configuration only.

## 4. Summary of findings

- **Implemented and verified end to end**: see `EXISTING_FEATURES_MATRIX.md` (40 features; all
  marked "E2E" were driven through the UI or API against the running app).
- **Mock**: only the LLM in development/tests (`backend/dev/mock_llm.py`, `tests/conftest.py FakeLLM`).
  No mock code is reachable from production routes (`grep -ri mock backend/app` → one docstring).
- **Incomplete / missing**: SSO, OAuth connectors, app-event triggers, approval step, RAG, durable
  job queue, frontend unit tests, browser tests in CI. See `TECHNICAL_DEBT.md`.
- **Duplicated**: legacy node types `agent`/`tool`/`transform` alongside `action` steps
  (`services/workflow_validator.py:17`, `services/workflow_engine.py`); `/api/tools` is a filtered view
  of `/api/nodes`. Both kept on purpose for backward compatibility.
- **Security**: see `SECURITY_FINDINGS.md`.
- **Architecture changes needed**: see `TARGET_ARCHITECTURE.md`; plan in `PHASE_ROADMAP.md`.
