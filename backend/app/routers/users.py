from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import audit
from ..database import get_db
from ..models import Organization, User
from ..rbac import ADMIN_ROLES, PLATFORM_ADMIN, is_platform_admin, require_permission
from ..schemas import OrgIn, OrgOut, OrgUpdate, PasswordReset, UserCreate, UserOut, UserUpdate
from ..security import hash_password, password_problems
from ..services.sessions import revoke_all_sessions

router = APIRouter(prefix="/api/admin/users", tags=["users"])
orgs_router = APIRouter(prefix="/api/admin/orgs", tags=["organizations"])
admin_only = require_permission("user:manage")
platform_only = require_permission("org:manage")


def _check_password(pw: str) -> None:
    problems = password_problems(pw)
    if problems:
        raise HTTPException(status_code=400, detail="Password " + "; ".join(problems))


def _managed_user(db: Session, user_id: int, admin: User) -> User:
    """Org admins manage users of their own organization; platform admins manage everyone."""
    user = db.get(User, user_id)
    if user is None or (not is_platform_admin(admin) and user.org_id != admin.org_id):
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == PLATFORM_ADMIN and not is_platform_admin(admin):
        raise HTTPException(status_code=403, detail="Only a platform admin can change a platform admin")
    return user


def _check_role_grant(admin: User, role: str) -> None:
    # Nobody can hand out more power than they have: only platform admins create platform admins.
    if role == PLATFORM_ADMIN and not is_platform_admin(admin):
        raise HTTPException(status_code=403, detail="Only a platform admin can grant the platform admin role")


def _remaining_admins(db: Session, user: User) -> int:
    """Active admins who could still manage this user's organization (or the platform)."""
    if user.role == PLATFORM_ADMIN:
        return db.query(User).filter(User.role == PLATFORM_ADMIN, User.is_active.is_(True)).count()
    return (
        db.query(User).filter(User.org_id == user.org_id, User.role.in_(ADMIN_ROLES), User.is_active.is_(True)).count()
    )


@router.get("", response_model=list[UserOut])
def list_users(org_id: int | None = None, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    q = db.query(User)
    if not is_platform_admin(admin):
        q = q.filter(User.org_id == admin.org_id)
    elif org_id is not None:
        q = q.filter(User.org_id == org_id)
    return q.order_by(User.email).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    email = body.email.lower()
    _check_role_grant(admin, body.role)
    org_id = admin.org_id
    if body.org_id is not None and body.org_id != admin.org_id:
        if not is_platform_admin(admin):
            raise HTTPException(status_code=403, detail="You can only add users to your own organization")
        org = db.get(Organization, body.org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        org_id = org.id
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    _check_password(body.password)
    user = User(
        email=email,
        full_name=body.full_name,
        role=body.role,
        org_id=org_id,
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
        details={"email": email, "role": body.role, "department": body.department, "org_id": org_id},
        request=request,
        org_id=org_id,
    )
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)
):
    user = _managed_user(db, user_id, admin)
    changes = body.model_dump(exclude_unset=True)
    if "role" in changes and changes["role"] is None:
        raise HTTPException(status_code=400, detail="Role cannot be empty")
    if "role" in changes:
        _check_role_grant(admin, changes["role"])

    was_admin = user.role in ADMIN_ROLES and user.is_active
    stays_admin = changes.get("is_active", True) is not False and (
        changes.get("role", user.role) in ADMIN_ROLES
        and (user.role != PLATFORM_ADMIN or changes.get("role", user.role) == PLATFORM_ADMIN)
    )
    if was_admin and not stays_admin and _remaining_admins(db, user) <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove or deactivate the last active admin")

    before = {k: getattr(user, k) for k in changes}
    for key, value in changes.items():
        setattr(user, key, value)
    if changes.get("is_active") is False or ("role" in changes and changes["role"] != before.get("role")):
        user.token_version += 1  # force re-login so the change takes effect everywhere
        revoke_all_sessions(db, user.id)
    audit(
        db,
        "user.role_change" if "role" in changes and changes["role"] != before.get("role") else "user.update",
        user=admin,
        resource_type="user",
        resource_id=user.id,
        details={"before": before, "after": changes},
        request=request,
        org_id=user.org_id,
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
    user = _managed_user(db, user_id, admin)
    _check_password(body.password)
    user.password_hash = hash_password(body.password)
    user.token_version += 1
    user.failed_login_count = 0
    user.locked_until = None
    revoke_all_sessions(db, user.id)
    audit(
        db,
        "user.reset_password",
        user=admin,
        resource_type="user",
        resource_id=user.id,
        request=request,
        org_id=user.org_id,
    )
    return {"status": "ok"}


# ---------- organizations (platform admins) ----------
def _org_out(db: Session, org: Organization) -> OrgOut:
    out = OrgOut.model_validate(org)
    out.user_count = db.query(func.count(User.id)).filter(User.org_id == org.id).scalar() or 0
    return out


@orgs_router.get("", response_model=list[OrgOut])
def list_orgs(db: Session = Depends(get_db), _: User = Depends(platform_only)):
    return [_org_out(db, o) for o in db.query(Organization).order_by(Organization.name).all()]


@orgs_router.post("", response_model=OrgOut, status_code=201)
def create_org(body: OrgIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(platform_only)):
    if db.query(Organization).filter(Organization.slug == body.slug).first():
        raise HTTPException(status_code=409, detail="An organization with this short name already exists")
    org = Organization(name=body.name, slug=body.slug)
    db.add(org)
    db.flush()
    audit(
        db,
        "org.create",
        user=admin,
        resource_type="organization",
        resource_id=org.id,
        details=body.model_dump(),
        request=request,
        org_id=org.id,
    )
    db.refresh(org)
    return _org_out(db, org)


@orgs_router.patch("/{org_id}", response_model=OrgOut)
def update_org(
    org_id: int, body: OrgUpdate, request: Request, db: Session = Depends(get_db), admin: User = Depends(platform_only)
):
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("is_active") is False and org.id == admin.org_id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own organization")
    for k, v in changes.items():
        setattr(org, k, v)
    audit(
        db,
        "org.update",
        user=admin,
        resource_type="organization",
        resource_id=org.id,
        details=changes,
        request=request,
        org_id=org.id,
    )
    db.refresh(org)
    return _org_out(db, org)
