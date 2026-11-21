from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import audit
from ..database import get_db
from ..models import AuditLog, Run, Trigger, User, Workflow
from ..rbac import can_edit, can_view, has_permission, is_admin, require_permission, visible_filter
from ..schemas import (
    DefinitionCheckIn,
    GenerateRequest,
    RunOut,
    ValidationOut,
    WorkflowIn,
    WorkflowOut,
    WorkflowRunRequest,
)
from ..services.ai_builder import BuilderError
from ..services.ai_builder import generate as ai_generate
from ..services.blueprint import to_definition
from ..services.form_input import check_input
from ..services.runs import create_run, enforce_rate_limit, execute_run, submit_run
from ..services.templates_library import BY_KEY as TEMPLATES_BY_KEY
from ..services.templates_library import TEMPLATES
from ..services.workflow_validator import reference_problems, validate_definition

router = APIRouter(prefix="/api/workflows", tags=["workflows"])
templates_router = APIRouter(prefix="/api/templates", tags=["templates"])


def _out(wf: Workflow, user: User) -> WorkflowOut:
    out = WorkflowOut.model_validate(wf)
    out.can_edit = can_edit(user, wf)
    return out


def _get_visible(db: Session, workflow_id: int, user: User) -> Workflow:
    wf = db.get(Workflow, workflow_id)
    if wf is None or not can_view(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


def _owner(db: Session, wf: Workflow) -> User | None:
    return db.get(User, wf.owner_id) if wf.owner_id else None


def _checked_input(wf: Workflow, data: dict) -> dict:
    cleaned, problems = check_input(wf.definition or {}, data)
    if problems:
        raise HTTPException(status_code=400, detail={"message": "Please check the form", "errors": problems})
    return cleaned


def _require_edit(user: User, wf: Workflow) -> None:
    if not can_edit(user, wf):
        raise HTTPException(status_code=403, detail="You cannot edit this workflow")


@router.get("", response_model=list[WorkflowOut])
def list_workflows(
    include_archived: bool = False,
    group_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:read")),
):
    q = visible_filter(db.query(Workflow), Workflow, user)
    if group_id:
        q = q.filter(Workflow.group_id == group_id)
    rows = [
        w for w in q.order_by(Workflow.name, Workflow.group_id, Workflow.version.desc()).all() if _listable(user, w)
    ]
    if group_id or include_archived:
        return [_out(w, user) for w in rows]
    # Hide archived versions, except the newest one of an automation that has nothing else
    # (a turned-off automation stays visible so it can be turned back on).
    groups: dict[str, list] = {}
    for w in rows:
        groups.setdefault(w.group_id, []).append(w)
    out = []
    for versions in groups.values():
        current = [w for w in versions if w.status != "archived"]
        archived = [w for w in versions if w.status == "archived"]
        out.extend(current)
        # No live version: also return the newest old version, so a turned-off workflow
        # (even one with a leftover draft) can be turned back on from the list.
        if archived and not any(w.status == "active" for w in current):
            out.append(max(archived, key=lambda w: w.version))
    return [_out(w, user) for w in out]


def _listable(user: User, wf: Workflow) -> bool:
    """Visible, and - for people who cannot edit automations - only published versions."""
    if not can_view(user, wf):
        return False
    return wf.status == "active" or has_permission(user, "workflow:write")


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(
    workflow_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("workflow:read"))
):
    wf = _get_visible(db, workflow_id, user)
    if not _listable(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _out(wf, user)


@router.post("", response_model=WorkflowOut, status_code=201)
def create_workflow(
    body: WorkflowIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:write")),
):
    """Create a new workflow, or a new draft version when group_id is given."""
    version, group_id, owner_id = 1, None, user.id
    if body.group_id:
        latest = (
            db.query(Workflow)
            .filter(Workflow.group_id == body.group_id, Workflow.org_id == user.org_id)
            .order_by(Workflow.version.desc())
            .first()
        )
        if latest is None or not can_view(user, latest):
            raise HTTPException(status_code=404, detail="Workflow not found")
        _require_edit(user, latest)
        version = (db.query(func.max(Workflow.version)).filter(Workflow.group_id == body.group_id).scalar() or 0) + 1
        group_id = body.group_id
        # A new version keeps the workflow's owner, whose access its steps use.
        owner_id = latest.owner_id or user.id

    data = body.model_dump(exclude={"group_id"})
    data["department"] = (body.department or None) if is_admin(user) else user.department
    wf = Workflow(**data, version=version, status="draft", owner_id=owner_id, org_id=user.org_id)
    if group_id:
        wf.group_id = group_id
    db.add(wf)
    db.flush()
    audit(
        db,
        "workflow.create",
        user=user,
        resource_type="workflow",
        resource_id=wf.id,
        details={"name": wf.name, "group_id": wf.group_id, "version": wf.version},
        request=request,
    )
    db.refresh(wf)
    return _out(wf, user)


@router.put("/{workflow_id}", response_model=WorkflowOut)
def update_draft(
    workflow_id: int,
    body: WorkflowIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:write")),
):
    wf = _get_visible(db, workflow_id, user)
    _require_edit(user, wf)
    if wf.status != "draft":
        raise HTTPException(status_code=409, detail="Only drafts can be edited. Save a new version instead.")
    data = body.model_dump(exclude={"group_id"})
    data["department"] = (body.department or None) if is_admin(user) else user.department
    for k, v in data.items():
        setattr(wf, k, v)
    audit(db, "workflow.update", user=user, resource_type="workflow", resource_id=wf.id, request=request)
    db.refresh(wf)
    return _out(wf, user)


@router.delete("/{workflow_id}")
def delete_draft(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:write")),
):
    wf = _get_visible(db, workflow_id, user)
    _require_edit(user, wf)
    if wf.status != "draft":
        raise HTTPException(status_code=409, detail="Only drafts can be deleted. Deactivate active versions instead.")
    db.delete(wf)
    audit(db, "workflow.delete", user=user, resource_type="workflow", resource_id=workflow_id, request=request)
    return {"status": "deleted"}


@router.post("/validate-definition", response_model=ValidationOut)
def validate_unsaved(
    body: DefinitionCheckIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:write")),
):
    """Check a definition that is not saved yet (the builder calls this while you edit).
    Agents and connections are checked with the caller's access, or the owner's for an
    existing workflow the caller can edit."""
    owner = user
    if body.workflow_id is not None:
        wf = _get_visible(db, body.workflow_id, user)
        owner = _owner(db, wf) or user
    errors = validate_definition(body.definition, db, owner=owner)
    return ValidationOut(is_valid=not errors, errors=errors, warnings=reference_problems(body.definition)[1])


@router.post("/{workflow_id}/validate", response_model=ValidationOut)
def validate(
    workflow_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("workflow:read"))
):
    wf = _get_visible(db, workflow_id, user)
    errors = validate_definition(wf.definition, db, owner=_owner(db, wf))
    return ValidationOut(is_valid=not errors, errors=errors, warnings=reference_problems(wf.definition)[1])


