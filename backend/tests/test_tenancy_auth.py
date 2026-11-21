"""Authentication, authorization and tenant-isolation tests (security phase).

Covers: invalid/expired/forged tokens, sessions (refresh rotation, reuse, logout), the six roles,
admin-only endpoints, role escalation, cross-tenant access by id, Microsoft Entra ID sign-in, and
security headers / request limits.
"""

import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import oidc, ratelimit
from app.config import settings
from app.database import SessionLocal
from app.logging_config import redact
from app.models import AuthSession, User
from app.security import ALGORITHM, TOKEN_AUDIENCE, TOKEN_ISSUER

from .conftest import ADMIN, PASSWORD, create_agent, login
from .test_automation import chain, finish, start, step


# ---------- helpers ----------
def _set(monkeypatch, name, value):
    """Settings is a frozen dataclass; patch one attribute for the duration of a test."""
    monkeypatch.setattr(type(settings), name, property(lambda self: value), raising=False)


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _claims(headers):
    return jwt.decode(headers["Authorization"].split()[1], options={"verify_signature": False})


def _forge(claims, secret=None, alg=ALGORITHM):
    return jwt.encode(claims, secret or settings.jwt_secret, algorithm=alg)


def _refresh(client, token):
    client.cookies.clear()
    return client.post("/api/auth/refresh", headers={"Cookie": f"sd_refresh={token}"})


@pytest.fixture()
def tenant_b(client, admin):
    """A second organization with its own admin, developer and operator."""
    org = client.post("/api/admin/orgs", headers=admin, json={"name": "Beta Ltd", "slug": "beta"})
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]
    heads = {}
    for email, role in [("boss@beta.com", "org_admin"), ("dev@beta.com", "developer"), ("op@beta.com", "operator")]:
        r = client.post(
            "/api/admin/users",
            headers=admin,
            json={"email": email, "password": PASSWORD, "role": role, "org_id": org_id, "department": "ops"},
        )
        assert r.status_code == 201, r.text
        heads[role] = login(client, email, PASSWORD)
    heads["org_id"] = org_id
    return heads


# ---------- invalid and expired tokens ----------
def test_invalid_tokens_are_rejected(client, admin):
    good = _claims(admin)
    now = datetime.now(timezone.utc)
    cases = {
        "garbage": "not-a-jwt",
        "wrong secret": _forge(good, secret="x" * 40),
        "alg none": jwt.encode(good, None, algorithm="none"),
        "wrong audience": _forge({**good, "aud": "someone-else"}),
        "wrong issuer": _forge({**good, "iss": "evil"}),
        "no session id": _forge({k: v for k, v in good.items() if k != "sid"}),
        "unknown session": _forge({**good, "sid": "0" * 32}),
        "not an access token": _forge({**good, "typ": "refresh"}),
        "stale token version": _forge({**good, "tv": good["tv"] + 1}),
        "other user id": _forge({**good, "sub": "999"}),
        "not yet valid": _forge({**good, "nbf": int((now + timedelta(hours=1)).timestamp())}),
    }
    for name, token in cases.items():
        r = client.get("/api/auth/me", headers=_bearer(token))
        assert r.status_code == 401, name
        assert r.headers.get("www-authenticate") == "Bearer", name
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Basic YTpi"}).status_code == 401


def test_expired_token_is_rejected(client, admin):
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    claims = {**_claims(admin), "iat": old, "nbf": old, "exp": old + timedelta(minutes=15)}
    assert client.get("/api/auth/me", headers=_bearer(_forge(claims))).status_code == 401
    assert client.get("/api/auth/me", headers=admin).status_code == 200


def test_access_tokens_are_short_lived_and_bound_to_a_session(client):
    r = _login(client, *ADMIN)
    claims = _claims(_bearer(r.json()["access_token"]))
    assert claims["exp"] - claims["iat"] == settings.jwt_expire_minutes * 60 <= 3600
    assert claims["iss"] == TOKEN_ISSUER and claims["aud"] == TOKEN_AUDIENCE and claims["sid"]
    assert "role" not in claims and "org" not in claims  # authority always comes from the database
    cookie = r.headers["set-cookie"]
    assert "sd_refresh=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/api/auth" in cookie


