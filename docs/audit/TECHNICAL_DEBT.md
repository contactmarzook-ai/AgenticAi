# Technical debt

Each item: evidence (file:line or command), impact, and whether it is **verified** or an
**assumption**. Severity: H (blocks scale or safe operation), M (will hurt soon), L (tidy-up).
Security issues are listed separately in `SECURITY_FINDINGS.md`.

## Process and delivery

| # | Item | Evidence | Impact | Sev | Status |
|---|---|---|---|---|---|
| D1 | `main` is stale; all current work is on an unmerged branch (16 commits) | `git rev-list --count origin/main..HEAD` → 16; `main` still has `auth.py` mock SSO | Anyone deploying `main` ships the critical defects listed in the state report | H | Verified |
| D2 | Browser tests live outside the repository and do not run in CI | scripts in the session scratchpad (`e2e2`-`e5.js`); `.github/workflows/ci.yml` has no browser job | UI regressions are only caught by hand | H | Verified |
| D3 | No frontend unit/component tests | `git ls-files frontend/src | grep -c test` → 0 | Builder logic (auto-connect, rename references, undo) is untested below e2e level | M | Verified |
| D4 | Docker images never built in this environment | no Docker daemon; CI job `images` exists | First real build may fail | M | Assumption (CI not observed) |
| D5 | Real model behaviour never exercised | Ollama/HF blocked; all AI paths ran on `dev/mock_llm.py` | AI-builder draft quality and tool-calling reliability on local models unknown | H | Verified (gap) |

## Runtime architecture

| # | Item | Evidence | Impact | Sev | Status |
|---|---|---|---|---|---|
| A1 | Async runs execute on an in-process thread pool | `services/runs.py:31` `_pool = ThreadPoolExecutor(...)`, `submit_run` line 216 | A pod restart loses queued/running work (later marked failed by `fail_stale_runs`, line 220); capacity scales only with API pods; no back-pressure | H | Verified |
| A2 | Long LLM calls block request threads | sync endpoints `routers/agents.py:146 run_agent_endpoint`, `routers/workflows.py:247 test`, `routers/chat.py:71 send_message` run the whole agent/workflow in the request | Each slow run holds one of FastAPI's worker threads and a DB connection (`database.py:10` pool 10+10) for minutes | H | Verified (code) |
| A3 | List endpoints load whole tables and filter in Python | `routers/agents.py:65` `... .all() if can_view(user, a)`; `routers/workflows.py:55 list_workflows` (`_listable` after `.all()`); `routers/credentials.py list_credentials` | O(rows) per request, no pagination | M | Verified |
| A4 | Metrics computed in Python over all finished runs in the window | `routers/admin.py:67` `durations = sorted(...)` | Slow for large histories (30-day window) | M | Verified |
| A5 | Step outputs stored untruncated in `runs.steps` | `services/workflow_engine.py:325` `step.update(output=out, ...)`; HTTP bodies up to 50 kB each, loops up to 200 results | Large JSON rows; History page payloads grow | M | Verified |
| A6 | Platform settings cached 10 s per process | `services/platform_settings.py:14` | An admin disabling a step takes up to 10 s to apply on other replicas | L | Verified |
| A7 | Scheduler has no health probe and fails each tick until migrations exist | `deploy/k8s/base/scheduler.yaml` (0 probes); run log `no such table: triggers` | Silent scheduler death is not detected by Kubernetes | M | Verified |
| A8 | Scheduler executes due runs inline in its loop | `services/scheduler.py tick` → `execute_run` | One slow scheduled workflow delays every other trigger | M | Verified (code) |

## Code structure

| # | Item | Evidence | Impact | Sev | Status |
|---|---|---|---|---|---|
| C1 | `FlowBuilder.jsx` is 969 lines (canvas, palette, settings panes, test dialog) | `wc -l` | Hard to change safely; untested (D3) | M | Verified |
| C2 | Legacy node types `agent`/`tool`/`transform` still supported beside `action` | `services/workflow_validator.py:17`, `workflow_engine._execute_node` | Two ways to do the same thing in the engine | L | Verified |
| C3 | Technical identifiers say `agentos`, product says Star Dust | image names, k8s names, `localStorage` key `agentos.token`, `X-Request-ID` logger `agentos.*` | Confusing for operators | L | Verified |
| C4 | Three settings undocumented | `BCRYPT_ROUNDS`, `CHAT_HISTORY_MESSAGES`, `LLM_API_KEY_ENV` read in `config.py`, absent from README/configmap/.env.example | Operators cannot discover them | L | Verified |
| C5 | Two fast-refresh lint warnings | `StepForm.jsx:24`, `RunForm.jsx:76` export helpers next to components | Dev-only (HMR) | L | Verified |
| C6 | Coverage gaps | `nodes/flow_nodes.py` 44 %, `routers/llm_models.py` 59 %, `nodes/app_nodes.py` 63 %, `services/scheduler.py` 68 % | Least-tested code is the code talking to external systems | M | Verified |

## Product gaps (not defects)

SSO/OIDC, OAuth app connectors (Microsoft 365, Google), app-event triggers (new email/file/row),
human-approval step, sub-workflows, retrieval over documents (RAG), Vivriti brand palette (blocked:
site not reachable from this environment). See `PHASE_ROADMAP.md`.
