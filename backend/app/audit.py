"""Audit trail. Every security-relevant action writes one row to audit_logs."""

import logging
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditLog, User

logger = logging.getLogger("agentos.audit")


def client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    # Use the address appended by our own proxy (right-most entry); the left-most entries are
    # whatever the client sent and can be forged (security finding L3).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else None


def audit(
    db: Session,
    action: str,
    *,
    user: Optional[User] = None,
    user_email: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Any = None,
    status: str = "success",
    details: Optional[dict] = None,
    request: Optional[Request] = None,
    commit: bool = True,
) -> None:
    entry = AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else user_email,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        status=status,
        details=details,
        ip_address=client_ip(request),
        request_id=getattr(request.state, "request_id", None) if request else None,
    )
    db.add(entry)
    if commit:
        db.commit()
    logger.info(
        "audit",
        extra={
            "action": action,
            "status": status,
            "user_id": entry.user_id,
            "resource": f"{resource_type}:{resource_id}",
        },
    )
