from fastapi import APIRouter, Depends

from ..models import User
from ..rbac import require_permission, role_level
from ..schemas import ToolOut
from ..services.platform_settings import get_settings
from ..tools.registry import list_tools_for

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("", response_model=list[ToolOut])
def get_tools(user: User = Depends(require_permission("tool:read"))):
    """Tools the caller is allowed to attach to agents or use in workflow tool nodes."""
    level = role_level(user.role)
    return [
        ToolOut(name=t.name, description=t.description, parameters=t.parameters, min_role=t.min_role)
        for t in list_tools_for(get_settings())
        if role_level(t.min_role) <= level
    ]
