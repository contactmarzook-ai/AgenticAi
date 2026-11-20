import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..database import get_db
from ..models import Trigger, User, Workflow, utcnow
from ..rbac import can_edit, can_view, require_permission
from ..schemas import RunOut, TriggerCreated, TriggerIn, TriggerOut
from ..security import hash_token, new_webhook_token
from ..services.runs import submit_run
from ..services.scheduler import next_fire_time, start_trigger_run, valid_cron

router = APIRouter(prefix="/api/triggers", tags=["triggers"])
hooks = APIRouter(prefix="/api/hooks", tags=["webhooks"])

MAX_WEBHOOK_BODY_BYTES = 256 * 1024


def _latest(db: Session, group_id: str) -> Workflow | None:
    return db.query(Workflow).filter(Workflow.group_id == group_id).order_by(Workflow.version.desc()).first()


def _check_workflow(db: Session, user: User, group_id: str) -> Workflow:
    wf = _latest(db, group_id)
    if wf is None or not can_view(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not can_edit(user, wf):
        raise HTTPException(status_code=403, detail="You cannot add triggers to this workflow")
    return wf


def _validate(body: TriggerIn) -> None:
    if body.type == "schedule":
        if not body.cron or not valid_cron(body.cron):
            raise HTTPException(
                status_code=400, detail="A valid 5-field cron expression is required, e.g. '0 9 * * 1-5'"
            )
        try:
            next_fire_time(body.cron, body.timezone)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Unknown timezone '{body.timezone}'")


def _visible_trigger(db: Session, trigger_id: int, user: User) -> Trigger:
    trig = db.get(Trigger, trigger_id)
    if trig is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    wf = _latest(db, trig.workflow_group_id)
    owns = trig.owner_id == user.id and wf is not None and can_view(user, wf)
    if user.role != "admin" and not owns and not (wf and can_edit(user, wf)):
        raise HTTPException(status_code=404, detail="Trigger not found")
    return trig


@router.get("", response_model=list[TriggerOut])
def list_triggers(
    workflow_group_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("trigger:write")),
):
    q = db.query(Trigger)
    if workflow_group_id:
        q = q.filter(Trigger.workflow_group_id == workflow_group_id)
    out = []
    for trig in q.order_by(Trigger.id).all():
        wf = _latest(db, trig.workflow_group_id)
        if user.role == "admin" or (wf and (can_edit(user, wf) or (trig.owner_id == user.id and can_view(user, wf)))):
            out.append(trig)
    return out


@router.post("", response_model=TriggerCreated, status_code=201)
def create_trigger(
    body: TriggerIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("trigger:write")),
):
    _check_workflow(db, user, body.workflow_group_id)
    _validate(body)
    trig = Trigger(**body.model_dump(), owner_id=user.id)
    token = None
    if body.type == "schedule":
        trig.next_run_at = next_fire_time(body.cron, body.timezone) if body.is_enabled else None
        trig.cron = body.cron
    else:
        trig.cron = None
        token = new_webhook_token()
        trig.webhook_token_hash = hash_token(token)
    db.add(trig)
    db.flush()
    audit(
        db,
        "trigger.create",
        user=user,
        resource_type="trigger",
        resource_id=trig.id,
        details={"type": trig.type, "cron": trig.cron, "workflow_group_id": trig.workflow_group_id},
        request=request,
    )
    db.refresh(trig)
    out = TriggerCreated.model_validate(trig)
    out.webhook_token = token
    return out


@router.put("/{trigger_id}", response_model=TriggerOut)
def update_trigger(
    trigger_id: int,
    body: TriggerIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("trigger:write")),
):
    trig = _visible_trigger(db, trigger_id, user)
    if body.type != trig.type or body.workflow_group_id != trig.workflow_group_id:
        raise HTTPException(status_code=400, detail="Trigger type and workflow cannot be changed; create a new trigger")
    _validate(body)
    for k in ("name", "cron", "timezone", "input", "is_enabled"):
        setattr(trig, k, getattr(body, k))
    if trig.type == "schedule":
        trig.next_run_at = next_fire_time(trig.cron, trig.timezone) if trig.is_enabled else None
    audit(
        db,
        "trigger.update",
        user=user,
        resource_type="trigger",
        resource_id=trig.id,
        details={"cron": trig.cron, "enabled": trig.is_enabled},
        request=request,
    )
    db.refresh(trig)
    return trig


@router.post("/{trigger_id}/rotate-token", response_model=TriggerCreated)
def rotate_token(
    trigger_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("trigger:write")),
):
    trig = _visible_trigger(db, trigger_id, user)
    if trig.type != "webhook":
        raise HTTPException(status_code=400, detail="Only webhook triggers have tokens")
    token = new_webhook_token()
    trig.webhook_token_hash = hash_token(token)
    audit(db, "trigger.rotate_token", user=user, resource_type="trigger", resource_id=trig.id, request=request)
    db.refresh(trig)
    out = TriggerCreated.model_validate(trig)
    out.webhook_token = token
    return out


@router.delete("/{trigger_id}")
def delete_trigger(
    trigger_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("trigger:write")),
):
    trig = _visible_trigger(db, trigger_id, user)
    db.delete(trig)
    audit(db, "trigger.delete", user=user, resource_type="trigger", resource_id=trigger_id, request=request)
    return {"status": "deleted"}


async def _raw_body(request: Request) -> bytes:
    return await request.body()


@hooks.post("/{trigger_id}", response_model=RunOut, status_code=202)
def receive_webhook(
    trigger_id: int,
    request: Request,
    db: Session = Depends(get_db),
    x_webhook_token: str = Header(default=""),
    raw: bytes = Depends(_raw_body),
):
    """Start the trigger's active workflow. Authenticate with header `X-Webhook-Token`.
    The JSON body (an object) is merged over the trigger's default input."""
    trig = db.get(Trigger, trigger_id)
    valid = (
        trig is not None
        and trig.type == "webhook"
        and trig.is_enabled
        and trig.webhook_token_hash
        and hmac.compare_digest(trig.webhook_token_hash, hash_token(x_webhook_token))
    )
    if not valid:
        audit(db, "webhook.receive", resource_type="trigger", resource_id=trigger_id, status="denied", request=request)
        raise HTTPException(status_code=404, detail="Not found")

    if len(raw) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    payload: Any = {}
    if raw.strip():
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail="Body must be JSON")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object")

    run = start_trigger_run(db, trig, {**(trig.input or {}), **payload}, "webhook")
    if run is None:
        raise HTTPException(status_code=409, detail="Workflow has no active version or the trigger owner lost access")
    trig.last_run_at = utcnow()
    audit(
        db,
        "webhook.receive",
        resource_type="trigger",
        resource_id=trigger_id,
        details={"run_id": run.id},
        request=request,
    )
    submit_run(run.id)
    return run