# ---------- sessions ----------
def test_refresh_rotates_and_detects_reuse(client):
    r = _login(client, *ADMIN)
    first = r.cookies["sd_refresh"]
    r2 = _refresh(client, first)
    assert r2.status_code == 200
    second = r2.cookies["sd_refresh"]
    assert second != first
    assert client.get("/api/auth/me", headers=_bearer(r2.json()["access_token"])).status_code == 200
    # The rotated-out token is presented again: treated as stolen, the whole session ends.
    assert _refresh(client, first).status_code == 401
    assert _refresh(client, second).status_code == 401
    assert client.get("/api/auth/me", headers=_bearer(r2.json()["access_token"])).status_code == 401
    audit = client.get("/api/admin/audit?action=auth.refresh_reuse", headers=login(client, *ADMIN)).json()
    assert audit["total"] == 1


def test_refresh_without_or_with_bad_cookie(client):
    client.cookies.clear()
    r = client.post("/api/auth/refresh")
    assert r.status_code == 204 and not r.content
    assert _refresh(client, "rft_forged").status_code == 401


def test_logout_revokes_the_session(client):
    r = _login(client, *ADMIN)
    headers, cookie = _bearer(r.json()["access_token"]), r.cookies["sd_refresh"]
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert _refresh(client, cookie).status_code == 401


def test_logout_all_and_session_list(client):
    a = _bearer(_login(client, *ADMIN).json()["access_token"])
    b = _bearer(_login(client, *ADMIN).json()["access_token"])
    sessions = client.get("/api/auth/sessions", headers=a).json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    assert client.post("/api/auth/logout-all", headers=a).status_code == 200
    assert client.get("/api/auth/me", headers=a).status_code == 401
    assert client.get("/api/auth/me", headers=b).status_code == 401


def test_refresh_fails_after_deactivation_or_role_change(client, admin, make_user):
    make_user("r@example.com", "developer")
    r = _login(client, "r@example.com", PASSWORD)
    cookie = r.cookies["sd_refresh"]
    uid = client.get("/api/auth/me", headers=_bearer(r.json()["access_token"])).json()["id"]
    client.patch(f"/api/admin/users/{uid}", headers=admin, json={"role": "viewer"})
    assert _refresh(client, cookie).status_code == 401


def test_expired_session_cannot_refresh(client):
    r = _login(client, *ADMIN)
    db = SessionLocal()
    db.query(AuthSession).update({AuthSession.expires_at: datetime.now(timezone.utc) - timedelta(minutes=1)})
    db.commit()
    db.close()
    assert _refresh(client, r.cookies["sd_refresh"]).status_code == 401
    assert client.get("/api/auth/me", headers=_bearer(r.json()["access_token"])).status_code == 401


# ---------- roles ----------
def test_viewer_is_read_only(client, admin, make_user):
    agent = create_agent(client, admin, visibility="public")
    viewer = make_user("v@example.com", "viewer")
    assert client.get(f"/api/agents/{agent['id']}", headers=viewer).status_code == 200
    assert client.post(f"/api/agents/{agent['id']}/run", headers=viewer, json={"message": "hi"}).status_code == 403
    assert client.get("/api/chat/sessions", headers=viewer).status_code == 403
    assert client.post("/api/agents", headers=viewer, json={"name": "x"}).status_code == 403
    assert client.get("/api/credentials", headers=viewer).status_code == 403


