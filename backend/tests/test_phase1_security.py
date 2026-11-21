"""Regression tests for the Phase 1 security findings (docs/audit/SECURITY_FINDINGS.md)."""

import dataclasses
import time

import pytest

from app.database import SessionLocal
from app.models import Run, User

from .conftest import ADMIN, create_agent, login
from .test_automation import chain, finish, start, step


def make_key(client, headers, name="Key", visibility="private", value="SECRET-123"):
    r = client.post(
        "/api/credentials",
        headers=headers,
        json={
            "name": name,
            "type": "http_header",
            "visibility": visibility,
            "data": {"header_name": "X-Api-Key", "header_value": value},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------- C1 / L7: only the owner or an admin edits ----------
def test_department_builder_cannot_edit_or_version_someone_elses_workflow(client, make_user):
    alice = make_user("alice@example.com", "builder", department="eng")
    bob = make_user("bob@example.com", "builder", department="eng")
    secret = make_key(client, alice)
    wf = client.post(
        "/api/workflows",
        headers=alice,
        json={"name": "Shared", "visibility": "department", "definition": chain(start(), finish())},
    ).json()
    assert wf["can_edit"] is True
    bob_view = client.get(f"/api/workflows/{wf['id']}", headers=bob).json()
    assert bob_view["can_edit"] is False
    evil = chain(
        start(), step("h", "http_request", {"url": "https://example.com", "credential_id": secret["id"]}), finish()
    )
    assert (
        client.put(f"/api/workflows/{wf['id']}", headers=bob, json={"name": "x", "definition": evil}).status_code == 403
    )
    assert (
        client.post(
            "/api/workflows", headers=bob, json={"name": "x", "group_id": wf["group_id"], "definition": evil}
        ).status_code
        == 403
    )
    assert client.post(f"/api/workflows/{wf['id']}/test", headers=bob, json={"input": {}}).status_code == 403
    # Bob may duplicate; the copy is his, so Alice's private key is not usable from it.
    copy = client.post(f"/api/workflows/{wf['id']}/duplicate", headers=bob).json()
    client.put(f"/api/workflows/{copy['id']}", headers=bob, json={"name": "copy", "definition": evil})
    r = client.post(f"/api/workflows/{copy['id']}/test", headers=bob, json={"input": {}})
    assert r.status_code == 400 and "does not have access" in r.text


def test_admin_made_version_keeps_the_original_owner(client, admin, make_user):
    bob = make_user("bob@example.com", "builder", department="eng")
    wf = client.post("/api/workflows", headers=bob, json={"name": "B", "definition": chain(start(), finish())}).json()
    v2 = client.post(
        "/api/workflows",
        headers=admin,
        json={"name": "B", "group_id": wf["group_id"], "definition": chain(start(), finish())},
    ).json()
    assert v2["owner_id"] == wf["owner_id"]


def test_department_builder_cannot_edit_someone_elses_agent(client, make_user):
    alice = make_user("alice@example.com", "builder", department="eng")
    bob = make_user("bob@example.com", "builder", department="eng")
    agent = create_agent(client, alice, visibility="department")
    assert (
        client.put(
            f"/api/agents/{agent['id']}", headers=bob, json={"name": "hijack", "visibility": "public"}
        ).status_code
        == 403
    )


# ---------- H1: formulas cannot freeze the server ----------
def test_huge_formulas_are_refused_quickly(client, admin):
    d = chain(
        start([{"key": "x", "label": "X", "type": "text"}]),
        step("c", "calculate", {"expression": "{{input.x}}"}),
        finish(),
    )
    wf = client.post("/api/workflows", headers=admin, json={"name": "Calc", "definition": d}).json()
    t = time.monotonic()
    run = client.post(
        f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {"x": "(((9**99)**99)**99)**99"}}
    ).json()
    assert time.monotonic() - t < 2
    assert run["status"] == "failed" and "too large" in run["error"]
    run = client.post(f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {"x": "1e308*10"}}).json()
    assert run["status"] == "failed"