@router.post("/{workflow_id}/activate", response_model=WorkflowOut)
def activate(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:activate")),
):
    wf = _get_visible(db, workflow_id, user)
    _require_edit(user, wf)
    errors = validate_definition(wf.definition, db, owner=_owner(db, wf))
    if errors:
        audit(
            db,
            "workflow.activate",
            user=user,
            resource_type="workflow",
            resource_id=wf.id,
            status="failure",
            details={"errors": errors},
            request=request,
        )
        raise HTTPException(status_code=400, detail={"message": "Validation failed", "errors": errors})
    previous = (
        db.query(Workflow)
        .filter(Workflow.group_id == wf.group_id, Workflow.status == "active", Workflow.id != wf.id)
        .all()
    )
    for old in previous:
        old.status = "archived"
    wf.status = "active"
    if wf.published_at is None:  # from now on this version is immutable
        wf.published_at = datetime.now(timezone.utc)
        wf.published_by = user.id
    audit(
        db,
        "workflow.activate",
        user=user,
        resource_type="workflow",
        resource_id=wf.id,
        details={"version": wf.version, "archived": [o.id for o in previous]},
        request=request,
    )
    db.refresh(wf)
    return _out(wf, user)


@router.post("/{workflow_id}/deactivate", response_model=WorkflowOut)
def deactivate(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:activate")),
):
    wf = _get_visible(db, workflow_id, user)
    _require_edit(user, wf)
    if wf.status != "active":
        raise HTTPException(status_code=409, detail="Workflow version is not active")
    wf.status = "archived"
    audit(db, "workflow.deactivate", user=user, resource_type="workflow", resource_id=wf.id, request=request)
    db.refresh(wf)
    return _out(wf, user)