def test_operator_runs_but_cannot_build(client, admin, make_user, llm):
    agent = create_agent(client, admin, visibility="public")
    op = make_user("o@example.com", "operator")
    assert client.post(f"/api/agents/{agent['id']}/run", headers=op, json={"message": "hi"}).status_code == 200
    assert client.post("/api/agents", headers=op, json={"name": "x"}).status_code == 403
    assert client.post("/api/workflows", headers=op, json={"name": "x", "definition": {}}).status_code == 403
    assert client.get("/api/admin/audit", headers=op).status_code == 403


def test_auditor_reads_everything_in_org_but_changes_nothing(client, admin, make_user, llm):
    private = create_agent(client, admin, name="Secret", visibility="private")
    auditor = make_user("aud@example.com", "auditor", department="audit")
    assert client.get(f"/api/agents/{private['id']}", headers=auditor).status_code == 200
    assert client.get("/api/admin/audit", headers=auditor).status_code == 200
    assert client.get("/api/admin/metrics", headers=auditor).status_code == 200
    assert client.get("/api/runs", headers=auditor).status_code == 200
    assert client.put(f"/api/agents/{private['id']}", headers=auditor, json={"name": "x"}).status_code == 403
    assert client.post(f"/api/agents/{private['id']}/run", headers=auditor, json={"message": "x"}).status_code == 403
    assert (
        client.post(
            "/api/credentials", headers=auditor, json={"name": "x", "type": "http_header", "data": {}}
        ).status_code
        == 403
    )
    assert client.get("/api/admin/users", headers=auditor).status_code == 403
    assert client.get("/api/chat/sessions", headers=auditor).status_code == 403


def test_admin_only_endpoints(client, admin, make_user):
    org_admin = make_user("oa@example.com", "org_admin")
    developer = make_user("d@example.com", "developer")
    platform_only = [
        ("get", "/api/models/providers"),
        ("put", "/api/settings"),
        ("get", "/api/admin/orgs"),
        ("post", "/api/admin/orgs"),
    ]
    for method, url in platform_only:
        kwargs = {"json": {"name": "N", "slug": "n-org"}} if method == "post" else {}
        kwargs = {"json": {"ai_builder_enabled": False}} if method == "put" else kwargs
        assert getattr(client, method)(url, headers=org_admin, **kwargs).status_code == 403, url
        assert getattr(client, method)(url, headers=developer, **kwargs).status_code == 403, url
    assert client.get("/api/admin/orgs", headers=admin).status_code == 200
    assert client.get("/api/admin/users", headers=org_admin).status_code == 200
    assert client.get("/api/admin/users", headers=developer).status_code == 403
    assert client.get("/api/admin/audit", headers=developer).status_code == 403


# ---------- role escalation ----------
def test_client_cannot_choose_its_role_at_sign_in(client, make_user):
    make_user("e@example.com", "operator")
    r = client.post(
        "/api/auth/login",
        json={"email": "e@example.com", "password": PASSWORD, "role": "platform_admin", "org_id": 99},
    )
    me = client.get("/api/auth/me", headers=_bearer(r.json()["access_token"])).json()
    assert me["role"] == "operator" and me["org_id"] == 1
    assert client.get("/api/auth/oidc/login?role=admin", follow_redirects=False).status_code == 404


def test_org_admin_cannot_escalate(client, admin, make_user):
    oa = make_user("oa@example.com", "org_admin")
    me = client.get("/api/auth/me", headers=oa).json()
    platform = client.get("/api/auth/me", headers=admin).json()
    body = {"email": "x@example.com", "password": PASSWORD}
    assert client.post("/api/admin/users", headers=oa, json={**body, "role": "platform_admin"}).status_code == 403
    assert client.patch(f"/api/admin/users/{me['id']}", headers=oa, json={"role": "platform_admin"}).status_code == 403
    assert client.patch(f"/api/admin/users/{platform['id']}", headers=oa, json={"is_active": False}).status_code == 403
    assert (
        client.post(
            f"/api/admin/users/{platform['id']}/reset-password", headers=oa, json={"password": PASSWORD}
        ).status_code
        == 403
    )
    assert client.post("/api/admin/users", headers=oa, json={**body, "role": "developer"}).status_code == 201