# ---------- M1: loops respect the workflow deadline ----------
def test_repeat_loop_stops_at_the_deadline():
    from app.services.workflow_engine import WorkflowError, run_definition

    d = {
        "nodes": [
            start(),
            {"id": "l", "type": "loop", "data": {"items": "a\nb\nc\nd\ne", "action": "x", "config": {}}},
            finish(),
        ],
        "edges": [{"source": "start", "target": "l"}, {"source": "l", "target": "finish"}],
    }
    t = time.monotonic()
    with pytest.raises(WorkflowError) as exc:
        run_definition(d, {}, None, None, lambda key, cfg, node: time.sleep(0.4) or {"ok": 1}, timeout_seconds=1)
    assert "time limit" in str(exc.value) and time.monotonic() - t < 2


# ---------- M2: callers cannot override values fixed on the trigger ----------
def test_form_link_and_webhook_cannot_override_fixed_values(client, admin):
    d = chain(
        start([{"key": "name", "label": "Name", "type": "text"}]),
        step("c", "compose_text", {"template": "{{input.name}} -> {{input.approver}}"}),
        finish("{{c.text}}"),
    )
    wf = client.post("/api/workflows", headers=admin, json={"name": "Fixed", "definition": d}).json()
    client.post(f"/api/workflows/{wf['id']}/activate", headers=admin)
    form = client.post(
        "/api/triggers",
        headers=admin,
        json={
            "name": "f",
            "workflow_group_id": wf["group_id"],
            "type": "form",
            "input": {"approver": "boss@corp"},
            "options": {"show_result": True},
        },
    ).json()
    r = client.post(
        f"/api/public/forms/{form['id']}",
        headers={"X-Form-Token": form["webhook_token"]},
        json={"input": {"name": "Ann", "approver": "attacker@evil"}},
    ).json()
    assert r["result"] == "Ann -> boss@corp"
    hook = client.post(
        "/api/triggers",
        headers=admin,
        json={"name": "h", "workflow_group_id": wf["group_id"], "type": "webhook", "input": {"approver": "boss@corp"}},
    ).json()
    run = client.post(
        f"/api/hooks/{hook['id']}",
        headers={"X-Webhook-Token": hook["webhook_token"]},
        json={"name": "Bo", "approver": "attacker@evil"},
    ).json()
    from .conftest import wait_for_run

    assert wait_for_run(client, admin, run["id"])["output"]["result"] == "Bo -> boss@corp"


# ---------- M3 / L1 / L2: outbound protections ----------
def test_smtp_connections_cannot_reach_private_hosts_or_odd_ports(client, admin):
    cred = client.post(
        "/api/credentials",
        headers=admin,
        json={"name": "local", "type": "smtp", "data": {"host": "127.0.0.1", "port": 587, "from_address": "a@b.co"}},
    ).json()
    res = client.post(f"/api/credentials/{cred['id']}/test", headers=admin).json()
    assert res["ok"] is False and "non-public" in res["message"]
    odd = client.post(
        "/api/credentials",
        headers=admin,
        json={
            "name": "odd",
            "type": "smtp",
            "data": {"host": "mail.example.com", "port": 8398, "from_address": "a@b.co"},
        },
    ).json()
    res = client.post(f"/api/credentials/{odd['id']}/test", headers=admin).json()
    assert res["ok"] is False and "not an email port" in res["message"]


def test_slack_connections_are_limited_to_slack(client, admin):
    r = client.post(
        "/api/credentials",
        headers=admin,
        json={"name": "s", "type": "slack_webhook", "data": {"url": "https://evil.example.com/x"}},
    )
    assert r.status_code == 400 and "not a Slack webhook address" in r.json()["detail"]
    r = client.post(
        "/api/credentials",
        headers=admin,
        json={"name": "s", "type": "slack_webhook", "data": {"url": "https://hooks.slack.com/services/T/B/X"}},
    )
    assert r.status_code == 201


def test_shared_address_space_is_not_public(monkeypatch):
    from app import safe_http

    monkeypatch.setattr(
        safe_http.socket, "getaddrinfo", lambda host, port: [(None, None, None, None, ("100.64.1.1", 0))]
    )
    with pytest.raises(safe_http.BlockedRequest):
        safe_http.check_url("https://cgnat.example.com/", {"http_allowed_hosts": ["*"]})


