"""Role-based access control and tenant isolation.

Every request is authorised here, on the server; the frontend only hides what the user cannot use.

Roles (one per user):

- ``viewer``         read agents/workflows shared with them and their own run history
- ``operator``       viewer + chat, run agents and workflows
- ``developer``      operator + build agents, workflows, triggers and connections
- ``auditor``        read-only view of everything in their organization, plus audit log and monitoring
- ``org_admin``      developer + manage users of their organization, read everything in it
- ``platform_admin`` org_admin + LLM models, platform settings and organizations

Tenancy: every user belongs to exactly one organization (``org_id``, fixed at creation) and every
agent, workflow, run, trigger and connection carries the ``org_id`` of its creator. Resources of
another organization are invisible to everyone, platform admins included, and are reported as
"not found" so ids cannot be probed. Platform admins manage *users and organizations* across
tenants, never another tenant's agents, workflows, runs or connections.
"""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import AuthSession, Organization, User
from .security import decode_access_token

PLATFORM_ADMIN = "platform_admin"
ORG_ADMIN = "org_admin"
DEVELOPER = "developer"
OPERATOR = "operator"
VIEWER = "viewer"
AUDITOR = "auditor"

ROLES = [VIEWER, OPERATOR, DEVELOPER, AUDITOR, ORG_ADMIN, PLATFORM_ADMIN]
ADMIN_ROLES = {ORG_ADMIN, PLATFORM_ADMIN}

# Used where a setting names "the lowest role allowed" (tools, connections). The auditor is
# read-only, so it ranks with viewers.
ROLE_LEVEL = {VIEWER: 0, AUDITOR: 0, OPERATOR: 1, DEVELOPER: 2, ORG_ADMIN: 3, PLATFORM_ADMIN: 4}

# Names used before multi-tenancy; kept so old data, settings and tool declarations still resolve.
LEGACY_ROLES = {"user": OPERATOR, "builder": DEVELOPER, "admin": PLATFORM_ADMIN}

_READ = {"agent:read", "workflow:read", "run:read_own"}
_RUN = {"chat:use", "agent:run", "workflow:run"}
_BUILD = {"agent:write", "workflow:write", "workflow:activate", "trigger:write", "tool:read", "model:read"}
_OVERSIGHT = {"audit:read", "monitoring:read", "run:read_all"}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    VIEWER: frozenset(_READ),
    OPERATOR: frozenset(_READ | _RUN),
    DEVELOPER: frozenset(_READ | _RUN | _BUILD),
    AUDITOR: frozenset(_READ | _OVERSIGHT | {"tool:read", "model:read"}),
    ORG_ADMIN: frozenset(_READ | _RUN | _BUILD | _OVERSIGHT | {"user:manage"}),
    PLATFORM_ADMIN: frozenset(
        _READ | _RUN | _BUILD | _OVERSIGHT | {"user:manage", "model:manage", "settings:manage", "org:manage"}
    ),
}

VISIBILITIES = ("public", "department", "private")


def normalize_role(role: str | None) -> str:
    role = LEGACY_ROLES.get(role or "", role or "")
    return role if role in ROLE_PERMISSIONS else VIEWER


def role_level(role: str | None) -> int:
    return ROLE_LEVEL.get(normalize_role(role), 0)


def permissions_for(role: str) -> set[str]:
    return set(ROLE_PERMISSIONS.get(role, frozenset()))


def has_permission(user: User, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(user.role, frozenset())


def is_admin(user: User) -> bool:
    """Organization admin or platform admin: full control inside their own organization."""
    return user.role in ADMIN_ROLES


def is_platform_admin(user: User) -> bool:
    return user.role == PLATFORM_ADMIN


def sees_whole_org(user: User) -> bool:
    return user.role in ADMIN_ROLES or user.role == AUDITOR


_bearer = HTTPBearer(auto_error=False)


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
        session_id = str(payload["sid"])
    except Exception:
        raise unauthorized

    # Role, organization and active flag always come from the database, never from the token.
    user = db.get(User, user_id)
    if user is None or not user.is_active or payload.get("tv") != user.token_version:
        raise unauthorized
    session = db.get(AuthSession, session_id)
    if (
        session is None
        or session.user_id != user.id
        or session.revoked_at is not None
        or _aware(session.expires_at) <= datetime.now(timezone.utc)
    ):
        raise unauthorized
    org = db.get(Organization, user.org_id)
    if org is None or not org.is_active:
        raise unauthorized
    request.state.user_id = user.id
    request.state.session_id = session_id
    return user


def require_permission(permission: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")
        return user

    return dependency


def same_org(user: User, resource) -> bool:
    return resource is not None and getattr(resource, "org_id", None) == user.org_id


def can_view(user: User, resource) -> bool:
    """Visibility check for agents, workflows and connections (always within one organization)."""
    if not same_org(user, resource):
        return False
    if sees_whole_org(user) or resource.owner_id == user.id:
        return True
    if resource.visibility == "public":
        return True
    if resource.visibility == "department":
        return bool(resource.department) and resource.department == user.department
    return False


def can_edit(user: User, resource) -> bool:
    """Only the owner or an admin of the same organization may change an agent or workflow.

    Others with access can view, run and duplicate it (a duplicate belongs to them). Editing is
    owner-only because a workflow runs with its owner's agents and connections: letting someone
    else change it would let them use the owner's access (security finding C1).
    """
    if not same_org(user, resource):
        return False
    if is_admin(user):
        return True
    return has_permission(user, "agent:write") and resource.owner_id == user.id


def visible_filter(query, model, user: User):
    """SQL version of `can_view` for list endpoints."""
    from sqlalchemy import and_, or_

    query = query.filter(model.org_id == user.org_id)
    if sees_whole_org(user):
        return query
    conds = [model.owner_id == user.id, model.visibility == "public"]
    if user.department:
        conds.append(and_(model.visibility == "department", model.department == user.department))
    return query.filter(or_(*conds))