def test_developer_cannot_change_own_role(client, make_user):
    dev = make_user("d@example.com", "developer")
    uid = client.get("/api/auth/me", headers=dev).json()["id"]
    assert client.patch(f"/api/admin/users/{uid}", headers=dev, json={"role": "org_admin"}).status_code == 403


def test_unknown_or_legacy_role_is_rejected(client, admin):
    for role in ("admin", "superuser", "builder"):
        r = client.post(
            "/api/admin/users", headers=admin, json={"email": "z@example.com", "password": PASSWORD, "role": role}
        )
        assert r.status_code == 422, role


def test_last_org_admin_is_protected(client, admin, tenant_b):
    boss = tenant_b["org_admin"]
    me = client.get("/api/auth/me", headers=boss).json()
    assert client.patch(f"/api/admin/users/{me['id']}", headers=boss, json={"role": "developer"}).status_code == 400


# ---------- tenant isolation ----------
def _org_a_resources(client, admin, llm):
    agent = create_agent(client, admin, name="A-agent", visibility="public")
    cred = client.post(
        "/api/credentials",
        headers=admin,
        json={
            "name": "A-key",
            "type": "http_header",
            "visibility": "public",
            "data": {"header_name": "X-Key", "header_value": "s3cret-value"},
        },
    ).json()
    wf = client.post(
        "/api/workflows",
        headers=admin,
        json={
            "name": "A-flow",
            "visibility": "public",
            "definition": chain(start(), step("s", "set_fields", {"fields": {"a": "1"}}), finish()),
        },
    ).json()
    assert client.post(f"/api/workflows/{wf['id']}/activate", headers=admin).status_code == 200
    trig = client.post(
        "/api/triggers", headers=admin, json={"name": "t", "workflow_group_id": wf["group_id"], "type": "webhook"}
    ).json()
    run = client.post(f"/api/agents/{agent['id']}/run", headers=admin, json={"message": "hi"}).json()
    chat = client.post("/api/chat/sessions", headers=admin, json={"title": "A chat"}).json()
    return {"agent": agent, "cred": cred, "wf": wf, "trig": trig, "run": run, "chat": chat}


def test_cross_tenant_access_by_id_is_not_found(client, admin, tenant_b, llm):
    a = _org_a_resources(client, admin, llm)
    for role in ("org_admin", "developer", "operator"):
        h = tenant_b[role]
        checks = [
            ("get", f"/api/agents/{a['agent']['id']}", None),
            ("put", f"/api/agents/{a['agent']['id']}", {"name": "pwn", "system_prompt": "x"}),
            ("delete", f"/api/agents/{a['agent']['id']}", None),
            ("post", f"/api/agents/{a['agent']['id']}/run", {"message": "hi"}),
            ("get", f"/api/workflows/{a['wf']['id']}", None),
            ("put", f"/api/workflows/{a['wf']['id']}", {"name": "pwn", "definition": a["wf"]["definition"]}),
            ("post", f"/api/workflows/{a['wf']['id']}/run", {"input": {}}),
            ("post", f"/api/workflows/{a['wf']['id']}/duplicate", None),
            ("post", f"/api/workflows/{a['wf']['id']}/activate", None),
            ("delete", f"/api/workflows/groups/{a['wf']['group_id']}", None),
            ("get", f"/api/runs/{a['run']['id']}", None),
            ("post", f"/api/runs/{a['run']['id']}/rerun", None),
            ("get", f"/api/chat/sessions/{a['chat']['id']}/messages", None),
            ("delete", f"/api/chat/sessions/{a['chat']['id']}", None),
            (
                "put",
                f"/api/triggers/{a['trig']['id']}",
                {"name": "x", "workflow_group_id": a["wf"]["group_id"], "type": "webhook"},
            ),
            ("delete", f"/api/triggers/{a['trig']['id']}", None),
            ("post", f"/api/triggers/{a['trig']['id']}/rotate-token", None),
            ("get", f"/api/credentials/{a['cred']['id']}/usage", None),
            ("put", f"/api/credentials/{a['cred']['id']}", {"name": "x", "type": "http_header", "data": {}}),
            ("delete", f"/api/credentials/{a['cred']['id']}", None),
            ("post", f"/api/credentials/{a['cred']['id']}/test", None),
        ]
        for method, url, body in checks:
            kwargs = {"json": body} if body is not None else {}
            r = getattr(client, method)(url, headers=h, **kwargs)
            # 403 only where the role lacks the permission entirely; never 200/2xx, never data.
            assert r.status_code in (403, 404), (role, method, url, r.status_code)
            if role != "operator" or r.status_code != 403:
                assert r.status_code == 404 or (role == "operator"), (role, method, url, r.status_code)
            assert "A-" not in r.text, (role, url)
    # Nothing changed in organization A.
    assert client.get(f"/api/agents/{a['agent']['id']}", headers=admin).json()["name"] == "A-agent"
    assert client.get(f"/api/workflows/{a['wf']['id']}", headers=admin).status_code == 200