@router.post("/{workflow_id}/test", response_model=RunOut)
def test(
    workflow_id: int,
    body: WorkflowRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:write")),
    background: bool = False,
):
    """Run any version (including drafts), for builders. Synchronous by default; with
    `?background=true` it returns at once and the builder follows GET /api/runs/{id}."""
    wf = _get_visible(db, workflow_id, user)
    _require_edit(user, wf)
    errors = validate_definition(wf.definition, db, owner=_owner(db, wf))
    if errors:
        raise HTTPException(status_code=400, detail={"message": "Validation failed", "errors": errors})
    data = _checked_input(wf, body.input)
    enforce_rate_limit(db, user)
    if background:
        run = create_run(db, target=wf, user=user, source="test", input_data=data)
        audit(
            db,
            "workflow.test",
            user=user,
            resource_type="workflow",
            resource_id=wf.id,
            details={"run_id": run.id, "background": True},
            request=request,
        )
        submit_run(run.id)
        db.refresh(run)
        return run
    run = create_run(db, target=wf, user=user, source="test", input_data=data, hold=True)
    execute_run(run.id)
    db.expire_all()
    run = db.get(Run, run.id)
    audit(
        db,
        "workflow.test",
        user=user,
        resource_type="workflow",
        resource_id=wf.id,
        status="success" if run.status == "succeeded" else "failure",
        details={"run_id": run.id},
        request=request,
    )
    return run


@router.post("/{workflow_id}/run", response_model=RunOut, status_code=202)
def run(
    workflow_id: int,
    body: WorkflowRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:run")),
):
    """Start a published version in the background. Poll GET /api/runs/{id} for the result.

    Normally the live (active) version; an earlier published version can be run explicitly by
    its id (it is immutable, and is re-checked first because its agents or connections may have
    changed since)."""
    wf = _get_visible(db, workflow_id, user)
    if wf.status != "active":
        if wf.published_at is None:
            raise HTTPException(status_code=409, detail="This version was never published, so it cannot be run")
        if not has_permission(user, "workflow:write"):
            raise HTTPException(status_code=403, detail="Only builders can run an earlier version")
        errors = validate_definition(wf.definition, db, owner=_owner(db, wf))
        if errors:
            raise HTTPException(
                status_code=409, detail={"message": "This earlier version is no longer valid", "errors": errors}
            )
    data = _checked_input(wf, body.input)
    enforce_rate_limit(db, user)
    run_row = create_run(db, target=wf, user=user, source="form" if body.from_form else "api", input_data=data)
    audit(
        db,
        "workflow.run",
        user=user,
        resource_type="workflow",
        resource_id=wf.id,
        details={"run_id": run_row.id},
        request=request,
    )
    submit_run(run_row.id)
    return run_row


# ---------------- templates & AI builder ----------------
@templates_router.get("")
def list_templates(user: User = Depends(require_permission("workflow:read"))):
    return [
        {k: t[k] for k in ("key", "name", "category", "description", "needs")} | {"steps": len(t["steps"])}
        for t in TEMPLATES
    ]


@templates_router.post("/{key}/use", response_model=WorkflowOut, status_code=201)
def use_template(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:write")),
):
    tpl = TEMPLATES_BY_KEY.get(key)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    wf = Workflow(
        name=tpl["name"],
        description=tpl["description"],
        definition=to_definition(tpl),
        status="draft",
        visibility="private",
        department=user.department,
        owner_id=user.id,
        org_id=user.org_id,
    )
    db.add(wf)
    db.flush()
    audit(
        db,
        "workflow.create",
        user=user,
        resource_type="workflow",
        resource_id=wf.id,
        details={"name": wf.name, "template": key},
        request=request,
    )
    db.refresh(wf)
    return _out(wf, user)


