"""Gaps found during QA: server-side form checks, reference checks, lifecycle actions, alerts, retention."""

import json
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.llm.client import LLMResponse
from app.models import Run

from .test_automation import chain, finish, link, make_smtp, save_and_test, start, step


def form_flow():
    fields = [
        {"key": "name", "label": "Name", "type": "text", "required": True},
        {"key": "amount", "label": "Amount", "type": "number"},
        {"key": "vip", "label": "VIP", "type": "boolean"},
        {"key": "email", "label": "Email", "type": "email"},
        {"key": "tier", "label": "Tier", "type": "select", "options": ["gold", "silver"]},
    ]
    return chain(
        start(fields),
        step("s", "set_fields", {"fields": {"n": "{{input.name}}", "a": "{{input.amount}}", "v": "{{input.vip}}"}}),
        finish(),
    )


def test_form_input_is_checked_on_the_server(client, admin):
    wf, run = save_and_test(
        client, admin, form_flow(), {"amount": "abc", "email": "nope", "tier": "bronze", "vip": "maybe"}
    )
    assert run.status_code == 400
    errors = " | ".join(run.json()["detail"]["errors"])
    for expected in (
        "'Name' is required",
        "'Amount' must be a number",
        "'Email' must be an email",
        "'Tier' must be one of",
        "'VIP' must be yes or no",
    ):
        assert expected in errors
    ok = client.post(
        f"/api/workflows/{wf['id']}/test",
        headers=admin,
        json={"input": {"name": "Ann", "amount": "1,500", "vip": "yes"}},
    ).json()
    assert ok["output"]["result"] == {"n": "Ann", "a": 1500, "v": True}  # values are converted to their types


def test_webhook_and_schedule_respect_the_form(client, admin):
    wf = client.post("/api/workflows", headers=admin, json={"name": "F", "definition": form_flow()}).json()
    client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    hook = client.post(
        "/api/triggers", headers=admin, json={"name": "h", "workflow_group_id": wf["group_id"], "type": "webhook"}
    ).json()
    r = client.post(f"/api/hooks/{hook['id']}", headers={"X-Webhook-Token": hook["webhook_token"]}, json={"amount": 3})
    assert r.status_code == 400 and "'Name' is required" in json.dumps(r.json())

    from app.models import Trigger
    from app.services.scheduler import tick

    base = {"name": "s", "workflow_group_id": wf["group_id"], "type": "schedule", "cron": "* * * * *"}
    r = client.post("/api/triggers", headers=admin, json=base)
    assert r.status_code == 400 and "'Name' is required" in json.dumps(r.json())
    sched = client.post("/api/triggers", headers=admin, json={**base, "input": {"name": "nightly"}}).json()
    db = SessionLocal()
    row = db.get(Trigger, sched["id"])
    row.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    row.input = {}  # e.g. the form gained a required field after the schedule was made
    db.commit()
    tick(db)
    failed = db.query(Run).filter(Run.trigger_id == sched["id"]).one()
    assert failed.status == "failed" and "set a default input" in failed.error
    db.close()


def test_chat_fills_the_first_text_field(client, admin, llm):
    llm.handler = lambda m, t, j: LLMResponse(content="x")
    d = chain(
        start([{"key": "ticket", "label": "Ticket", "type": "textarea", "required": True}]),
        step("c", "compose_text", {"template": "Got: {{input.ticket}}"}),
        finish("{{c.text}}"),
    )
    wf = client.post(
        "/api/workflows", headers=admin, json={"name": "Desk", "definition": d, "trigger_keywords": "helpdesk"}
    ).json()
    client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    sid = client.post("/api/chat/sessions", headers=admin, json={}).json()["id"]
    reply = client.post(
        f"/api/chat/sessions/{sid}/messages", headers=admin, json={"message": "helpdesk: printer jammed"}
    ).json()
    assert reply["content"] == "Got: helpdesk: printer jammed"

    d2 = chain(
        start(
            [
                {"key": "a", "label": "A", "type": "text", "required": True},
                {"key": "b", "label": "Order number", "type": "number", "required": True},
            ]
        ),
        finish(),
    )
    wf2 = client.post(
        "/api/workflows", headers=admin, json={"name": "Two", "definition": d2, "trigger_keywords": "twofields"}
    ).json()
    client.post(f"/api/workflows/{wf2['id']}/activate", headers=admin)
    reply = client.post(
        f"/api/chat/sessions/{sid}/messages", headers=admin, json={"message": "twofields please"}
    ).json()
    assert (
        "needs more information" in reply["content"] and "Order number" in reply["content"] and reply["run_id"] is None
    )