def test_cross_tenant_lists_are_empty(client, admin, tenant_b, llm):
    _org_a_resources(client, admin, llm)
    boss = tenant_b["org_admin"]
    for url in ("/api/agents", "/api/workflows", "/api/credentials", "/api/triggers", "/api/chat/sessions"):
        assert client.get(url, headers=boss).json() == [], url
    assert client.get("/api/runs", headers=boss).json()["total"] == 0
    users = {u["email"] for u in client.get("/api/admin/users", headers=boss).json()}
    assert users == {"boss@beta.com", "dev@beta.com", "op@beta.com"}
    audit = client.get("/api/admin/audit?limit=500", headers=boss).json()["items"]
    # Only events about organization B: its own users' actions, and the platform admin creating them.
    assert audit
    for i in audit:
        assert i["user_email"].endswith("@beta.com") or i["action"] in ("user.create", "org.create"), i
    assert not any(i["action"].startswith(("agent.", "workflow.", "connection.", "trigger.", "run.")) for i in audit)
    metrics = client.get("/api/admin/metrics", headers=boss).json()
    assert metrics["runs_total"] == 0 and metrics["inventory"]["agents_active"] == 0


def test_cross_tenant_references_inside_workflows_are_refused(client, admin, tenant_b, llm):
    a = _org_a_resources(client, admin, llm)
    dev = tenant_b["developer"]
    d = chain(
        start(), step("h", "http_request", {"url": "https://example.com", "credential_id": a["cred"]["id"]}), finish()
    )
    wf = client.post("/api/workflows", headers=dev, json={"name": "B-flow", "definition": d}).json()
    r = client.post(f"/api/workflows/{wf['id']}/activate", headers=dev)
    assert r.status_code == 400 and "no longer exists" in json.dumps(r.json())
    d2 = chain(start(), step("ask", "run_agent", {"agent_id": a["agent"]["id"], "message": "hi"}), finish())
    wf2 = client.post("/api/workflows", headers=dev, json={"name": "B-flow2", "definition": d2}).json()
    assert client.post(f"/api/workflows/{wf2['id']}/activate", headers=dev).status_code == 400
    # A new version or a trigger on organization A's workflow group.
    assert (
        client.post(
            "/api/workflows", headers=dev, json={"name": "x", "group_id": a["wf"]["group_id"], "definition": d}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/triggers",
            headers=dev,
            json={"name": "t", "workflow_group_id": a["wf"]["group_id"], "type": "webhook"},
        ).status_code
        == 404
    )
    # Chat with organization A's agent.
    assert (
        client.post("/api/chat/sessions", headers=tenant_b["operator"], json={"agent_id": a["agent"]["id"]}).status_code
        == 404
    )


