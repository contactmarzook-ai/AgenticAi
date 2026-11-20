from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import audit
from ..database import get_db
from ..models import Run, User, Workflow
from ..rbac import can_edit, can_view, require_permission
from ..schemas import RunOut, ValidationOut, WorkflowIn, WorkflowOut, WorkflowRunRequest
from ..services.runs import create_run, enforce_rate_limit, execute_run, submit_run
from ..services.workflow_validator import validate_definition

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _out(wf: Workflow, user: User) -> WorkflowOut:
    out = WorkflowOut.model_validate(wf)
    out.can_edit = can_edit(user, wf)
    return out


def _get_visible(db: Session, workflow_id: int, user: User) -> Workflow:
    wf = db.get(Workflow, workflow_id)
    if wf is None or not can_view(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


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
    q = db.query(Workflow)
    if group_id:
        q = q.filter(Workflow.group_id == group_id)
    elif not include_archived:
        q = q.filter(Workflow.status != "archived")
    rows = q.order_by(Workflow.name, Workflow.group_id, Workflow.version.desc()).all()
    return [_out(w, user) for w in rows if can_view(user, w)]


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(
    workflow_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("workflow:read"))
):
    return _out(_get_visible(db, workflow_id, user), user)


@router.post("", response_model=WorkflowOut, status_code=201)
def create_workflow(
    body: WorkflowIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:write")),
):
    """Create a new workflow, or a new draft version when group_id is given."""
    version, group_id = 1, None
    if body.group_id:
        latest = db.query(Workflow).filter(Workflow.group_id == body.group_id).order_by(Workflow.version.desc()).first()
        if latest is None or not can_view(user, latest):
            raise HTTPException(status_code=404, detail="Workflow not found")
        _require_edit(user, latest)
        version = (db.query(func.max(Workflow.version)).filter(Workflow.group_id == body.group_id).scalar() or 0) + 1
        group_id = body.group_id

    data = body.model_dump(exclude={"group_id"})
    data["department"] = (body.department or None) if user.role == "admin" else user.department
    wf = Workflow(**data, version=version, status="draft", owner_id=user.id)
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
    data["department"] = (body.department or None) if user.role == "admin" else user.department
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


@router.post("/{workflow_id}/validate", response_model=ValidationOut)
def validate(
    workflow_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("workflow:read"))
):
    wf = _get_visible(db, workflow_id, user)
    errors = validate_definition(wf.definition, db)
    return ValidationOut(is_valid=not errors, errors=errors)


@router.post("/{workflow_id}/activate", response_model=WorkflowOut)
def activate(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workflow:activate")),
):
    wf = _get_visible(db, workflow_id, user)
    _require_edit(user, wf)
    errors = validate_definition(wf.definition, db)
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
):
    """Run any version (including drafts) synchronously, for builders."""
    wf = _get_visible(db, workflow_id, user)
    _require_edit(user, wf)
    errors = validate_definition(wf.definition, db)
    if errors:
        raise HTTPException(status_code=400, detail={"message": "Validation failed", "errors": errors})
    enforce_rate_limit(db, user)
    run = create_run(db, target=wf, user=user, source="test", input_data=body.input)
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
    """Start an active workflow in the background. Poll GET /api/runs/{id} for the result."""
    wf = _get_visible(db, workflow_id, user)
    if wf.status != "active":
        raise HTTPException(status_code=409, detail="Only the active version of a workflow can be run")
    enforce_rate_limit(db, user)
    run_row = create_run(db, target=wf, user=user, source="api", input_data=body.input)
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
