from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..nodes import CREDENTIAL_TYPES, NODE_TYPES
from ..rbac import require_permission
from ..services.platform_settings import get_settings

router = APIRouter(prefix="/api/nodes", tags=["nodes"])

CATEGORY_ORDER = ["AI", "Apps", "Data", "Flow"]


@router.get("")
def catalog(db: Session = Depends(get_db), user: User = Depends(require_permission("workflow:read"))):
    """Everything the workflow builder offers: step types (with their form fields) and connection types."""
    disabled = set(get_settings(db).get("disabled_nodes") or [])
    nodes = []
    for nt in sorted(NODE_TYPES.values(), key=lambda n: (CATEGORY_ORDER.index(n.category), n.name)):
        nodes.append({**nt.to_dict(), "disabled": nt.key in disabled})
    return {"nodes": nodes, "credential_types": [c.to_dict() for c in CREDENTIAL_TYPES.values()]}
