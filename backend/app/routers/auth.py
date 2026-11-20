from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..database import get_db
from ..models import User
from ..rbac import get_current_user, permissions_for
from ..schemas import LoginRequest, MeOut, PasswordChange, TokenResponse
from ..security import (
    create_access_token,
    hash_password,
    password_problems,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Compared against when the email is unknown, so response time does not reveal which emails exist.
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.query(User).filter(User.email == email).first()
    now = datetime.now(timezone.utc)
    invalid = HTTPException(status_code=401, detail="Invalid email or password")

    if user is None:
        verify_password(body.password, _DUMMY_HASH)
        audit(db, "auth.login", user_email=email, status="failure", details={"reason": "unknown_user"}, request=request)
        raise invalid

    if user.locked_until and _aware(user.locked_until) > now:
        audit(db, "auth.login", user=user, status="denied", details={"reason": "locked"}, request=request)
        raise HTTPException(
            status_code=423, detail="Account temporarily locked after repeated failed logins. Try again later."
        )

    if not verify_password(body.password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        details = {"reason": "bad_password", "failed_count": user.failed_login_count}
        if user.failed_login_count >= settings.login_max_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_count = 0
            details["locked"] = True
        audit(db, "auth.login", user=user, status="failure", details=details, request=request)
        raise invalid

    if not user.is_active:
        audit(db, "auth.login", user=user, status="denied", details={"reason": "inactive"}, request=request)
        raise invalid

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    token, expires_in = create_access_token(user.id, user.token_version)
    audit(db, "auth.login", user=user, request=request)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    out = MeOut.model_validate(user, from_attributes=True)
    out.permissions = sorted(permissions_for(user.role))
    return out


@router.post("/change-password")
def change_password(
    body: PasswordChange, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not verify_password(body.current_password, user.password_hash):
        audit(db, "auth.change_password", user=user, status="failure", request=request)
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    problems = password_problems(body.new_password)
    if problems:
        raise HTTPException(status_code=400, detail="Password " + "; ".join(problems))
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # sign out other sessions
    audit(db, "auth.change_password", user=user, request=request)
    token, expires_in = create_access_token(user.id, user.token_version)
    return TokenResponse(access_token=token, expires_in=expires_in)
