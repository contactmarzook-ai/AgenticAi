from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..database import get_db
from ..models import User
from ..nodes import NODE_TYPES
from ..rbac import get_current_user, require_permission
from ..schemas import SettingsIn
from ..services.platform_settings import get_settings, save_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Readable by everyone signed in, so the UI can hide features that are switched off."""
    return get_settings(db, fresh=True)


@router.put("")
def update_settings(
    body: SettingsIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("settings:manage")),
):
    changes = body.model_dump(exclude_none=True)
    unknown = set(changes.get("disabled_nodes", [])) - set(NODE_TYPES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown step types: {', '.join(sorted(unknown))}")
    if "http_allowed_hosts" in changes:
        changes["http_allowed_hosts"] = sorted({h.strip().lower() for h in changes["http_allowed_hosts"] if h.strip()})
    before = get_settings(db, fresh=True)
    after = save_settings(db, changes)
    audit(
        db,
        "settings.update",
        user=admin,
        resource_type="settings",
        resource_id="platform",
        details={k: {"before": before.get(k), "after": after.get(k)} for k in changes if before.get(k) != after.get(k)},
        request=request,
    )
    return after
