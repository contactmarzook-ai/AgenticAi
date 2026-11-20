from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..database import get_db
from ..models import Agent, Run, User, Workflow
from ..rbac import can_edit, can_view, has_permission, require_permission
from ..schemas import Page, RunOut, RunSummary
from ..services.runs import create_run, enforce_rate_limit, submit_run

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=Page)
def list_runs(
    status: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    source: Optional[str] = None,
    mine: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("run:read_own")),
):
    q = db.query(Run)
    if mine or not has_permission(user, "run:read_all"):
        q = q.filter(Run.user_id == user.id)
    if status:
        q = q.filter(Run.status == status)
    if target_type:
        q = q.filter(Run.target_type == target_type)
    if target_id is not None:
        q = q.filter(Run.target_id == target_id)
    if source:
        q = q.filter(Run.source == source)
    total = q.count()
    rows = q.order_by(Run.id.desc()).offset(offset).limit(limit).all()
    return Page(items=[RunSummary.model_validate(r) for r in rows], total=total)


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("run:read_own"))):
    run = db.get(Run, run_id)
    if run is None or (run.user_id != user.id and not has_permission(user, "run:read_all")):
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/{run_id}/rerun", response_model=RunOut, status_code=202)
def rerun(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("run:read_own")),
):
    """Run the same agent/workflow again with the same input (workflows use the current active version)."""
    run = db.get(Run, run_id)
    if run is None or (run.user_id != user.id and not has_permission(user, "run:read_all")):
        raise HTTPException(status_code=404, detail="Run not found")
    if run.target_type == "agent":
        target = db.get(Agent, run.target_id)
        ok = target is not None and target.is_active and can_view(user, target) and has_permission(user, "agent:run")
    else:
        old = db.get(Workflow, run.target_id)
        target = (
            db.query(Workflow).filter(Workflow.group_id == old.group_id, Workflow.status == "active").first()
            if old
            else None
        )
        if run.source == "test" and old is not None and can_edit(user, old):
            target = old  # re-test the same version
        ok = target is not None and can_view(user, target) and has_permission(user, "workflow:run")
    if not ok:
        raise HTTPException(status_code=409, detail="This can no longer be run (it was disabled, archived or unshared)")
    enforce_rate_limit(db, user)
    new = create_run(
        db,
        target=target,
        user=user,
        source=run.source if run.source in ("test", "api") else "api",
        input_data=run.input or {},
    )
    audit(
        db,
        "run.rerun",
        user=user,
        resource_type="run",
        resource_id=new.id,
        details={"from_run": run_id},
        request=request,
    )
    submit_run(new.id)
    return new