@router.post("/generate")
def generate_workflow(
    body: GenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:write")),
):
    """Draft a workflow from a description. Nothing is saved; the builder shows it for review."""
    recent = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == user.id,
            AuditLog.action == "workflow.generate",
            AuditLog.created_at >= datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        .count()
    )
    if recent >= 10:
        raise HTTPException(status_code=429, detail="Too many AI drafts in a minute; wait a moment and try again")
    try:
        result = ai_generate(db, user, body.prompt)
    except BuilderError as exc:
        audit(db, "workflow.generate", user=user, status="failure", details={"error": str(exc)[:300]}, request=request)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(
        db,
        "workflow.generate",
        user=user,
        details={"name": result["name"], "steps": len(result["definition"]["nodes"])},
        request=request,
    )
    return result


@router.post("/{workflow_id}/duplicate", response_model=WorkflowOut, status_code=201)
def duplicate(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:write")),
):
    """Copy any automation you can see into a new private draft you own."""
    src = _get_visible(db, workflow_id, user)
    wf = Workflow(
        name=f"Copy of {src.name}"[:200],
        description=src.description,
        definition=src.definition,
        status="draft",
        visibility="private",
        department=user.department,
        owner_id=user.id,
        org_id=user.org_id,
    )
    db.add(wf)
    db.flush()
    audit(
        db,
        "workflow.duplicate",
        user=user,
        resource_type="workflow",
        resource_id=wf.id,
        details={"from": src.id},
        request=request,
    )
    db.refresh(wf)
    return _out(wf, user)


@router.get("/groups/{group_id}/versions")
def version_history(
    group_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("workflow:read"))
):
    """Every version of a workflow (newest first) with its state and run counts."""
    versions = (
        db.query(Workflow)
        .filter(Workflow.group_id == group_id, Workflow.org_id == user.org_id)
        .order_by(Workflow.version.desc())
        .all()
    )
    if not versions or not can_view(user, versions[0]):
        raise HTTPException(status_code=404, detail="Workflow not found")
    ids = [v.id for v in versions]
    counts: dict[int, dict] = {}
    for target_id, status, n in (
        db.query(Run.target_id, Run.status, func.count())
        .filter(Run.target_type == "workflow", Run.target_id.in_(ids))
        .group_by(Run.target_id, Run.status)
    ):
        counts.setdefault(target_id, {})[status] = n
    return [
        {
            "id": v.id,
            "version": v.version,
            "status": v.status,
            "published": v.published_at is not None,
            "published_at": v.published_at,
            "published_by": v.published_by,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
            "runs": counts.get(v.id, {}),
        }
        for v in versions
        if _listable(user, v) or v.published_at is not None
    ]


@router.delete("/groups/{group_id}")
def delete_automation(
    group_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:write")),
):
    """Delete an automation: every version and its schedules/webhooks. Run history is kept."""
    versions = db.query(Workflow).filter(Workflow.group_id == group_id, Workflow.org_id == user.org_id).all()
    latest = max(versions, key=lambda w: w.version) if versions else None
    if latest is None or not can_view(user, latest):
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not (is_admin(user) or latest.owner_id == user.id):
        raise HTTPException(status_code=403, detail="Only the owner or an admin can delete a workflow")
    triggers = db.query(Trigger).filter(Trigger.workflow_group_id == group_id, Trigger.org_id == user.org_id).all()
    for t in triggers:
        db.delete(t)
    for v in versions:
        db.delete(v)
    audit(
        db,
        "workflow.delete_all",
        user=user,
        resource_type="workflow",
        resource_id=group_id,
        details={"name": latest.name, "versions": len(versions), "triggers": len(triggers)},
        request=request,
    )
    return {"status": "deleted", "versions": len(versions), "triggers": len(triggers)}