def test_org_admin_cannot_manage_other_tenants_users(client, admin, tenant_b):
    boss = tenant_b["org_admin"]
    a_admin = client.get("/api/auth/me", headers=admin).json()
    assert client.patch(f"/api/admin/users/{a_admin['id']}", headers=boss, json={"department": "x"}).status_code in (
        403,
        404,
    )
    assert (
        client.post(
            "/api/admin/users",
            headers=boss,
            json={"email": "n@x.com", "password": PASSWORD, "role": "operator", "org_id": 1},
        ).status_code
        == 403
    )
    created = client.post("/api/admin/users", headers=boss, json={"email": "n@beta.com", "password": PASSWORD}).json()
    assert created["org_id"] == tenant_b["org_id"] and created["role"] == "operator"


def test_platform_admin_does_not_see_other_tenants_resources(client, admin, tenant_b, llm):
    dev = tenant_b["developer"]
    b_agent = create_agent(client, dev, name="B-agent", visibility="public")
    assert client.get(f"/api/agents/{b_agent['id']}", headers=admin).status_code == 404
    assert all(x["name"] != "B-agent" for x in client.get("/api/agents", headers=admin).json())
    # ...but does manage users across organizations and sees the whole audit trail.
    assert any(u["email"] == "dev@beta.com" for u in client.get("/api/admin/users", headers=admin).json())
    assert client.get(f"/api/admin/audit?org_id={tenant_b['org_id']}", headers=admin).json()["total"] > 0


def test_deactivated_organization_locks_out_its_users(client, admin, tenant_b):
    op = tenant_b["operator"]
    assert client.get("/api/auth/me", headers=op).status_code == 200
    assert (
        client.patch(f"/api/admin/orgs/{tenant_b['org_id']}", headers=admin, json={"is_active": False}).status_code
        == 200
    )
    assert client.get("/api/auth/me", headers=op).status_code == 401
    assert client.post("/api/auth/login", json={"email": "op@beta.com", "password": PASSWORD}).status_code == 401
    me = client.get("/api/auth/me", headers=admin).json()
    assert client.patch(f"/api/admin/orgs/{me['org_id']}", headers=admin, json={"is_active": False}).status_code == 400


# ---------- authentication failures ----------
def test_authentication_failures_are_audited_and_limited(client, admin, monkeypatch):
    _set(monkeypatch, "auth_requests_per_minute", 3)
    ratelimit.reset()
    codes = [
        client.post("/api/auth/login", json={"email": f"n{i}@x.com", "password": "x"}).status_code for i in range(5)
    ]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
    items = client.get("/api/admin/audit?action=auth.login&status=failure", headers=admin).json()["items"]
    assert {i["user_email"] for i in items} >= {"n0@x.com", "n1@x.com", "n2@x.com"}


def test_public_endpoints_are_rate_limited_per_address(client, monkeypatch):
    _set(monkeypatch, "public_requests_per_minute", 2)
    ratelimit.reset()
    codes = [client.post("/api/hooks/1", headers={"X-Webhook-Token": "guess"}, json={}).status_code for _ in range(3)]
    assert codes == [404, 404, 429]
    assert client.get("/api/public/forms/1", headers={"X-Form-Token": "guess"}).status_code == 429


def test_password_login_can_be_disabled_for_sso(client, make_user, monkeypatch):
    make_user("p@example.com", "developer")
    _set(monkeypatch, "local_login_enabled", False)
    assert client.post("/api/auth/login", json={"email": "p@example.com", "password": PASSWORD}).status_code == 403
    assert client.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}).status_code == 200
    assert client.get("/api/auth/config").json() == {"password": False, "microsoft": False}


def test_jwt_secret_has_no_hardcoded_fallback(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    a, b = Settings().jwt_secret, Settings().jwt_secret
    assert a != b and len(a) >= 32  # random per process, never a constant
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        Settings().validate()
    monkeypatch.setenv("JWT_SECRET", "y" * 40)
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "600")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError) as exc:
        Settings().validate()
    assert "JWT_EXPIRE_MINUTES" in str(exc.value) and "CORS_ORIGINS" in str(exc.value)