def test_references_to_missing_or_later_steps_are_errors(client, admin):
    d = {
        "nodes": [
            start([{"key": "x", "label": "X", "type": "text"}]),
            step("a", "compose_text", {"template": "{{ghost.text}} {{b.text}} {{input.y}}"}, label="A"),
            step("b", "compose_text", {"template": "{{a.text}}"}, label="B"),
            finish(),
        ],
        "edges": [link("start", "a"), link("a", "b"), link("b", "finish")],
    }
    wf = client.post("/api/workflows", headers=admin, json={"name": "R", "definition": d}).json()
    res = client.post(f"/api/workflows/{wf['id']}/validate", headers=admin).json()
    text = " | ".join(res["errors"])
    assert "step that no longer exists ({{ghost.text}})" in text
    assert "uses data from 'B', which does not run before it" in text
    assert res["warnings"] == ["'A' uses form field 'y', which the Start form does not have"]


def test_duplicate_and_delete_automation(client, admin, make_user):
    wf = client.post(
        "/api/workflows", headers=admin, json={"name": "Orig", "definition": form_flow(), "visibility": "public"}
    ).json()
    client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    client.post(
        "/api/triggers", headers=admin, json={"name": "h", "workflow_group_id": wf["group_id"], "type": "webhook"}
    )
    other = make_user("b@example.com", "builder")
    copy = client.post(f"/api/workflows/{wf['id']}/duplicate", headers=other).json()
    assert copy["name"] == "Copy of Orig" and copy["status"] == "draft" and copy["group_id"] != wf["group_id"]
    assert client.delete(f"/api/workflows/groups/{wf['group_id']}", headers=other).status_code == 403
    r = client.delete(f"/api/workflows/groups/{wf['group_id']}", headers=admin).json()
    assert r == {"status": "deleted", "versions": 1, "triggers": 1}
    assert client.get(f"/api/workflows?group_id={wf['group_id']}", headers=admin).json() == []


def test_connection_usage(client, admin):
    cred = make_smtp(client, admin)
    d = chain(
        start(),
        step("m", "send_email", {"credential_id": cred["id"], "to": "a@b.co", "subject": "s", "body": "b"}),
        finish(),
    )
    client.post("/api/workflows", headers=admin, json={"name": "Mailer", "definition": d})
    used = client.get(f"/api/credentials/{cred['id']}/usage", headers=admin).json()
    assert [u["name"] for u in used] == ["Mailer"]


def test_failure_alerts_are_sent(client, admin, monkeypatch):
    from app import safe_http

    posted = []

    class Resp:
        status_code = 200
        text = "ok"

    monkeypatch.setattr(
        safe_http, "request", lambda method, url, settings, **kw: posted.append((url, kw["json_body"])) or Resp()
    )
    slack = client.post(
        "/api/credentials",
        headers=admin,
        json={"name": "Ops", "type": "slack_webhook", "data": {"url": "https://hooks.slack.com/x"}},
    ).json()
    d = chain(start(), step("boom", "stop_with_error", {"message": "disk full"}), finish())
    d["settings"] = {"notify_on_failure": {"credential_id": slack["id"]}}
    wf = client.post("/api/workflows", headers=admin, json={"name": "Nightly", "definition": d}).json()
    client.post(f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {}})
    assert posted == []  # tests never alert
    client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    run = client.post(f"/api/workflows/{wf['id']}/run", headers=admin, json={"input": {}}).json()
    from .conftest import wait_for_run

    wait_for_run(client, admin, run["id"])
    import time

    time.sleep(0.2)
    assert posted and posted[0][0] == "https://hooks.slack.com/x" and "disk full" in posted[0][1]["text"]


def test_history_filter_by_automation_and_retention(client, admin, llm):
    wf_a, _ = save_and_test(client, admin, chain(start(), finish()), name="A")
    save_and_test(client, admin, chain(start(), finish()), name="B")
    runs = client.get(f"/api/runs?group_id={wf_a['group_id']}", headers=admin).json()
    assert runs["total"] == 1 and runs["items"][0]["target_name"] == "A"

    from app.services.runs import purge_old_runs

    db = SessionLocal()
    for r in db.query(Run).all():
        r.created_at = datetime.now(timezone.utc) - timedelta(days=100)
    db.commit()
    assert purge_old_runs(db, 90) == 2
    assert purge_old_runs(db, 0) == 0
    db.close()


