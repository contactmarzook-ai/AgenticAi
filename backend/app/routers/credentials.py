import smtplib
import ssl

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import safe_http
from ..audit import audit
from ..crypto import decrypt_json, encrypt_json
from ..database import get_db
from ..models import Credential, User, Workflow
from ..nodes import CREDENTIAL_TYPES
from ..rbac import can_view, is_admin, require_permission, role_level, same_org, visible_filter
from ..schemas import CredentialIn, CredentialOut, CredentialTestOut
from ..services.platform_settings import get_settings

router = APIRouter(prefix="/api/credentials", tags=["connections"])
# Builders, admins and auditors (read-only) see connections; viewers and operators never need them.
_reader = require_permission("tool:read")


def _require_creator(db: Session, user: User) -> None:
    min_role = get_settings(db).get("connections_min_role", "developer")
    if role_level(user.role) < max(role_level(min_role), 2) or user.role == "auditor":
        raise HTTPException(status_code=403, detail=f"Only {min_role}s can manage connections")


def _can_edit(user: User, cred: Credential) -> bool:
    return same_org(user, cred) and (is_admin(user) or cred.owner_id == user.id)


def _out(cred: Credential, user: User) -> CredentialOut:
    out = CredentialOut.model_validate(cred)
    ctype = CREDENTIAL_TYPES.get(cred.type)
    try:
        data = decrypt_json(cred.data_encrypted)
    except ValueError:
        data = {}
    secret_keys = {f.key for f in ctype.fields if f.type == "password"} if ctype else set(data)
    out.public_data = {k: v for k, v in data.items() if k not in secret_keys}
    out.can_edit = _can_edit(user, cred)
    return out


def _check_destination(db: Session, ctype_key: str, data: dict) -> None:
    try:
        if ctype_key in ("slack_webhook", "teams_webhook") and data.get("url"):
            safe_http.check_webhook_url(
                str(data["url"]), "slack" if ctype_key == "slack_webhook" else "teams", get_settings(db)
            )
    except safe_http.BlockedRequest as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _clean(ctype, data: dict, existing: dict | None = None) -> dict:
    result = {}
    for f in ctype.fields:
        value = data.get(f.key)
        if f.type == "password" and value in (None, "") and existing is not None:
            value = existing.get(f.key)  # keep the saved secret
        if value in (None, "") and f.default is not None:
            value = f.default
        if f.required and value in (None, ""):
            raise HTTPException(status_code=400, detail=f"'{f.label}' is required")
        if f.key == "url" and value not in (None, "") and not str(value).strip().lower().startswith("https://"):
            raise HTTPException(status_code=400, detail=f"'{f.label}' must be a web address starting with https://")
        if f.key == "port" and value not in (None, ""):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"'{f.label}' must be a number") from None
        if value not in (None, ""):
            result[f.key] = value
    return result


def _checked(db: Session, ctype, data: dict, existing: dict | None = None) -> dict:
    cleaned = _clean(ctype, data, existing)
    _check_destination(db, ctype.key, cleaned)
    return cleaned


def _get(db: Session, cred_id: int, user: User) -> Credential:
    cred = db.get(Credential, cred_id)
    if cred is None or not can_view(user, cred):
        raise HTTPException(status_code=404, detail="Connection not found")
    return cred


@router.get("", response_model=list[CredentialOut])
def list_credentials(type: str | None = None, db: Session = Depends(get_db), user: User = Depends(_reader)):
    q = visible_filter(db.query(Credential), Credential, user)
    if type:
        q = q.filter(Credential.type.in_(type.split("|")))
    return [_out(c, user) for c in q.order_by(Credential.name).all() if can_view(user, c)]


@router.post("", response_model=CredentialOut, status_code=201)
def create_credential(
    body: CredentialIn, request: Request, db: Session = Depends(get_db), user: User = Depends(_reader)
):
    _require_creator(db, user)
    ctype = CREDENTIAL_TYPES.get(body.type)
    if ctype is None:
        raise HTTPException(status_code=400, detail="Unknown connection type")
    cred = Credential(
        name=body.name,
        type=body.type,
        data_encrypted=encrypt_json(_checked(db, ctype, body.data)),
        visibility=body.visibility,
        department=user.department,
        owner_id=user.id,
        org_id=user.org_id,
    )
    db.add(cred)
    db.flush()
    audit(
        db,
        "connection.create",
        user=user,
        resource_type="connection",
        resource_id=cred.id,
        details={"name": cred.name, "type": cred.type, "visibility": cred.visibility},
        request=request,
    )
    db.refresh(cred)
    return _out(cred, user)


