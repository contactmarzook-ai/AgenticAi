from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import update
from sqlalchemy.orm import Session

from .. import oidc, ratelimit
from ..audit import audit, client_ip
from ..config import settings
from ..database import get_db
from ..models import AuditLog, AuthSession, Organization, User
from ..rbac import PLATFORM_ADMIN, get_current_user, permissions_for
from ..schemas import LoginRequest, MeOut, PasswordChange, SessionOut, TokenResponse
from ..security import hash_password, password_problems, verify_password
from ..services.sessions import (
    REFRESH_COOKIE,
    clear_refresh_cookie,
    refresh_session,
    revoke_all_sessions,
    revoke_session,
    start_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Compared against when the email is unknown, so response time does not reveal which emails exist.
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def _org_active(db: Session, user: User) -> bool:
    org = db.get(Organization, user.org_id)
    return org is not None and org.is_active


@router.get("/config")
def auth_config():
    """Public: which sign-in methods the login page should offer."""
    return {"password": settings.local_login_enabled, "microsoft": settings.oidc_enabled}


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ratelimit.check(request, "auth", settings.auth_requests_per_minute)
    email = body.email.lower()
    # Per-address limit on failed sign-ins, so one client cannot lock accounts or guess
    # passwords at bcrypt speed across many emails (security finding L4).
    ip = client_ip(request)
    if ip and settings.login_ip_failures_per_10min > 0:
        recent = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "auth.login",
                AuditLog.status != "success",
                AuditLog.ip_address == ip,
                AuditLog.created_at >= datetime.now(timezone.utc) - timedelta(minutes=10),
            )
            .count()
        )
        if recent >= settings.login_ip_failures_per_10min:
            raise HTTPException(
                status_code=429, detail="Too many failed sign-ins from your network. Try again in a few minutes."
            )

    user = db.query(User).filter(User.email == email).first()
    now = datetime.now(timezone.utc)
    invalid = HTTPException(status_code=401, detail="Invalid email or password")

    if user is None:
        verify_password(body.password, _DUMMY_HASH)
        audit(db, "auth.login", user_email=email, status="failure", details={"reason": "unknown_user"}, request=request)
        raise invalid

    locked = "Account temporarily locked after repeated failed logins. Try again later."
    if user.locked_until and _aware(user.locked_until) > now:
        audit(db, "auth.login", user=user, status="denied", details={"reason": "locked"}, request=request)
        raise HTTPException(status_code=423, detail=locked)
    if user.locked_until:
        # The lock has expired: start counting again (only one concurrent request performs the reset).
        db.execute(
            update(User)
            .where(User.id == user.id, User.locked_until == user.locked_until)
            .values(failed_login_count=0, locked_until=None)
        )
        db.commit()

    # Count this attempt atomically BEFORE checking the password, so parallel guesses
    # (across threads and replicas) cannot slip past the limit. The counter is only reset by
    # a successful login or an expired lock.
    db.execute(update(User).where(User.id == user.id).values(failed_login_count=User.failed_login_count + 1))
    db.commit()
    db.refresh(user)
    attempts = user.failed_login_count

    if attempts > settings.login_max_attempts:
        if not user.locked_until:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
        audit(db, "auth.login", user=user, status="denied", details={"reason": "too_many_attempts"}, request=request)
        raise HTTPException(status_code=423, detail=locked)

    if not verify_password(body.password, user.password_hash):
        details = {"reason": "bad_password", "failed_count": attempts}
        if attempts >= settings.login_max_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            details["locked"] = True
        audit(db, "auth.login", user=user, status="failure", details=details, request=request)
        raise invalid

    if not user.is_active or not _org_active(db, user):
        audit(db, "auth.login", user=user, status="denied", details={"reason": "inactive"}, request=request)
        raise invalid
    if not settings.local_login_enabled and user.role != PLATFORM_ADMIN:
        # Passwords stay available only to platform admins (break-glass) when SSO is enforced.
        audit(db, "auth.login", user=user, status="denied", details={"reason": "password_disabled"}, request=request)
        raise HTTPException(status_code=403, detail="Password sign-in is disabled. Use 'Sign in with Microsoft'.")

    user.failed_login_count = 0
    user.locked_until = None
    result = start_session(db, user, request, response, "password")
    audit(db, "auth.login", user=user, request=request)
    return result


@router.post("/refresh", response_model=TokenResponse, responses={204: {"description": "No session"}})
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    sd_refresh: Optional[str] = Cookie(default=None, alias=REFRESH_COOKIE),
):
    """Renew the access token using the HttpOnly refresh cookie (rotated on every use).

    204 when the browser holds no session cookie at all (the app's start-up check), 401 when
    the cookie is invalid, expired or revoked.
    """
    ratelimit.check(request, "refresh", settings.auth_requests_per_minute)
    if not sd_refresh:
        return Response(status_code=204)
    return refresh_session(db, sd_refresh, request, response)


@router.post("/logout")
def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    revoke_session(db, request.state.session_id)
    audit(db, "auth.logout", user=user, resource_type="session", resource_id=request.state.session_id, request=request)
    clear_refresh_cookie(response)
    return {"status": "ok"}


