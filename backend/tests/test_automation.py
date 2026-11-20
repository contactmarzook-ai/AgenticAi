import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.llm.client import LLMResponse
from app.services.workflow_engine import evaluate_condition, run_definition

from .conftest import ADMIN, PASSWORD, create_agent, login, wait_for_run


def step(sid, action, config, label=None, settings=None):
    return {
        "id": sid,
        "type": "action",
        "data": {"label": label or sid, "action": action, "config": config, "settings": settings or {}},
    }


def start(fields=None):
    return {"id": "start", "type": "input", "data": {"label": "Start", "fields": fields or []}}


def finish(output=None):
    return {"id": "finish", "type": "end", "data": {"label": "Finish", "config": {"output": output} if output else {}}}


def link(s, t, handle=None):
    e = {"id": f"{s}-{t}", "source": s, "target": t}
    if handle:
        e["sourceHandle"] = handle
    return e


def chain(*nodes):
    return {"nodes": list(nodes), "edges": [link(a["id"], b["id"]) for a, b in zip(nodes, nodes[1:], strict=False)]}


def save_and_test(client, headers, definition, inp=None, name="Flow"):
    wf = client.post("/api/workflows", headers=headers, json={"name": name, "definition": definition}).json()
    run = client.post(f"/api/workflows/{wf['id']}/test", headers=headers, json={"input": inp or {}})
    return wf, run


# ---------------- catalog & settings ----------------
def test_catalog_lists_steps_and_connection_types(client, make_user):
    builder = make_user("b@example.com", "builder")
    cat = client.get("/api/nodes", headers=builder).json()
    keys = {n["key"] for n in cat["nodes"]}
    assert {
        "ai_prompt",
        "ai_classify",
        "ai_extract",
        "http_request",
        "send_email",
        "slack_message",
        "set_fields",
    } <= keys
    email = next(n for n in cat["nodes"] if n["key"] == "send_email")
    assert any(f["type"] == "credential" and f["credential_type"] == "smtp" for f in email["fields"])
    smtp = next(c for c in cat["credential_types"] if c["key"] == "smtp")
    assert any(f["secret"] for f in smtp["fields"])


def test_admin_can_disable_steps(client, admin, make_user):
    builder = make_user("b@example.com", "builder")
    assert client.put("/api/settings", headers=builder, json={"disabled_nodes": ["http_request"]}).status_code == 403
    assert client.put("/api/settings", headers=admin, json={"disabled_nodes": ["nope"]}).status_code == 400
    r = client.put("/api/settings", headers=admin, json={"disabled_nodes": ["http_request"]})
    assert r.status_code == 200 and r.json()["disabled_nodes"] == ["http_request"]
    catalog = {n["key"]: n for n in client.get("/api/nodes", headers=builder).json()["nodes"]}
    assert catalog["http_request"]["disabled"] is True  # still described, so existing steps stay readable

    d = chain(start(), step("h", "http_request", {"url": "https://example.com"}), finish())
    _, run = save_and_test(client, builder, d)
    assert run.status_code == 400
    assert "disabled by your administrator" in json.dumps(run.json())
    audit = client.get("/api/admin/audit?action=settings.", headers=admin).json()["items"]
    assert audit[0]["details"]["disabled_nodes"]["after"] == ["http_request"]


# ---------------- steps ----------------
def test_ai_steps_with_switch_routing(client, admin, llm):
    def handler(messages, tools, json_mode):
        text = messages[-1]["content"]
        if "Classify" in text:
            return LLMResponse(content='{"category": "Billing", "reason": "mentions invoice"}')
        return LLMResponse(content="reply about " + ("billing" if "billing" in text else "other"))

    llm.handler = handler
    d = {
        "nodes": [
            start([{"key": "msg", "label": "Message", "type": "textarea"}]),
            step("cls", "ai_classify", {"text": "{{input.msg}}", "categories": ["billing", "technical"]}),
            {
                "id": "sw",
                "type": "switch",
                "data": {"label": "Route", "value": "{{cls.category}}", "cases": ["billing", "technical"]},
            },
            step("b", "ai_prompt", {"instruction": "write billing reply"}),
            step("o", "ai_prompt", {"instruction": "write other reply"}),
            finish("{{b.text}}{{o.text}}"),
        ],
        "edges": [
            link("start", "cls"),
            link("cls", "sw"),
            link("sw", "b", "billing"),
            link("sw", "o", "default"),
            link("b", "finish"),
            link("o", "finish"),
        ],
    }
    _, run = save_and_test(client, admin, d, {"msg": "where is my invoice?"})
    run = run.json()
    assert run["status"] == "succeeded", run
    assert run["output"]["result"] == "reply about billing"
    statuses = {s["node_id"]: s["status"] for s in run["steps"]}
    assert statuses["o"] == "skipped"
    assert run["llm_calls"] == 2  # classify + one reply; token usage is recorded for AI steps


