# Browser tests

End-to-end tests that drive the real app in Chromium (Playwright) against the mock LLM
(`backend/dev/mock_llm.py`), so they need no GPU or network.

```bash
cd frontend && npm ci && npx playwright install chromium
pip install -r ../backend/requirements-dev.txt
bash e2e/run.sh          # all specs; screenshots and logs go to e2e/results/
bash e2e/run.sh 03       # one spec
```

| Spec | Covers |
|---|---|
| 01-ai-builder-and-templates | AI draft → test → publish → run from the form; template; blank build with Insert data; connections; admin settings; history |
| 02-builder-lifecycle-and-triggers | auto-connect, protected Start, field rename, undo, switch paths, form link (signed out), schedule picker, unsaved guard, duplicate, filtered history, turn off/on, delete |
| 03-builder-safety | shortcuts ignored in dialogs, switch path rename/duplicates, sidebar leaves builder, local drafts cleared |
| 04-agents-chat-admin | agent with Calculate, chat routing, model test, user creation, audit log, monitoring, builder navigation |
| 07-workflow-execution | live validation (problem shown, cleared), background test followed on the canvas, node logs, execution history, cancel a slow run, failure details + re-run, versions (read-only published, run a published version) |

Each spec gets a fresh database. CI runs this suite on every push (`.github/workflows/ci.yml`, job `e2e`).