# ---------- Microsoft Entra ID ----------
TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "app-client-id"


@pytest.fixture()
def entra(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for name, value in {
        "oidc_tenant_id": TENANT,
        "oidc_client_id": CLIENT_ID,
        "oidc_client_secret": "secret",
        "oidc_redirect_uri": "https://app.example.com/api/auth/oidc/callback",
        "oidc_role_map": json.dumps(
            {"StarDust.Developer": "developer", "grp-admins": "org_admin", "Root": "platform_admin"}
        ),
        "oidc_default_role": "",
    }.items():
        _set(monkeypatch, name, value)
    doc = {
        "issuer": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "authorization_endpoint": "https://login.microsoftonline.com/authorize",
        "token_endpoint": "https://login.microsoftonline.com/token",
        "jwks_uri": "https://login.microsoftonline.com/keys",
    }
    monkeypatch.setattr(oidc, "discovery", lambda: doc)
    monkeypatch.setattr(oidc, "signing_key", lambda token: key.public_key())
    state = {"claims": {}, "codes": []}

    def exchange(code, verifier):
        state["codes"].append((code, verifier))
        return {"id_token": state["token"]}

    monkeypatch.setattr(oidc, "exchange_code", exchange)

    def sign_in(client, claims_overrides=None, nonce=None, tamper_state=False):
        r = client.get("/api/auth/oidc/login", follow_redirects=False)
        assert r.status_code == 302
        q = parse_qs(urlparse(r.headers["location"]).query)
        assert q["code_challenge_method"] == ["S256"] and q["client_id"] == [CLIENT_ID]
        now = datetime.now(timezone.utc)
        claims = {
            "iss": doc["issuer"],
            "aud": CLIENT_ID,
            "sub": "sub-1",
            "oid": "oid-1",
            "tid": TENANT,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "nonce": nonce or q["nonce"][0],
            "email": "alice@corp.com",
            "name": "Alice",
            "roles": [],
        }
        claims.update(claims_overrides or {})
        state["token"] = jwt.encode(claims, key, algorithm="RS256")
        st = "tampered" if tamper_state else q["state"][0]
        before = len(state["codes"])
        cb = client.get(f"/api/auth/oidc/callback?code=abc&state={st}", follow_redirects=False)
        # PKCE: the verifier sent to the token endpoint matches the challenge sent to Microsoft.
        if len(state["codes"]) > before:
            verifier = state["codes"][-1][1]
            digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            assert digest == q["code_challenge"][0]
        return cb

    return sign_in


def _sso_session(client, cb):
    assert cb.status_code == 302 and cb.headers["location"] == "/", cb.headers.get("location")
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200, r.text
    return _bearer(r.json()["access_token"])


def test_oidc_disabled_by_default(client):
    assert client.get("/api/auth/oidc/login", follow_redirects=False).status_code == 404
    assert client.get("/api/auth/oidc/callback?code=x&state=y", follow_redirects=False).status_code == 404
    assert client.get("/api/auth/config").json()["microsoft"] is False


def test_oidc_signs_in_mapped_user(client, admin, entra):
    h = _sso_session(client, entra(client, {"roles": ["StarDust.Developer"]}))
    me = client.get("/api/auth/me", headers=h).json()
    assert me["email"] == "alice@corp.com" and me["role"] == "developer" and me["auth_provider"] == "oidc"
    assert me["org_id"] == 1
    # Signing in again with a new group mapping updates the role; it never grants platform admin.
    h2 = _sso_session(client, entra(client, {"roles": ["Root"], "groups": ["grp-admins"]}))
    assert client.get("/api/auth/me", headers=h2).json()["role"] == "org_admin"
    actions = {i["action"] for i in client.get("/api/admin/audit?action=", headers=admin).json()["items"]}
    assert {"auth.oidc_login", "user.role_sync"} <= actions


def test_oidc_refuses_unprovisioned_and_tampered_logins(client, admin, entra):
    for overrides, kw, reason in [
        ({}, {}, "not_provisioned"),  # no mapped role and no default role
        ({"roles": ["StarDust.Developer"]}, {"nonce": "replayed"}, "bad_nonce"),
        ({"roles": ["StarDust.Developer"], "aud": "other-app"}, {}, "bad_token"),
        ({"roles": ["StarDust.Developer"], "iss": "https://evil.example.com/v2.0"}, {}, "bad_token"),
        ({"roles": ["StarDust.Developer"], "tid": "other-tenant"}, {}, "wrong_tenant"),
        ({"roles": ["StarDust.Developer"], "exp": datetime.now(timezone.utc) - timedelta(hours=1)}, {}, "bad_token"),
        ({"roles": ["StarDust.Developer"]}, {"tamper_state": True}, "state_mismatch"),
    ]:
        cb = entra(client, overrides, **kw)
        assert cb.status_code == 302 and cb.headers["location"].endswith(f"sso_error={reason}"), (reason, cb.headers)
        assert "sd_refresh=" not in cb.headers.get("set-cookie", ""), reason
    db = SessionLocal()
    assert db.query(User).filter(User.email == "alice@corp.com").count() == 0
    db.close()


def test_oidc_links_existing_account_and_respects_deactivation(client, admin, make_user, entra):
    make_user("alice@corp.com", "auditor")
    h = _sso_session(client, entra(client))  # no mapping: existing role is kept
    me = client.get("/api/auth/me", headers=h).json()
    assert me["role"] == "auditor"
    client.patch(f"/api/admin/users/{me['id']}", headers=admin, json={"is_active": False})
    cb = entra(client)
    assert cb.headers["location"].endswith("sso_error=inactive")


def test_oidc_platform_admin_is_never_demoted_by_mapping(client, entra, monkeypatch):
    cb = entra(client, {"email": ADMIN[0], "roles": ["StarDust.Developer"]})
    h = _sso_session(client, cb)
    assert client.get("/api/auth/me", headers=h).json()["role"] == "platform_admin"


# ---------- headers, limits, logging ----------
def test_security_headers(client, admin):
    r = client.get("/api/agents", headers=admin)
    for header, value in {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
        "cache-control": "no-store",
        "referrer-policy": "no-referrer",
    }.items():
        assert r.headers.get(header) == value, header


def test_cors_only_for_configured_origins(client):
    ok = client.options(
        "/api/auth/login",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-credentials" not in ok.headers
    bad = client.options(
        "/api/auth/login", headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in bad.headers


def test_oversized_request_rejected(client, admin):
    big = "x" * (settings.max_request_bytes + 10)
    r = client.post("/api/agents", headers={**admin, "Content-Type": "application/json"}, content=big)
    assert r.status_code == 413


def test_request_id_is_sanitised(client):
    r = client.get("/healthz", headers={"X-Request-ID": "bad id\nInjected: yes"})
    assert r.headers["x-request-id"] != "bad id\nInjected: yes" and "\n" not in r.headers["x-request-id"]
    assert client.get("/healthz", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"


def test_logs_never_contain_tokens(caplog):
    text = (
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig and whk_abcdefghijklmnop "
        "rft_abcdefghijklmnopq password=hunter2 api_key: s3cr3t"
    )
    clean = redact(text)
    for secret in ("eyJhbGciOiJIUzI1NiJ9", "whk_abcdefghijklmnop", "rft_abcdefghijklmnopq", "hunter2", "s3cr3t"):
        assert secret not in clean, secret
    from app.logging_config import RedactingFilter

    record = logging.makeLogRecord({"msg": "token=%s", "args": ("whk_zzzzzzzzzzzz",)})
    RedactingFilter().filter(record)
    assert "whk_zzzzzzzzzzzz" not in record.getMessage()
