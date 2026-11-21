from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Agent, AuditLog, Run, User, Workflow
from ..rbac import is_platform_admin, require_permission
from ..schemas import AuditOut, Page

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/audit", response_model=Page)
def list_audit(
    action: Optional[str] = None,
    user_email: Optional[str] = None,
    status: Optional[str] = None,
    resource_type: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    org_id: Optional[int] = None,
    user: User = Depends(require_permission("audit:read")),
):
    # Organization admins and auditors see their organization; platform admins see everything
    # (or one organization with ?org_id=).
    q = db.query(AuditLog)
    if not is_platform_admin(user):
        q = q.filter(AuditLog.org_id == user.org_id)
    elif org_id is not None:
        q = q.filter(AuditLog.org_id == org_id)
    if action:
        q = q.filter(AuditLog.action.like(f"{action}%"))
    if user_email:
        q = q.filter(AuditLog.user_email.ilike(f"%{user_email}%"))
    if status:
        q = q.filter(AuditLog.status == status)
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if since:
        q = q.filter(AuditLog.created_at >= since)
    if until:
        q = q.filter(AuditLog.created_at <= until)
    total = q.count()
    rows = q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    return Page(items=[AuditOut.model_validate(r) for r in rows], total=total)


@router.get("/metrics")
def metrics(
    hours: int = Query(24, ge=1, le=24 * 90),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("monitoring:read")),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    org = user.org_id
    runs = db.query(Run).filter(Run.org_id == org, Run.created_at >= since)

    by_status = dict(runs.with_entities(Run.status, func.count()).group_by(Run.status).all())
    by_source = dict(runs.with_entities(Run.source, func.count()).group_by(Run.source).all())
    tokens = runs.with_entities(
        func.coalesce(func.sum(Run.prompt_tokens), 0), func.coalesce(func.sum(Run.completion_tokens), 0)
    ).one()

    finished = (
        runs.filter(Run.finished_at.isnot(None), Run.started_at.isnot(None))
        .with_entities(Run.started_at, Run.finished_at)
        .all()
    )
    durations = sorted((f - s).total_seconds() for s, f in finished)
    p50 = durations[len(durations) // 2] if durations else 0
    p95 = durations[int(len(durations) * 0.95) - 1] if len(durations) >= 20 else (durations[-1] if durations else 0)

    top = (
        runs.with_entities(
            Run.target_type,
            Run.target_name,
            func.count().label("n"),
            func.sum(case((Run.status == "failed", 1), else_=0)).label("failed"),
        )
        .group_by(Run.target_type, Run.target_name)
        .order_by(func.count().desc())
        .limit(10)
        .all()
    )
    total = sum(by_status.values())
    return {
        "window_hours": hours,
        "runs_total": total,
        "runs_by_status": by_status,
        "runs_by_source": by_source,
        "success_rate": round(100 * by_status.get("succeeded", 0) / total, 1) if total else None,
        "prompt_tokens": int(tokens[0]),
        "completion_tokens": int(tokens[1]),
        "duration_p50_sec": round(p50, 2),
        "duration_p95_sec": round(p95, 2),
        "top_targets": [{"type": t, "name": n, "runs": c, "failed": int(f or 0)} for t, n, c, f in top],
        "inventory": {
            "users_active": db.query(User).filter(User.org_id == org, User.is_active.is_(True)).count(),
            "agents_active": db.query(Agent).filter(Agent.org_id == org, Agent.is_active.is_(True)).count(),
            "workflows_active": db.query(Workflow).filter(Workflow.org_id == org, Workflow.status == "active").count(),
        },
        "failed_logins": db.query(AuditLog)
        .filter(
            AuditLog.org_id == org,
            AuditLog.action == "auth.login",
            AuditLog.status != "success",
            AuditLog.created_at >= since,
        )
        .count(),
    }