def test_generate_is_rate_limited(client, make_user, llm):
    builder = make_user("b@example.com", "builder")
    llm.handler = lambda m, t, j: LLMResponse(content="nope")
    codes = [
        client.post("/api/workflows/generate", headers=builder, json={"prompt": "do a thing"}).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [422] * 10 and codes[10] == 429


def test_turned_off_automation_stays_listed_and_users_see_only_live(client, admin, make_user):
    wf = client.post(
        "/api/workflows",
        headers=admin,
        json={"name": "Off", "definition": chain(start(), finish()), "visibility": "public"},
    ).json()
    client.post(
        "/api/workflows",
        headers=admin,
        json={"name": "Draft only", "definition": chain(start(), finish()), "visibility": "public"},
    )
    client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    client.post(f"/api/workflows/{wf['id']}/deactivate", headers=admin)
    listed = {w["name"]: w["status"] for w in client.get("/api/workflows", headers=admin).json()}
    assert listed == {"Off": "archived", "Draft only": "draft"}
    user = make_user("u@example.com")
    assert (
        client.get("/api/workflows", headers=user).json() == []
    )  # drafts and turned-off ones are not offered to users
    assert (
        client.post(f"/api/workflows/{wf['id']}/activate", headers=admin).json()["status"] == "active"
    )  # turn back on
    assert [w["name"] for w in client.get("/api/workflows", headers=user).json()] == ["Off"]


def test_finish_after_a_no_branch_returns_real_output(client, admin):
    d = {
        "nodes": [
            start([{"key": "n", "label": "N", "type": "number"}]),
            step("calc", "calculate", {"expression": "{{input.n}} * 2"}),
            {
                "id": "big",
                "type": "condition",
                "data": {"label": "Big?", "condition": {"left": "{{calc.result}}", "operator": ">", "right": "100"}},
            },
            step("alert", "compose_text", {"template": "big!"}),
            finish(),
        ],
        "edges": [
            link("start", "calc"),
            link("calc", "big"),
            link("big", "alert", "true"),
            link("big", "finish", "false"),
            link("alert", "finish"),
        ],
    }
    _, run = save_and_test(client, admin, d, {"n": 3})
    assert run.json()["output"]["result"] == {"result": 6}


def test_settings_normalise_hosts_and_report_affected_automations(client, admin):
    r = client.put(
        "/api/settings",
        headers=admin,
        json={"http_allowed_hosts": ["https://API.GitHub.com:443/repos", "*.example.com", ""]},
    )
    assert r.json()["http_allowed_hosts"] == ["*.example.com", "api.github.com"]
    assert client.put("/api/settings", headers=admin, json={"http_allowed_hosts": ["not a host!"]}).status_code == 400
    client.post(
        "/api/workflows",
        headers=admin,
        json={
            "name": "Uses compose",
            "definition": chain(start(), step("c", "compose_text", {"template": "x"}), finish()),
        },
    )
    r = client.put("/api/settings", headers=admin, json={"disabled_nodes": ["compose_text"]}).json()
    assert r["affected_automations"][0]["name"] == "Uses compose"


def test_connection_checks(client, admin):
    r = client.post(
        "/api/credentials", headers=admin, json={"name": "bad", "type": "slack_webhook", "data": {"url": "not a url"}}
    )
    assert r.status_code == 400 and "https://" in r.json()["detail"]
    cred = make_smtp(client, admin)
    res = client.post(f"/api/credentials/{cred['id']}/test", headers=admin).json()
    assert res["ok"] is False and "Could not reach" in res["message"]


def test_repeat_for_each(client, admin, llm):
    llm.handler = lambda m, t, j: LLMResponse(content="hi " + m[-1]["content"].split()[-1])
    d = {
        "nodes": [
            start([{"key": "names", "label": "Names", "type": "textarea"}]),
            step("split", "text_tools", {"text": "{{input.names}}", "operation": "split", "find": ","}),
            {
                "id": "each",
                "type": "loop",
                "data": {
                    "label": "Greet each",
                    "items": "{{split.result}}",
                    "action": "ai_prompt",
                    "config": {"instruction": "Greet #{{index}} {{item}}"},
                },
            },
            finish("{{each.results}}"),
        ],
        "edges": [link("start", "split"), link("split", "each"), link("each", "finish")],
    }
    _, run = save_and_test(client, admin, d, {"names": "Ann, Bo"})
    run = run.json()
    assert run["status"] == "succeeded", run
    assert run["output"]["result"] == [{"text": "hi Ann"}, {"text": "hi Bo"}]
    assert run["llm_calls"] == 2
    bad = {
        **d,
        "nodes": [
            *d["nodes"][:2],
            {"id": "each", "type": "loop", "data": {"label": "L", "items": "", "action": "nope"}},
            d["nodes"][3],
        ],
    }
    wf = client.post("/api/workflows", headers=admin, json={"name": "bad", "definition": bad}).json()
    text = " | ".join(client.post(f"/api/workflows/{wf['id']}/validate", headers=admin).json()["errors"])
    assert "choose the list" in text and "choose what this step does" in text


def test_public_form_link(client, admin, llm):
    d = chain(
        start([{"key": "name", "label": "Name", "type": "text", "required": True}]),
        step("c", "compose_text", {"template": "Welcome {{input.name}}"}),
        finish("{{c.text}}"),
    )
    wf = client.post("/api/workflows", headers=admin, json={"name": "Signup", "definition": d}).json()
    client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    trig = client.post(
        "/api/triggers",
        headers=admin,
        json={
            "name": "Public signup",
            "workflow_group_id": wf["group_id"],
            "type": "form",
            "options": {"title": "Join us", "show_result": True, "success_message": "Done!"},
        },
    ).json()
    token = trig["webhook_token"]
    assert token.startswith("frm_")
    anon = {"X-Form-Token": token}
    assert client.get(f"/api/public/forms/{trig['id']}").status_code == 404
    form = client.get(f"/api/public/forms/{trig['id']}", headers=anon).json()
    assert form["title"] == "Join us" and form["fields"][0]["key"] == "name"
    r = client.post(f"/api/public/forms/{trig['id']}", headers=anon, json={"input": {}})
    assert r.status_code == 400 and "'Name' is required" in json.dumps(r.json())
    r = client.post(f"/api/public/forms/{trig['id']}", headers=anon, json={"input": {"name": "Ann"}}).json()
    assert r == {"status": "done", "message": "Done!", "result": "Welcome Ann"}
    runs = client.get("/api/runs?source=form_link", headers=admin).json()
    assert runs["total"] == 1


def test_switch_path_names_must_be_unique_and_not_default(client, admin):
    d = {
        "nodes": [
            start(),
            {"id": "sw", "type": "switch", "data": {"label": "Route", "value": "x", "cases": ["a", "A", "default"]}},
            finish(),
        ],
        "edges": [link("start", "sw"), link("sw", "finish", "a")],
    }
    wf = client.post("/api/workflows", headers=admin, json={"name": "S", "definition": d}).json()
    text = " | ".join(client.post(f"/api/workflows/{wf['id']}/validate", headers=admin).json()["errors"])
    assert "two paths have the same name" in text and "'default' is reserved" in text


def test_turned_off_workflow_with_leftover_draft_can_be_turned_on(client, admin):
    wf = client.post("/api/workflows", headers=admin, json={"name": "W", "definition": chain(start(), finish())}).json()
    client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    client.post(
        "/api/workflows",
        headers=admin,
        json={"name": "W", "group_id": wf["group_id"], "definition": chain(start(), finish())},
    )
    client.post(f"/api/workflows/{wf['id']}/deactivate", headers=admin)
    listed = sorted((w["version"], w["status"]) for w in client.get("/api/workflows", headers=admin).json())
    assert listed == [(1, "archived"), (2, "draft")]


def test_alert_email_must_be_valid(client, admin):
    cred = make_smtp(client, admin)
    d = chain(start(), finish())
    d["settings"] = {"notify_on_failure": {"credential_id": cred["id"], "email_to": "not-an-email"}}
    wf = client.post("/api/workflows", headers=admin, json={"name": "A", "definition": d}).json()
    errors = client.post(f"/api/workflows/{wf['id']}/validate", headers=admin).json()["errors"]
    assert "Failure alerts: the alert address is not a valid email address" in errors


def test_rotated_form_link_keeps_form_prefix(client, admin):
    wf = client.post("/api/workflows", headers=admin, json={"name": "F", "definition": chain(start(), finish())}).json()
    trig = client.post(
        "/api/triggers", headers=admin, json={"name": "f", "workflow_group_id": wf["group_id"], "type": "form"}
    ).json()
    rotated = client.post(f"/api/triggers/{trig['id']}/rotate-token", headers=admin).json()
    assert rotated["webhook_token"].startswith("frm_")