def test_extract_set_fields_calculate_and_types(client, admin, llm):
    llm.handler = lambda m, t, j: LLMResponse(content='```json\n{"total": "1500", "vendor": "Acme"}\n```')
    d = chain(
        start(),
        step("ex", "ai_extract", {"text": "invoice", "fields": ["total", "vendor"]}),
        step("tax", "calculate", {"expression": "{{ex.total}} * 0.18"}),
        step(
            "out",
            "set_fields",
            {"fields": {"vendor": "{{ex.vendor}}", "tax": "{{tax.result}}", "note": "Tax {{tax.result}}"}},
        ),
        finish(),
    )
    _, run = save_and_test(client, admin, d)
    out = run.json()["output"]["result"]
    assert out == {"vendor": "Acme", "tax": 270.0, "note": "Tax 270.0"}  # single-variable fields keep their type


def test_retries_and_continue_on_error(client, admin, llm):
    calls = {"n": 0}

    def flaky(messages, tools, json_mode):
        calls["n"] += 1
        if calls["n"] < 3:
            from app.llm.client import LLMError

            raise LLMError("model busy")
        return LLMResponse(content="ok now")

    llm.handler = flaky
    d = chain(
        start(),
        step("a", "ai_prompt", {"instruction": "hi"}, settings={"retries": 2, "retry_delay_seconds": 0}),
        finish(),
    )
    _, run = save_and_test(client, admin, d)
    run = run.json()
    assert run["status"] == "succeeded" and run["steps"][1]["attempts"] == 3

    d = chain(
        start(),
        step("boom", "stop_with_error", {"message": "nope"}, settings={"continue_on_error": True}),
        step("after", "compose_text", {"template": "error was: {{boom.error}}"}),
        finish(),
    )
    _, run = save_and_test(client, admin, d)
    run = run.json()
    assert run["status"] == "succeeded"
    assert run["output"]["result"]["text"] == "error was: nope"
    assert run["steps"][1]["status"] == "error_continued"


def test_http_request_respects_allowlist_and_private_networks(client, admin, monkeypatch):
    d = chain(start(), step("h", "http_request", {"url": "http://127.0.0.1:8000/healthz"}), finish())
    _, run = save_and_test(client, admin, d)
    assert "not on the allowed list" in run.json()["error"]

    client.put("/api/settings", headers=admin, json={"http_allowed_hosts": ["*"]})
    _, run = save_and_test(client, admin, d)
    assert "private address" in run.json()["error"]  # SSRF protection even with "*"

    import httpx

    from app import safe_http

    monkeypatch.setattr(safe_http, "_check_ips", lambda host: None)

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, method, url, headers=None, json=None, content=None, auth=None):
            seen.update(method=method, url=url, headers=headers, json=json)
            resp = httpx.Response(200, json={"order": "A1", "status": "shipped"})
            from contextlib import nullcontext

            return nullcontext(resp)

    seen = {}
    monkeypatch.setattr(safe_http.httpx, "Client", FakeClient)
    d = chain(
        start(),
        step(
            "h",
            "http_request",
            {"method": "POST", "url": "https://api.example.com/orders/{{input.id}}", "body": {"id": "{{input.id}}"}},
        ),
        finish("{{h.json.status}}"),
    )
    _, run = save_and_test(client, admin, d, {"id": "A1"})
    assert run.json()["output"]["result"] == "shipped"
    assert seen["url"] == "https://api.example.com/orders/A1" and seen["json"] == {"id": "A1"}


