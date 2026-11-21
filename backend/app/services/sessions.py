"""Sign-in sessions: refresh-token rotation, reuse detection and revocation."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, Response
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..audit import audit, client_ip
from ..config import settings
from ..models import AuthSession, Organization, User
from ..schemas import TokenResponse
from ..security import create_access_token, hash_token, new_refresh_token, new_session_id

REFRESH_COOKIE = "sd_refresh"
COOKIE_PATH = "/api/auth"


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_expire_hours * 3600,
        path=COOKIE_PATH,  # only sent to the auth endpoints
        httponly=True,  # not readable by scripts
        secure=settings.cookie_secure,
        samesite="strict",  # never sent on cross-site requests (CSRF)
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE, path=COOKIE_PATH, httponly=True, secure=settings.cookie_secure, samesite="strict"
    )


def start_session(db: Session, user: User, request: Request, response: Response, method: str) -> TokenResponse:
    """Create a session for a user who just proved who they are; returns the access token."""
    refresh = new_refresh_token()
    now = datetime.now(timezone.utc)
    sess = AuthSession(
        id=new_session_id(),
        user_id=user.id,
        refresh_hash=hash_token(refresh),
        token_version=user.token_version,
        method=method,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:255] or None,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(hours=settings.refresh_expire_hours),
    )
    db.add(sess)
    user.last_login_at = now
    db.commit()
    set_refresh_cookie(response, refresh)
    token, expires_in = create_access_token(user.id, user.token_version, sess.id)
    return TokenResponse(access_token=token, expires_in=expires_in)


def refresh_session(db: Session, refresh: Optional[str], request: Request, response: Response) -> TokenResponse:
    """Exchange a refresh token for a new access token and a new (rotated) refresh token."""
    invalid = HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    if not refresh:
        raise invalid
    digest = hash_token(refresh)
    now = datetime.now(timezone.utc)
    sess = db.query(AuthSession).filter(AuthSession.refresh_hash == digest).first()
    if sess is None:
        # A rotated-out token presented again: someone else has it. End that session.
        stolen = db.query(AuthSession).filter(AuthSession.prev_refresh_hash == digest).first()
        if stolen is not None and stolen.revoked_at is None:
            stolen.revoked_at = now
            user = db.get(User, stolen.user_id)
            audit(
                db,
                "auth.refresh_reuse",
                user=user,
                status="denied",
                resource_type="session",
                resource_id=stolen.id,
                request=request,
            )
        clear_refresh_cookie(response)
        raise invalid
    user = db.get(User, sess.user_id)
    org = db.get(Organization, user.org_id) if user else None
    if (
        sess.revoked_at is not None
        or _aware(sess.expires_at) <= now
        or user is None
        or not user.is_active
        or user.token_version != sess.token_version
        or org is None
        or not org.is_active
    ):
        clear_refresh_cookie(response)
        raise invalid
    new = new_refresh_token()
    # Compare-and-swap so two parallel refreshes with the same token cannot both succeed.
    changed = db.execute(
        update(AuthSession)
        .where(AuthSession.id == sess.id, AuthSession.refresh_hash == digest)
        .values(refresh_hash=hash_token(new), prev_refresh_hash=digest, last_used_at=now)
    ).rowcount
    db.commit()
    if changed != 1:
        raise invalid
    set_refresh_cookie(response, new)
    token, expires_in = create_access_token(user.id, user.token_version, sess.id)
    return TokenResponse(access_token=token, expires_in=expires_in)


def revoke_session(db: Session, session_id: str) -> None:
    sess = db.get(AuthSession, session_id)
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at = datetime.now(timezone.utc)


def revoke_all_sessions(db: Session, user_id: int) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
