from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..database import get_db
from ..models import User
from ..rbac import require_permission
from ..schemas import PasswordReset, UserCreate, UserOut, UserUpdate
from ..security import hash_password, password_problems

router = APIRouter(prefix="/api/admin/users", tags=["users"])
admin_only = require_permission("user:manage")


def _check_password(pw: str) -> None:
    problems = password_problems(pw)
    if problems:
        raise HTTPException(status_code=400, detail="Password " + "; ".join(problems))


def _active_admins(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return db.query(User).order_by(User.email).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    _check_password(body.password)
    user = User(
        email=email,
        full_name=body.full_name,
        role=body.role,
        department=(body.department or None),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    audit(
        db,
        "user.create",
        user=admin,
        resource_type="user",
        resource_id=user.id,
        details={"email": email, "role": body.role, "department": body.department},
        request=request,
    )
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    changes = body.model_dump(exclude_unset=True)

    losing_admin = (
        user.role == "admin"
        and user.is_active
        and (changes.get("role", "admin") != "admin" or changes.get("is_active") is False)
    )
    if losing_admin and _active_admins(db) <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove or deactivate the last active admin")

    before = {k: getattr(user, k) for k in changes}
    for key, value in changes.items():
        setattr(user, key, value)
    if changes.get("is_active") is False or ("role" in changes and changes["role"] != before.get("role")):
        user.token_version += 1  # force re-login so the change takes effect everywhere
    audit(
        db,
        "user.update",
        user=admin,
        resource_type="user",
        resource_id=user.id,
        details={"before": before, "after": changes},
        request=request,
    )
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    body: PasswordReset,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    _check_password(body.password)
    user.password_hash = hash_password(body.password)
    user.token_version += 1
    user.failed_login_count = 0
    user.locked_until = None
    audit(db, "user.reset_password", user=admin, resource_type="user", resource_id=user.id, request=request)
    return {"status": "ok"}