@router.post("/logout-all")
def logout_all(
    request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Sign out every session of the current user (all devices)."""
    revoke_all_sessions(db, user.id)
    user.token_version += 1
    audit(db, "auth.logout_all", user=user, request=request)
    clear_refresh_cookie(response)
    return {"status": "ok"}


@router.get("/sessions", response_model=list[SessionOut])
def my_sessions(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    rows = (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.last_used_at.desc())
        .all()
    )
    return [
        SessionOut(
            id=s.id,
            method=s.method,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            created_at=s.created_at,
            last_used_at=s.last_used_at,
            expires_at=s.expires_at,
            current=s.id == request.state.session_id,
        )
        for s in rows
        if _aware(s.expires_at) > now
    ]


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = MeOut.model_validate(user, from_attributes=True)
    out.permissions = sorted(permissions_for(user.role))
    org = db.get(Organization, user.org_id)
    out.org_name = org.name if org else None
    return out


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    body: PasswordChange,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.auth_provider != "local" or not user.password_hash:
        raise HTTPException(status_code=400, detail="This account signs in with Microsoft; change the password there.")
    if not verify_password(body.current_password, user.password_hash):
        audit(db, "auth.change_password", user=user, status="failure", request=request)
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    problems = password_problems(body.new_password)
    if problems:
        raise HTTPException(status_code=400, detail="Password " + "; ".join(problems))
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # sign out other sessions
    revoke_all_sessions(db, user.id)
    audit(db, "auth.change_password", user=user, request=request, commit=False)
    return start_session(db, user, request, response, "password")


# ---------- Microsoft Entra ID ----------
def _sso_fail(db: Session, request: Request, code: str, email: str | None = None) -> RedirectResponse:
    audit(db, "auth.oidc_login", user_email=email, status="failure", details={"reason": code}, request=request)
    resp = RedirectResponse(f"/#/login?sso_error={code}", status_code=302)
    resp.delete_cookie(oidc.STATE_COOKIE, path=oidc.STATE_COOKIE_PATH)
    return resp


@router.get("/oidc/login")
def oidc_login(request: Request):
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="Microsoft sign-in is not configured")
    ratelimit.check(request, "oidc", settings.auth_requests_per_minute)
    try:
        url, cookie = oidc.start()
    except oidc.OIDCError as exc:
        return RedirectResponse(f"/#/login?sso_error={exc.code}", status_code=302)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(
        oidc.STATE_COOKIE,
        cookie,
        max_age=600,
        path=oidc.STATE_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",  # must survive the top-level redirect back from Microsoft
    )
    return resp


@router.get("/oidc/callback")
def oidc_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
    sd_oidc: Optional[str] = Cookie(default=None, alias=oidc.STATE_COOKIE),
):
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="Microsoft sign-in is not configured")
    ratelimit.check(request, "oidc", settings.auth_requests_per_minute)
    if error or not code:
        return _sso_fail(db, request, "cancelled" if error == "access_denied" else "idp_error")
    email = None
    try:
        st = oidc.read_state(sd_oidc, state)
        tokens = oidc.exchange_code(code, st["cv"])
        claims = oidc.verify_id_token(str(tokens.get("id_token", "")), st["nn"])
        email = oidc.email_of(claims)
    except oidc.OIDCError as exc:
        return _sso_fail(db, request, exc.code, email)

    subject = f"{claims.get('tid', settings.oidc_tenant_id)}:{claims.get('oid') or claims['sub']}"
    mapped = oidc.mapped_role(claims)
    user = db.query(User).filter(User.oidc_subject == subject).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is not None and user.oidc_subject and user.oidc_subject != subject:
            return _sso_fail(db, request, "account_conflict", email)
    if user is None:
        role = mapped or oidc.default_role()
        org = db.query(Organization).filter(Organization.slug == settings.oidc_org_slug).first()
        if role is None or org is None or not org.is_active:
            return _sso_fail(db, request, "not_provisioned", email)
        user = User(
            email=email,
            full_name=str(claims.get("name") or "")[:255] or None,
            role=role,
            org_id=org.id,
            auth_provider="oidc",
        )
        db.add(user)
        db.flush()
        audit(
            db,
            "user.create",
            user=user,
            resource_type="user",
            resource_id=user.id,
            details={"via": "oidc", "role": role},
            request=request,
            commit=False,
        )
    if not user.is_active or not _org_active(db, user):
        return _sso_fail(db, request, "inactive", email)
    user.oidc_subject = subject
    if mapped and user.role != PLATFORM_ADMIN and user.role != mapped:
        audit(
            db,
            "user.role_sync",
            user=user,
            resource_type="user",
            resource_id=user.id,
            details={"before": user.role, "after": mapped, "via": "oidc"},
            request=request,
            commit=False,
        )
        user.role = mapped
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(oidc.STATE_COOKIE, path=oidc.STATE_COOKIE_PATH)
    # The browser gets only the HttpOnly refresh cookie; the app then calls /auth/refresh.
    start_session(db, user, request, resp, "oidc")
    audit(db, "auth.oidc_login", user=user, request=request)
    return resp
