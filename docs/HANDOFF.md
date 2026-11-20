# Work in progress - resume notes

Paused 2026-11-20 because of session usage limits; scheduled to resume automatically.

## State at pause (branch `claude/review-96bswd`, all pushed)

- Backend: 111 tests pass (SQLite; also run on PostgreSQL 16). Migrations up to
  `f8f52cef6e2e_public_form_options_on_triggers`.
- Frontend: lint clean, builds.
- Done this round (QA report + product review, see `docs/PRODUCT.md`):
  - Server-side form checks on every start path; chat fills the first text field.
  - Validator reference checks; duplicate/delete automation; connection usage + test;
    failure alerts; run retention; AI-builder rate limit; host normalisation;
    turned-off automations stay listed; plain users see only published automations.
  - One set of building blocks (agent tools generated from steps; old names alias).
  - Public form links (`#/f/<id>/<token>`), Repeat-for-each step.
  - Builder rewrite: undo/redo, Start protected, Delete/Backspace safe, deletable edges,
    switch rename keeps connections, field rename updates `{{input.x}}`, steps auto-connect
    (before Finish / on free branch / onward to Finish), version picker, discard draft,
    turn off/on, unsaved-changes guard + local restore, deep links `#/automations/<id>`,
    failure alerts panel, Advanced section.
  - "How it starts": form link, plain schedule picker with default inputs, webhook with
    copy URL / curl.
  - List: Turn on, History (filtered), Duplicate, Export, Import, Delete; sorted by update.
  - Session-expired message, cross-tab sign-in, friendly error messages.

## Since the first pause (all pushed)

- e2e regression run (e2e3) fixed and passing; README updated; backend formatted.
- Brand tokens: accent colours now come from `frontend/src/theme.css` (CSS variables).
- Renamed to **Star Dust** in all user-facing text (technical identifiers unchanged).
- New login screen with the stardust agent-constellation animation (`StarDustScene.jsx`).
- Menu and texts say "Workflow(s)" again; `#/automations` links still work.

## Remaining to deliver

1. Second-round QA report (started before the renames; it may mention "Automations"):
   fix confirmed issues, rerun `scratchpad/e2e2.js` and `e2e3.js` (selectors already use
   "Workflows"). If the report never arrived, run a fresh QA agent on the new UI.
2. Vivriti Capital brand colours: the user will allow `www.vivriticapital.com` and
   `vivriticapital.com` in the environment network settings. Only fetch the site once the user
   confirms it is allowed; then put the real palette into `frontend/src/theme.css` (and the
   login gradient in `Login.jsx`). Never guess the colours.
3. Final verification (pytest SQLite + Postgres, alembic check, frontend lint/build,
   kustomize + kubernetes-validate), delete this file, commit, push, final summary.
