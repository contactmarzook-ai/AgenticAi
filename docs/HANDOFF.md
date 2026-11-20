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

## Remaining to deliver

1. Finish the e2e regression run (`scratchpad/e2e3.js`): it passed up to the form-link step
   and stopped at filling the schedule's default input (`label:has-text("Customer note") input`
   in the "How it starts" dialog). Check whether `RunForm` renders the field there (or the
   selector), fix, and rerun the whole script.
2. Fresh-eyes QA pass with an independent agent on the new UI; fix confirmed issues.
3. Update README (form links, loops, unified tools, alerts, retention, import/export) and
   deploy docs if needed.
4. Run backend tests on SQLite + PostgreSQL, `alembic check`, frontend lint/build, manifest
   validation; commit, push; final summary to the user.
