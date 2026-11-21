"""Role-based access control.

Roles are hierarchical: each role has every permission of the roles below it.
Resource-level access (who can see / run / edit a specific agent or workflow)
is decided by `can_view` and `can_edit`, using visibility + department + owner.
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_access_token

ROLES = ["user", "builder", "admin"]
ROLE_LEVEL = {role: i for i, role in enumerate(ROLES)}

_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "user": {
        "chat:use",
        "agent:read",
        "agent:run",
        "workflow:read",
        "workflow:run",
        "run:read_own",
    },
    "builder": {
        "agent:write",
        "workflow:write",
        "workflow:activate",
        "trigger:write",
        "tool:read",
        "model:read",
    },
    "admin": {
        "user:manage",
        "model:manage",
        "audit:read",
        "monitoring:read",
        "run:read_all",
        "settings:manage",
    },
}

VISIBILITIES = ("public", "department", "private")


def permissions_for(role: str) -> set[str]:
    level = ROLE_LEVEL.get(role, -1)
    perms: set[str] = set()
    for r in ROLES:
        if ROLE_LEVEL[r] <= level:
            perms |= _ROLE_PERMISSIONS[r]
    return perms


def has_permission(user: User, permission: str) -> bool:
    return permission in permissions_for(user.role)


_bearer = HTTPBearer(auto_error=False)


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
    except Exception:
        raise unauthorized

    # Role, department and active flag always come from the database, never from the token.
    user = db.get(User, user_id)
    if user is None or not user.is_active or payload.get("tv") != user.token_version:
        raise unauthorized
    request.state.user_id = user.id
    return user


def require_permission(permission: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")
        return user

    return dependency


def can_view(user: User, resource) -> bool:
    """Visibility check for agents and workflows."""
    if user.role == "admin" or resource.owner_id == user.id:
        return True
    if resource.visibility == "public":
        return True
    if resource.visibility == "department":
        return bool(resource.department) and resource.department == user.department
    return False


def can_edit(user: User, resource) -> bool:
    """Only the owner or an admin may change an agent or workflow.

    Others with access can view, run and duplicate it (a duplicate belongs to them). Editing is
    owner-only because a workflow runs with its owner's agents and connections: letting someone
    else change it would let them use the owner's access (security finding C1).
    """
    if user.role == "admin":
        return True
    return has_permission(user, "agent:write") and resource.owner_id == user.id