@router.put("/{cred_id}", response_model=CredentialOut)
def update_credential(
    cred_id: int,
    body: CredentialIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_reader),
):
    _require_creator(db, user)
    cred = _get(db, cred_id, user)
    if not _can_edit(user, cred):
        raise HTTPException(status_code=403, detail="Only the owner or an admin can change this connection")
    if body.type != cred.type:
        raise HTTPException(status_code=400, detail="The connection type cannot be changed")
    ctype = CREDENTIAL_TYPES[cred.type]
    cred.data_encrypted = encrypt_json(_checked(db, ctype, body.data, decrypt_json(cred.data_encrypted)))
    cred.name = body.name
    cred.visibility = body.visibility
    audit(
        db,
        "connection.update",
        user=user,
        resource_type="connection",
        resource_id=cred.id,
        details={"name": cred.name, "visibility": cred.visibility},
        request=request,
    )
    db.refresh(cred)
    return _out(cred, user)


@router.delete("/{cred_id}")
def delete_credential(cred_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_reader)):
    _require_creator(db, user)
    cred = _get(db, cred_id, user)
    if not _can_edit(user, cred):
        raise HTTPException(status_code=403, detail="Only the owner or an admin can delete this connection")
    db.delete(cred)
    audit(db, "connection.delete", user=user, resource_type="connection", resource_id=cred_id, request=request)
    return {"status": "deleted"}


def _uses(definition: dict, cred_id: int) -> bool:
    for n in (definition or {}).get("nodes") or []:
        cfg = ((n or {}).get("data") or {}).get("config") or {}
        if isinstance(cfg, dict) and str(cfg.get("credential_id", "")) == str(cred_id):
            return True
    notify = ((definition or {}).get("settings") or {}).get("notify_on_failure") or {}
    return isinstance(notify, dict) and str(notify.get("credential_id", "")) == str(cred_id)


@router.get("/{cred_id}/usage")
def usage(cred_id: int, db: Session = Depends(get_db), user: User = Depends(_reader)):
    """Automations (non-archived versions) that use this connection."""
    _get(db, cred_id, user)
    rows = db.query(Workflow).filter(Workflow.org_id == user.org_id, Workflow.status != "archived").all()
    return [
        {
            "id": w.id if can_view(user, w) else None,
            "name": w.name if can_view(user, w) else None,
            "status": w.status,
            "version": w.version,
            "visible": can_view(user, w),
        }
        for w in rows
        if _uses(w.definition, cred_id)
    ]


@router.post("/{cred_id}/test", response_model=CredentialTestOut)
def test_credential(cred_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_reader)):
    """Check a connection works: Slack/Teams get a short test message; email signs in to the server."""
    cred = _get(db, cred_id, user)
    if not _can_edit(user, cred):
        raise HTTPException(status_code=403, detail="Only the owner or an admin can test this connection")
    data = decrypt_json(cred.data_encrypted)
    ok, message = True, "Connected."
    try:
        if cred.type in ("slack_webhook", "teams_webhook"):
            safe_http.check_webhook_url(
                data["url"], "slack" if cred.type == "slack_webhook" else "teams", get_settings(db)
            )
            resp = safe_http.request(
                "POST",
                data["url"],
                get_settings(db),
                json_body={"text": "Star Dust test message: this connection works."},
                trusted_host=True,
                timeout=15,
            )
            ok = resp.status_code < 400
            message = "Test message sent." if ok else f"The service answered HTTP {resp.status_code}."
        elif cred.type == "smtp":
            safe_http.check_smtp_host(data["host"], int(data.get("port") or 587), get_settings(db))
            security = data.get("security") or "starttls"
            server_cls = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
            with server_cls(data["host"], int(data.get("port") or 587), timeout=15) as server:
                if security == "starttls":
                    server.starttls(context=ssl.create_default_context())
                if data.get("username"):
                    server.login(data["username"], data.get("password") or "")
            message = "Signed in to the email server."
        else:
            message = "Saved. This kind of connection is checked when a workflow uses it."
    except safe_http.BlockedRequest as exc:
        ok, message = False, str(exc)
    except smtplib.SMTPAuthenticationError:
        ok, message = False, "The email server rejected the username or password."
    except (OSError, smtplib.SMTPException, httpx.HTTPError):
        ok, message = False, "Could not reach the server. Check the server address and port."
    audit(
        db,
        "connection.test",
        user=user,
        resource_type="connection",
        resource_id=cred.id,
        status="success" if ok else "failure",
        request=request,
    )
    return CredentialTestOut(ok=ok, message=message)
