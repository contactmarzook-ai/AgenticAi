from app.rbac import permissions_for

from .conftest import ADMIN, PASSWORD, login


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200


def test_login_and_me(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    assert me["email"] == ADMIN[0]
    assert me["role"] == "platform_admin"
    assert "user:manage" in me["permissions"]


def test_bad_password_and_unknown_email_look_identical(client):
    a = client.post("/api/auth/login", json={"email": ADMIN[0], "password": "wrong"})
    b = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_lockout_after_repeated_failures(client):
    for _ in range(3):
        client.post("/api/auth/login", json={"email": ADMIN[0], "password": "wrong"})
    r = client.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
    assert r.status_code == 423


def test_requires_token(client):
    assert client.get("/api/agents").status_code == 401
    assert client.get("/api/agents", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_role_hierarchy():
    assert "agent:run" in permissions_for("operator")
    assert "agent:write" not in permissions_for("operator")
    assert {"agent:run", "agent:write"} <= permissions_for("developer")
    assert "user:manage" not in permissions_for("developer")
    assert (
        permissions_for("viewer")
        < permissions_for("operator")
        < permissions_for("developer")
        < permissions_for("org_admin")
        < permissions_for("platform_admin")
    )
    assert permissions_for("nonsense") == set()
    assert permissions_for("admin") == set()  # legacy names grant nothing


def test_user_cannot_use_admin_or_builder_endpoints(client, make_user):
    user = make_user("u@example.com", "operator")
    assert client.get("/api/admin/users", headers=user).status_code == 403
    assert client.get("/api/admin/audit", headers=user).status_code == 403
    assert client.post("/api/agents", headers=user, json={"name": "x"}).status_code == 403
    assert client.get("/api/models/providers", headers=user).status_code == 403


def test_builder_cannot_manage_users_or_models(client, make_user):
    builder = make_user("b@example.com", "developer")
    assert client.get("/api/admin/users", headers=builder).status_code == 403
    assert (
        client.post("/api/models/providers", headers=builder, json={"name": "x", "base_url": "http://x"}).status_code
        == 403
    )
    assert client.get("/api/models", headers=builder).status_code == 200


def test_role_change_invalidates_old_token(client, admin, make_user):
    user = make_user("u2@example.com", "developer")
    uid = client.get("/api/auth/me", headers=user).json()["id"]
    assert client.patch(f"/api/admin/users/{uid}", headers=admin, json={"role": "operator"}).status_code == 200
    assert client.get("/api/auth/me", headers=user).status_code == 401
    fresh = login(client, "u2@example.com", PASSWORD)
    assert client.get("/api/auth/me", headers=fresh).json()["role"] == "operator"


def test_deactivated_user_cannot_login(client, admin, make_user):
    make_user("gone@example.com")
    uid = next(
        u["id"] for u in client.get("/api/admin/users", headers=admin).json() if u["email"] == "gone@example.com"
    )
    client.patch(f"/api/admin/users/{uid}", headers=admin, json={"is_active": False})
    r = client.post("/api/auth/login", json={"email": "gone@example.com", "password": PASSWORD})
    assert r.status_code == 401


def test_cannot_remove_last_admin(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    r = client.patch(f"/api/admin/users/{me['id']}", headers=admin, json={"role": "operator"})
    assert r.status_code == 400


def test_password_policy(client, admin):
    r = client.post("/api/admin/users", headers=admin, json={"email": "weak@example.com", "password": "short"})
    assert r.status_code == 400
    assert "at least" in r.json()["detail"]


def test_change_password_signs_out_other_sessions(client, make_user):
    old = make_user("pw@example.com")
    r = client.post(
        "/api/auth/change-password", headers=old, json={"current_password": PASSWORD, "new_password": "N3w#Password!!"}
    )
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401
    new = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=new).status_code == 200


def test_login_events_are_audited(client, admin):
    client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"})
    items = client.get("/api/admin/audit?action=auth.login", headers=admin).json()["items"]
    statuses = {(i["user_email"], i["status"]) for i in items}
    assert ("nobody@example.com", "failure") in statuses
    assert (ADMIN[0], "success") in statuses


def test_production_settings_refuse_insecure_defaults(monkeypatch):
    import pytest

    from app.config import Settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///x.db")
    with pytest.raises(RuntimeError) as exc:
        Settings().validate()
    assert "JWT_SECRET" in str(exc.value) and "PostgreSQL" in str(exc.value)
