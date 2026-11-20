from fastapi import APIRouter, Depends

from ..models import User
from ..rbac import ROLE_LEVEL, require_permission
from ..schemas import ToolOut
from ..tools.registry import list_tools

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("", response_model=list[ToolOut])
def get_tools(user: User = Depends(require_permission("tool:read"))):
    """Tools the caller is allowed to attach to agents or use in workflow tool nodes."""
    level = ROLE_LEVEL[user.role]
    return [
        ToolOut(name=t.name, description=t.description, parameters=t.parameters, min_role=t.min_role)
        for t in list_tools()
        if ROLE_LEVEL.get(t.min_role, 99) <= level
    ]