# ---------------- connections ----------------
def make_smtp(client, headers, name="Mail", visibility="private"):
    r = client.post(
        "/api/credentials",
        headers=headers,
        json={
            "name": name,
            "type": "smtp",
            "visibility": visibility,
            "data": {
                "host": "smtp.test",
                "port": 587,
                "username": "bot",
                "password": "s3cret!",
                "from_address": "bot@test",
            },
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_connection_secrets_are_encrypted_and_never_returned(client, admin):
    cred = make_smtp(client, admin)
    assert "password" not in cred["public_data"] and cred["public_data"]["host"] == "smtp.test"
    from app.database import SessionLocal
    from app.models import Credential

    db = SessionLocal()
    row = db.get(Credential, cred["id"])
    assert "s3cret!" not in row.data_encrypted
    db.close()
    # Updating without a password keeps the saved one.
    r = client.put(
        f"/api/credentials/{cred['id']}",
        headers=admin,
        json={"name": "Mail 2", "type": "smtp", "data": {"host": "smtp2.test", "port": 25, "from_address": "x@test"}},
    )
    assert r.status_code == 200
    db = SessionLocal()
    from app.crypto import decrypt_json

    assert decrypt_json(db.get(Credential, cred["id"]).data_encrypted)["password"] == "s3cret!"
    db.close()


def test_send_email_uses_connection(client, admin, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            sent["tls"] = True

        def login(self, u, p):
            sent["login"] = (u, p)

        def send_message(self, msg):
            sent["msg"] = msg

    from app.nodes import app_nodes

    monkeypatch.setattr(app_nodes.smtplib, "SMTP", FakeSMTP)
    cred = make_smtp(client, admin)
    d = chain(
        start(),
        step(
            "m",
            "send_email",
            {"credential_id": cred["id"], "to": "{{input.to}}", "subject": "Hi", "body": "Hello {{input.to}}"},
        ),
        finish(),
    )
    _, run = save_and_test(client, admin, d, {"to": "a@b.com"})
    assert run.json()["status"] == "succeeded", run.json()
    assert sent["login"] == ("bot", "s3cret!") and sent["tls"]
    assert sent["msg"]["To"] == "a@b.com" and "Hello a@b.com" in sent["msg"].get_content()


def test_connections_are_private_to_owner(client, admin, make_user):
    a = make_user("a@example.com", "builder", department="ops")
    b = make_user("b@example.com", "builder", department="ops")
    cred = make_smtp(client, a)
    assert cred["id"] not in {c["id"] for c in client.get("/api/credentials", headers=b).json()}
    # b cannot use a's private connection in a workflow
    d = chain(
        start(),
        step("m", "send_email", {"credential_id": cred["id"], "to": "x@y.z", "subject": "s", "body": "b"}),
        finish(),
    )
    _, run = save_and_test(client, b, d)
    assert run.status_code == 400 and "does not have access" in json.dumps(run.json())
    # sharing with the department fixes it
    client.put(
        f"/api/credentials/{cred['id']}",
        headers=a,
        json={
            "name": "Mail",
            "type": "smtp",
            "visibility": "department",
            "data": {"host": "h", "port": 25, "from_address": "f@x"},
        },
    )
    assert cred["id"] in {c["id"] for c in client.get("/api/credentials", headers=b).json()}
    # only admins create connections when the admin says so
    client.put("/api/settings", headers=admin, json={"connections_min_role": "admin"})
    assert (
        client.post(
            "/api/credentials", headers=a, json={"name": "x", "type": "slack_webhook", "data": {"url": "https://h"}}
        ).status_code
        == 403
    )


# ---------------- templates & AI builder ----------------
def test_templates_create_valid_drafts(client, make_user, llm):
    builder = make_user("b@example.com", "builder")
    templates = client.get("/api/templates", headers=builder).json()
    assert len(templates) >= 8
    for t in templates:
        wf = client.post(f"/api/templates/{t['key']}/use", headers=builder)
        assert wf.status_code == 201
        errors = client.post(f"/api/workflows/{wf.json()['id']}/validate", headers=builder).json()["errors"]
        if t["needs"]:
            assert errors and all("connection" in e or "fill in" in e for e in errors), (t["key"], errors)
        else:
            assert errors == [], (t["key"], errors)

    llm.handler = lambda m, tl, j: LLMResponse(content='{"category": "technical"}' if j else "Try restarting.")
    wf = client.post("/api/templates/support-ticket-router/use", headers=builder).json()
    run = client.post(
        f"/api/workflows/{wf['id']}/test",
        headers=builder,
        json={"input": {"customer": "Ann", "message": "app crashes"}},
    ).json()
    assert run["status"] == "succeeded" and run["output"]["result"] == {"text": "Try restarting."}


BLUEPRINT = {
    "name": "Ticket triage",
    "description": "Classify and reply",
    "steps": [
        {
            "id": "start",
            "type": "start",
            "fields": [{"key": "ticket", "label": "Ticket", "type": "textarea", "required": True}],
        },
        {
            "id": "c",
            "type": "action",
            "action": "ai_classify",
            "label": "Classify",
            "config": {"text": "{{input.ticket}}", "categories": ["urgent", "normal"]},
        },
        {"id": "is_urgent", "type": "if", "left": "{{c.category}}", "operator": "==", "right": "urgent"},
        {
            "id": "alert",
            "type": "action",
            "action": "slack_message",
            "config": {"credential_id": "", "text": "Urgent: {{input.ticket}}"},
        },
        {"id": "finish", "type": "finish"},
    ],
    "links": [
        {"from": "start", "to": "c"},
        {"from": "c", "to": "is_urgent"},
        {"from": "is_urgent", "to": "alert", "branch": "true"},
        {"from": "is_urgent", "to": "finish", "branch": "false"},
        {"from": "alert", "to": "finish"},
    ],
}


def test_ai_builder_generates_and_repairs(client, make_user, llm):
    builder = make_user("b@example.com", "builder")
    replies = iter(
        ['{"steps": [{"id": "x", "type": "action", "action": "made_up"}], "links": []}', json.dumps(BLUEPRINT)]
    )
    llm.handler = lambda m, t, j: LLMResponse(content=next(replies))
    r = client.post(
        "/api/workflows/generate", headers=builder, json={"prompt": "When a ticket arrives, alert Slack if urgent"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Ticket triage"
    nodes = {n["id"]: n for n in body["definition"]["nodes"]}
    assert nodes["is_urgent"]["type"] == "condition" and nodes["start"]["data"]["fields"][0]["key"] == "ticket"
    assert all("position" in n for n in body["definition"]["nodes"])
    assert any("connection" in w for w in body["warnings"])  # the user still has to pick a Slack connection
    assert "Fix these problems" in llm.calls[1]["messages"][-1]["content"]  # second call was a repair round

    llm.handler = lambda m, t, j: LLMResponse(content="sorry, I can't")
    r = client.post("/api/workflows/generate", headers=builder, json={"prompt": "do something"})
    assert r.status_code == 422

    client.put("/api/settings", headers=login(client, *ADMIN), json={"ai_builder_enabled": False})
    r = client.post("/api/workflows/generate", headers=builder, json={"prompt": "do something else"})
    assert r.status_code == 422 and "turned off" in r.json()["detail"]


def test_rerun(client, admin, llm):
    llm.handler = lambda m, t, j: LLMResponse(content="echo " + m[-1]["content"])
    agent = create_agent(client, admin)
    first = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "again"}).json()
    r = client.post(f"/api/runs/{first['id']}/rerun", headers=admin)
    assert r.status_code == 202
    assert wait_for_run(client, admin, r.json()["id"])["output"]["answer"] == "echo again"


# ---------------- regression tests for the security review ----------------
def test_workflow_cannot_use_agent_its_author_cannot_see(client, make_user, llm):
    llm.handler = lambda m, t, j: LLMResponse(content="SECRET " + m[0]["content"])
    fin = make_user("fin@example.com", "builder", department="finance")
    eng = make_user("eng@example.com", "builder", department="eng")
    secret = create_agent(client, fin, name="Secret", system_prompt="TOP SECRET PROMPT", visibility="private")
    for d in (
        chain(start(), step("a", "run_agent", {"agent_id": secret["id"], "message": "leak"}), finish()),
        chain(
            start(),
            {
                "id": "a",
                "type": "agent",
                "data": {"agent_id": secret["id"], "mappings": {"message": {"source": "static", "value": "x"}}},
            },
            finish(),
        ),
    ):
        wf, run = save_and_test(client, eng, d)
        assert run.status_code == 400, run.text
        # Even if validation were bypassed (e.g. agent made private after activation), the run refuses.
        from app.database import SessionLocal
        from app.models import Run, User, Workflow
        from app.services.runs import create_run, execute_run

        db = SessionLocal()
        row = create_run(
            db,
            target=db.get(Workflow, wf["id"]),
            user=db.query(User).filter_by(email="eng@example.com").one(),
            source="test",
            input_data={},
        )
        execute_run(row.id)
        db.expire_all()
        r = db.get(Run, row.id)
        assert r.status == "failed" and "not available" in r.error and "SECRET" not in json.dumps(r.steps)
        db.close()


def test_trigger_stops_when_owner_loses_access(client, admin, make_user, llm):
    bob = make_user("bob@example.com", "builder", department="sales")
    wf = client.post(
        "/api/workflows",
        headers=bob,
        json={
            "name": "Sales",
            "definition": chain(start(), step("s", "set_fields", {"fields": {"s": "SALES-DATA"}}), finish()),
        },
    ).json()
    client.post(f"/api/workflows/{wf['id']}/activate", headers=bob)
    trig = client.post(
        "/api/triggers", headers=bob, json={"name": "h", "workflow_group_id": wf["group_id"], "type": "webhook"}
    ).json()
    token = {"X-Webhook-Token": trig["webhook_token"]}
    assert client.post(f"/api/hooks/{trig['id']}", headers=token, json={}).status_code == 202
    bob_id = client.get("/api/auth/me", headers=bob).json()["id"]
    client.patch(f"/api/admin/users/{bob_id}", headers=admin, json={"role": "user", "department": "eng"})
    assert client.post(f"/api/hooks/{trig['id']}", headers=token, json={}).status_code == 409


def test_lockout_holds_under_parallel_guessing(client, make_user):
    make_user("victim@example.com")

    def guess(_):
        return client.post(
            "/api/auth/login", json={"email": "victim@example.com", "password": "wrong-guess"}
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(guess, range(12)))
    assert codes.count(401) <= 3, codes  # LOGIN_MAX_ATTEMPTS=3 in tests
    r = client.post("/api/auth/login", json={"email": "victim@example.com", "password": PASSWORD})
    assert r.status_code == 423


@pytest.mark.parametrize(
    "definition",
    [
        {"nodes": ["x"]},
        {"nodes": [{"id": "a", "type": "input", "data": "s"}]},
        {"nodes": [{"id": "a", "type": "input"}], "edges": [{"source": ["l"], "target": "a"}]},
    ],
)
def test_malformed_definitions_are_rejected_cleanly(client, admin, definition):
    wf = client.post("/api/workflows", headers=admin, json={"name": "bad", "definition": definition}).json()
    r = client.post(f"/api/workflows/{wf['id']}/validate", headers=admin)
    assert r.status_code == 200 and not r.json()["is_valid"]
    assert client.post(f"/api/workflows/{wf['id']}/activate", headers=admin).status_code == 400


def test_nul_characters_are_stripped(client, admin, llm):
    sid = client.post("/api/chat/sessions", headers=admin, json={}).json()["id"]
    r = client.post(f"/api/chat/sessions/{sid}/messages", headers=admin, json={"message": "a\u0000b"})
    assert r.status_code == 200
    msgs = client.get(f"/api/chat/sessions/{sid}/messages", headers=admin).json()
    assert msgs[0]["content"] == "ab"


@pytest.mark.parametrize(
    "left,op,right,expected",
    [
        (True, "==", "true", True),
        (False, "==", "false", True),
        ("01234", "==", "1234", False),
        (5, "==", "5.0", True),
        ("Approved", "==", "approved", False),
        ("abc", "not_contains", "z", True),
        ("Hello", "starts_with", "he", True),
    ],
)
def test_condition_semantics(left, op, right, expected):
    cond = {"left": {"source": "static", "value": left}, "operator": op, "right": {"source": "static", "value": right}}
    assert evaluate_condition(cond, {}, {}) is expected


def test_finish_returns_its_own_branch_output():
    d = {
        "nodes": [
            start(),
            {"id": "A", "type": "transform", "data": {"mappings": {"v": {"source": "static", "value": "from-A"}}}},
            {"id": "end1", "type": "end", "data": {}},
            {"id": "T", "type": "transform", "data": {"mappings": {"v": {"source": "static", "value": "from-T"}}}},
            {"id": "end2", "type": "end", "data": {}},
        ],
        "edges": [link("start", "A"), link("A", "end1"), link("start", "T"), link("T", "end2")],
    }
    res = run_definition(d, {}, None, None)
    outs = {s["node_id"]: s.get("output") for s in res["steps"]}
    assert outs["end1"] == {"v": "from-A"} and outs["end2"] == {"v": "from-T"}
