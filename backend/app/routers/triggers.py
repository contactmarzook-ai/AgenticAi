import hmac
import json
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from .. import ratelimit
from ..audit import audit
from ..config import settings
from ..database import get_db
from ..models import Run, Trigger, User, Workflow, utcnow
from ..rbac import can_edit, can_view, is_admin, require_permission
from ..schemas import RunOut, TriggerCreated, TriggerIn, TriggerOut, WorkflowRunRequest
from ..security import hash_token, new_webhook_token
from ..services.form_input import check_input, form_fields
from ..services.runs import execute_run, submit_run
from ..services.scheduler import InputProblem, active_version, next_fire_time, start_trigger_run, valid_cron

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


def _check_schedule_input(db: Session, body: TriggerIn) -> None:
    """A schedule cannot ask anyone for input, so it must supply every required form field."""
    if body.type != "schedule":
        return
    wf = _latest(db, body.workflow_group_id)
    _, problems = check_input((wf.definition if wf else {}) or {}, body.input or {})
    if problems:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "A schedule runs without anyone filling in the form. Set default values",
                "errors": problems,
            },
        )


def _visible_trigger(db: Session, trigger_id: int, user: User) -> Trigger:
    trig = db.get(Trigger, trigger_id)
    if trig is None or trig.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Trigger not found")
    wf = _latest(db, trig.workflow_group_id)
    owns = trig.owner_id == user.id and wf is not None and can_view(user, wf)
    if not is_admin(user) and not owns and not (wf and can_edit(user, wf)):
        raise HTTPException(status_code=404, detail="Trigger not found")
    return trig


@router.get("", response_model=list[TriggerOut])
def list_triggers(
    workflow_group_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("trigger:write")),
):
    q = db.query(Trigger).filter(Trigger.org_id == user.org_id)
    if workflow_group_id:
        q = q.filter(Trigger.workflow_group_id == workflow_group_id)
    out = []
    for trig in q.order_by(Trigger.id).all():
        wf = _latest(db, trig.workflow_group_id)
        if is_admin(user) or (wf and (can_edit(user, wf) or (trig.owner_id == user.id and can_view(user, wf)))):
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
    _check_schedule_input(db, body)
    trig = Trigger(**body.model_dump(exclude={"options"}), owner_id=user.id, org_id=user.org_id)
    trig.options = body.options.model_dump() if body.options and body.type == "form" else None
    token = None
    if body.type == "schedule":
        trig.next_run_at = next_fire_time(body.cron, body.timezone) if body.is_enabled else None
        trig.cron = body.cron
    else:
        trig.cron = None
        token = new_webhook_token() if body.type == "webhook" else "frm_" + new_webhook_token()[4:]
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
    _check_schedule_input(db, body)
    for k in ("name", "cron", "timezone", "input", "is_enabled"):
        setattr(trig, k, getattr(body, k))
    if trig.type == "form":
        trig.options = body.options.model_dump() if body.options else trig.options
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
    if trig.type not in ("webhook", "form"):
        raise HTTPException(status_code=400, detail="Only webhooks and form links have tokens")
    token = new_webhook_token() if trig.type == "webhook" else "frm_" + new_webhook_token()[4:]
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


def _verified_webhook(
    trigger_id: int,
    request: Request,
    db: Session = Depends(get_db),
    x_webhook_token: str = Header(default=""),
) -> Trigger:
    """Checked before the request body is read (dependencies resolve in order)."""
    ratelimit.check(request, "public", settings.public_requests_per_minute)
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
    return trig


@hooks.post("/{trigger_id}", response_model=RunOut, status_code=202)
def receive_webhook(
    trigger_id: int,
    request: Request,
    db: Session = Depends(get_db),
    trig: Trigger = Depends(_verified_webhook),
    raw: bytes = Depends(_raw_body),
):
    """Start the trigger's active workflow. Authenticate with header `X-Webhook-Token`.
    The JSON body (an object) supplies the input; values fixed on the trigger take precedence."""
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

    try:
        # Values fixed on the trigger win over the caller's (security finding M2).
        run = start_trigger_run(db, trig, {**payload, **(trig.input or {})}, "webhook")
    except InputProblem as exc:
        audit(
            db,
            "webhook.receive",
            resource_type="trigger",
            resource_id=trigger_id,
            status="failure",
            details={"errors": exc.problems},
            request=request,
        )
        raise HTTPException(status_code=400, detail={"message": "Invalid input", "errors": exc.problems}) from exc
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


# ---------------- public form links (no sign-in) ----------------
public = APIRouter(prefix="/api/public/forms", tags=["public forms"])
FORM_SUBMISSIONS_PER_MINUTE = 20


def _form_trigger(db: Session, trigger_id: int, token: str, request: Request) -> Trigger:
    # Per-address limit: slows down token guessing and anonymous flooding.
    ratelimit.check(request, "public", settings.public_requests_per_minute)
    trig = db.get(Trigger, trigger_id)
    if not (
        trig is not None
        and trig.type == "form"
        and trig.is_enabled
        and trig.webhook_token_hash
        and hmac.compare_digest(trig.webhook_token_hash, hash_token(token or ""))
    ):
        raise HTTPException(status_code=404, detail="This form link is not valid or has been switched off")
    return trig


@public.get("/{trigger_id}")
def public_form(
    trigger_id: int, request: Request, db: Session = Depends(get_db), x_form_token: str = Header(default="")
):
    trig = _form_trigger(db, trigger_id, x_form_token, request)
    wf = active_version(db, trig.workflow_group_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="This form is not available right now")
    opts = trig.options or {}
    return {
        "title": opts.get("title") or wf.name,
        "intro": opts.get("intro") or wf.description or "",
        "fields": form_fields(wf.definition or {}),
    }


@public.post("/{trigger_id}", status_code=202)
def submit_public_form(
    trigger_id: int,
    body: WorkflowRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    x_form_token: str = Header(default=""),
):
    trig = _form_trigger(db, trigger_id, x_form_token, request)
    recent = db.query(Run).filter(Run.trigger_id == trig.id, Run.created_at >= utcnow() - timedelta(minutes=1)).count()
    if recent >= FORM_SUBMISSIONS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Too many submissions right now. Please try again in a minute.")
    try:
        # Anonymous submitters may only fill the form's own fields, and cannot change values
        # fixed on the trigger (security finding M2).
        wf_now = active_version(db, trig.workflow_group_id)
        declared = {f["key"] for f in form_fields((wf_now.definition if wf_now else {}) or {})}
        submitted = {k: v for k, v in (body.input or {}).items() if k in declared}
        run = start_trigger_run(db, trig, {**submitted, **(trig.input or {})}, "form_link")
    except InputProblem as exc:
        raise HTTPException(
            status_code=400, detail={"message": "Please check the form", "errors": exc.problems}
        ) from exc
    if run is None:
        raise HTTPException(status_code=409, detail="This form is not available right now")
    trig.last_run_at = utcnow()
    audit(db, "form.submit", resource_type="trigger", resource_id=trig.id, details={"run_id": run.id}, request=request)
    opts = trig.options or {}
    message = opts.get("success_message") or "Thank you - your submission was received."
    if not opts.get("show_result"):
        submit_run(run.id)
        return {"status": "received", "message": message}
    execute_run(run.id)
    db.expire_all()
    run = db.get(Run, run.id)
    if run.status != "succeeded":
        return {"status": "failed", "message": "Sorry, something went wrong while processing your submission."}
    return {"status": "done", "message": message, "result": (run.output or {}).get("result")}
