import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..database import get_db
from ..models import User, Workflow
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
        hosts, bad = set(), []
        for raw in changes["http_allowed_hosts"]:
            host = _normalise_host(raw)
            if host is None:
                bad.append(raw)
            elif host:
                hosts.add(host)
        if bad:
            raise HTTPException(status_code=400, detail=f"Not a valid host name: {', '.join(bad)}")
        changes["http_allowed_hosts"] = sorted(hosts)
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
    newly_disabled = set(after.get("disabled_nodes") or []) - set(before.get("disabled_nodes") or [])
    return {**after, "affected_automations": _using_nodes(db, newly_disabled)}


HOST_RE = re.compile(r"^(\*|(\*\.)?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*)$")


def _normalise_host(raw: str):
    """'https://API.github.com:443/x' -> 'api.github.com'. Returns '' for blanks, None if invalid."""
    text = (raw or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        text = urlparse(text).hostname or ""
    text = text.split("/")[0].split(":")[0].strip(".")
    return text if HOST_RE.match(text) else None


def _using_nodes(db: Session, keys: set) -> list[dict]:
    if not keys:
        return []
    hits = []
    for w in db.query(Workflow).filter(Workflow.status != "archived").all():
        used = {
            (n.get("data") or {}).get("action")
            for n in (w.definition or {}).get("nodes") or []
            if isinstance(n, dict) and n.get("type") == "action"
        } & keys
        if used:
            hits.append({"id": w.id, "name": w.name, "status": w.status, "steps": sorted(used)})
    return hits
