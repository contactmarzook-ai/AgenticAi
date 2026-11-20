from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Run, User
from ..rbac import has_permission, require_permission
from ..schemas import Page, RunOut, RunSummary

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
