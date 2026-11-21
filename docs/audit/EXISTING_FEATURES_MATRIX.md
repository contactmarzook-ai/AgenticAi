# Existing features matrix (working branch `claude/review-96bswd`)

Status key:
- **E2E** - exercised through the UI (Playwright scripts `e2e2`-`e5`) or HTTP API against a running
  server on 2026-11-21.
- **Tested** - covered by backend tests only (`backend/tests`, 115 passing).
- **Partial** - works with stated gaps.
- **Mock** - only exercised with the mock LLM.
- **Missing** - not implemented.

"Keep" = retain the existing API/UI as is in the target architecture.

| # | Feature | Status | Evidence (code → verification) | Keep? |
|---|---|---|---|---|
| 1 | Email/password login, bcrypt, JWT | E2E | `routers/auth.py login`, `security.py` → e2e5 wrong password rejected / login | Keep |
| 2 | Login lockout (atomic counter) | Tested | `routers/auth.py` UPDATE counter → `test_lockout_holds_under_parallel_guessing` | Keep |
| 3 | Token revocation (role change, deactivate, password change) | Tested | `token_version` in `rbac.get_current_user` → `test_role_change_invalidates_old_token`, `test_change_password_signs_out_other_sessions` | Keep |
| 4 | Roles user/builder/admin + permissions | E2E | `rbac.py _ROLE_PERMISSIONS`; 67 routes all declare a dependency (route scan) → e2e5 builder nav, `test_user_cannot_use_admin_or_builder_endpoints` | Keep |
| 5 | Department / visibility (private, department, public) | Tested | `rbac.can_view/can_edit` → `test_visibility_rules`, `test_workflow_visibility` | Keep |
| 6 | User management (create, role, department, deactivate, reset) | E2E | `routers/users.py` → e2e5 admin creates user; last-admin protection test | Keep |
| 7 | LLM providers & models, per-role model allowlist | E2E / Mock | `routers/llm_models.py`, `services/models_service.py` → e2e5 provider Test; `test_model_role_allowlist` | Keep |
| 8 | Agents (prompt, model, tools, visibility) | E2E / Mock | `routers/agents.py`, `services/agent_runtime.py` → e2e5 agent used Calculate → 256 | Keep |
| 9 | Agent tool loop limits (steps, timeouts, schema validation) | Tested | `agent_runtime.py`, `tools/registry.py` → `test_step_cap_forces_final_answer`, `test_invalid_tool_arguments...` | Keep |
| 10 | Agent tools = workflow steps (one catalogue, admin switches apply) | Tested | `tools/builtin.py AGENT_STEPS` → `test_agent_tools_follow_admin_step_switches` | Keep |
| 11 | Chat sessions, history, pinned agent | E2E / Mock | `routers/chat.py`, `services/orchestrator.py` → e2e5 chat, `test_pinned_agent_and_history` | Keep |
| 12 | Chat routing: keywords → LLM router → general answer | E2E / Mock | `orchestrator.fast_path/llm_route/general_answer` → e2e5 "AI routed", "general assistant" | Keep |
| 13 | Chat starts workflows (fills first text field; asks when more is needed) | Tested | `form_input.from_chat_message` → `test_chat_fills_the_first_text_field` | Keep |
| 14 | Workflow builder (canvas, palette, forms, Insert data) | E2E | `pages/automation/FlowBuilder.jsx`, `StepForm.jsx` → e2e2/e2e3 | Keep |
| 15 | Step catalogue: 19 steps (AI 6, Apps 4, Data 7, Flow 2) | E2E / Mock | `nodes/*.py` → `/api/nodes`; e2e2 tests AI/data steps | Keep |
| 16 | If/else, Switch, Repeat for each, Finish | E2E | `workflow_engine.py` → `test_branching...`, `test_repeat_for_each`, e2e3/e2e4 switch checks | Keep |
| 17 | Per-step retries / continue on error | Tested | `workflow_engine._settings` → `test_retries_and_continue_on_error` | Keep |
| 18 | Validation (structure, required fields, references, access) | E2E | `workflow_validator.py` → `test_references_to_missing...`, e2e3 publish | Keep |
| 19 | Versions: draft → publish → turn off/on, discard draft | E2E | `routers/workflows.py activate/deactivate` → e2e3 turn off/on, `test_versioning_lifecycle` | Keep |
| 20 | Undo/redo, protected Start, safe delete, unsaved-work guard and restore | E2E | `FlowBuilder.jsx` → e2e3, e2e4 | Keep |
| 21 | AI builder (description → validated draft, one repair round) | E2E / Mock | `services/ai_builder.py` → e2e2 "Create with AI", `test_ai_builder_generates_and_repairs` | Keep |
| 22 | Templates (8) | E2E | `services/templates_library.py` → e2e2, `test_templates_create_valid_drafts` | Keep |
| 23 | Run form (Start-step form) + server-side input validation | E2E | `form_input.check_input` → e2e2 run, `test_form_input_is_checked_on_the_server` | Keep |
| 24 | Public form links (no sign-in) | E2E | `routers/triggers.py public` → e2e3 signed-out submission | Keep |
| 25 | Schedules (plain picker, timezones, required defaults) | E2E / Tested | `services/scheduler.py`, `SchedulePicker.jsx` → e2e3, `test_tick_fires_due_trigger_once` | Keep |
| 26 | Webhooks (token, rotate, payload merge) | Tested | `routers/triggers.py receive_webhook` → `test_webhook_auth_and_payload` | Keep |
| 27 | Connections (encrypted; SMTP, Slack, Teams, API key, basic) | E2E | `crypto.py`, `routers/credentials.py` → e2e2 create Slack, `test_connection_secrets_are_encrypted...` | Keep |
| 28 | Connection test + in-use warning | Partial | `credentials.test_credential` → `test_connection_checks` (unreachable SMTP); real Slack/Teams/SMTP **not verified** | Keep |
| 29 | Email / Slack / Teams / HTTP steps | Partial | `nodes/app_nodes.py` → tests with patched SMTP/HTTP; **no real service verified** | Keep |
| 30 | Failure alerts | Partial | `services/notify.py` → `test_failure_alerts_are_sent` (patched HTTP); real delivery not verified | Keep |
| 31 | History: list, filters, per-workflow, step trace, re-run | E2E | `routers/runs.py`, `pages/Runs.jsx` → e2e3 filtered History, `test_rerun` | Keep |
| 32 | Duplicate, delete, export, import | E2E | `routers/workflows.py duplicate/delete_automation`, `Automations.jsx` → e2e3 | Keep |
| 33 | Admin settings (steps on/off, host allowlist, private network, connection role, AI builder, wait, retention) | E2E | `routers/settings.py`, `services/platform_settings.py` → e2e2, `test_settings_normalise_hosts...` | Keep |
| 34 | SSRF protection for outbound HTTP | Tested | `safe_http.py` → `test_http_request_respects_allowlist_and_private_networks` | Keep |
| 35 | Audit log (filters, request id) | E2E | `audit.py`, `routers/admin.py list_audit` → e2e5 audit shows `user.create` | Keep |
| 36 | Monitoring metrics | E2E | `routers/admin.py metrics` → e2e5 | Keep |
| 37 | Run retention purge | Tested | `runs.purge_old_runs` → `test_history_filter_by_automation_and_retention` | Keep |
| 38 | Star Dust branding, login animation, brand tokens | E2E | `lib/brand.jsx`, `StarDustScene.jsx`, `theme.css` → screenshots | Keep |
| 39 | Vivriti brand colours | **Missing (blocked)** | site blocked by network policy; `theme.css` holds placeholder indigo | - |
| 40 | Health/readiness, JSON logs, request ids | Tested | `main.py /healthz /readyz`, `logging_config.py` | Keep |
| 41 | Docker, compose, Kubernetes, CI | Partial | files present, manifests validate; images **not built here** | Keep |
| 42 | SSO / OIDC / LDAP | Missing | no code | - |
| 43 | OAuth app connectors, app-event triggers, approval step, sub-workflows, RAG | Missing | no code | - |
| 44 | Durable job queue / separate run workers | Missing | runs use an in-process `ThreadPoolExecutor` (`services/runs.py _pool`) | - |
| 45 | Frontend unit tests; browser tests in CI | Missing | no `*.test.*` files; e2e scripts live outside the repo | - |

## Mock and duplication summary

- **Mock**: `backend/dev/mock_llm.py` (dev/demo/CI only) and `FakeLLM` in `tests/conftest.py`.
  Production code calls `llm/client.py` → real endpoint.
- **Duplicated, kept for compatibility**: legacy node types `agent`, `tool`, `transform`
  (`workflow_engine._execute_node`, `workflow_validator.py:17`); old tool names aliased in
  `tools/builtin.py ALIASES`; `/api/tools` is a role-filtered subset of the step catalogue.