# ---------- M4: provider keys only from LLM_KEY_* ----------
def test_provider_key_variable_must_use_the_llm_prefix(client, admin, monkeypatch):
    r = client.post(
        "/api/models/providers",
        headers=admin,
        json={"name": "x", "base_url": "https://x.example.com", "api_key_env": "JWT_SECRET"},
    )
    assert r.status_code == 422
    from app.llm.client import resolve_api_key

    monkeypatch.setenv("JWT_SECRET", "s")
    monkeypatch.setenv("LLM_KEY_OK", "k")
    assert resolve_api_key("JWT_SECRET") is None and resolve_api_key("LLM_KEY_OK") == "k"


# ---------- M5 ----------
def test_cryptography_is_a_declared_dependency():
    from pathlib import Path

    reqs = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text()
    assert "cryptography==" in reqs


# ---------- M6: per-user concurrency cap ----------
def test_concurrent_runs_are_capped(client, admin):
    agent = create_agent(client, admin)
    db = SessionLocal()
    me = db.query(User).filter_by(email=ADMIN[0]).one()
    for _ in range(5):
        db.add(
            Run(target_type="agent", target_id=agent["id"], target_name="x", status="running", input={}, user_id=me.id)
        )
    db.commit()
    db.close()
    r = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "hi"})
    assert r.status_code == 429 and "in progress" in r.json()["detail"]


# ---------- L3: audit uses the proxy-appended address ----------
def test_audit_ip_ignores_client_supplied_forwarded_entries(client):
    client.post(
        "/api/auth/login",
        headers={"X-Forwarded-For": "6.6.6.6, 10.1.2.3"},
        json={"email": "nobody@example.com", "password": "x"},
    )
    token = login(client, *ADMIN)
    items = client.get("/api/admin/audit?action=auth.login&status=failure", headers=token).json()["items"]
    assert items[0]["ip_address"] == "10.1.2.3"


# ---------- L4: per-address failed sign-in limit ----------
def test_failed_logins_are_limited_per_address(client, monkeypatch):
    from app.routers import auth

    monkeypatch.setattr(auth, "settings", dataclasses.replace(auth.settings, login_ip_failures_per_10min=3))
    codes = [
        client.post(
            "/api/auth/login",
            headers={"X-Forwarded-For": "7.7.7.7"},
            json={"email": f"u{i}@example.com", "password": "x"},
        ).status_code
        for i in range(5)
    ]
    assert codes == [401, 401, 401, 429, 429]


# ---------- L6 ----------
def test_connection_usage_hides_names_and_tests_need_ownership(client, admin, make_user):
    cred = make_key(client, admin, visibility="public")
    d = chain(start(), step("h", "http_request", {"url": "https://example.com", "credential_id": cred["id"]}), finish())
    client.post(
        "/api/workflows", headers=admin, json={"name": "Admin secret flow", "visibility": "private", "definition": d}
    )
    user = make_user("u@example.com", "user")
    used = client.get(f"/api/credentials/{cred['id']}/usage", headers=user).json()
    assert used and used[0]["name"] is None and used[0]["visible"] is False
    assert client.post(f"/api/credentials/{cred['id']}/test", headers=user).status_code == 403


# ---------- L9 ----------
def test_production_refuses_placeholder_database_password(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://agentos:change-me@db/agentos")
    with pytest.raises(RuntimeError) as exc:
        Settings().validate()
    assert "change-me" in str(exc.value)


# ---------- Info: secrets are masked in recorded step inputs ----------
def test_secret_looking_fields_are_masked_in_history(client, admin, monkeypatch):
    from app import safe_http

    class Resp:
        status_code = 200
        text = "{}"
        headers = {}

        def json(self):
            return {}

    seen = {}
    monkeypatch.setattr(safe_http, "request", lambda method, url, settings, **kw: seen.update(kw) or Resp())
    client.put("/api/settings", headers=admin, json={"http_allowed_hosts": ["*"]})
    d = chain(
        start(),
        step("h", "http_request", {"url": "https://api.example.com", "headers": {"Authorization": "Bearer TOPSECRET"}}),
        finish(),
    )
    wf = client.post("/api/workflows", headers=admin, json={"name": "M", "definition": d}).json()
    run = client.post(f"/api/workflows/{wf['id']}/test", headers=admin, json={"input": {}}).json()
    assert seen["headers"]["Authorization"] == "Bearer TOPSECRET"  # the real call still gets the value
    assert "TOPSECRET" not in str(run["steps"])
