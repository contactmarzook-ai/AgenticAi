from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..crypto import decrypt_json, encrypt_json
from ..database import get_db
from ..models import Credential, User
from ..nodes import CREDENTIAL_TYPES
from ..rbac import ROLE_LEVEL, can_view, get_current_user
from ..schemas import CredentialIn, CredentialOut
from ..services.platform_settings import get_settings

router = APIRouter(prefix="/api/credentials", tags=["connections"])


def _require_creator(db: Session, user: User) -> None:
    min_role = get_settings(db).get("connections_min_role", "builder")
    if ROLE_LEVEL.get(user.role, -1) < ROLE_LEVEL.get(min_role, 99):
        raise HTTPException(status_code=403, detail=f"Only {min_role}s can manage connections")


def _can_edit(user: User, cred: Credential) -> bool:
    return user.role == "admin" or cred.owner_id == user.id


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
        if value not in (None, ""):
            result[f.key] = value
    return result


def _get(db: Session, cred_id: int, user: User) -> Credential:
    cred = db.get(Credential, cred_id)
    if cred is None or not can_view(user, cred):
        raise HTTPException(status_code=404, detail="Connection not found")
    return cred


@router.get("", response_model=list[CredentialOut])
def list_credentials(type: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Credential)
    if type:
        q = q.filter(Credential.type.in_(type.split("|")))
    return [_out(c, user) for c in q.order_by(Credential.name).all() if can_view(user, c)]


@router.post("", response_model=CredentialOut, status_code=201)
def create_credential(
    body: CredentialIn, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    _require_creator(db, user)
    ctype = CREDENTIAL_TYPES.get(body.type)
    if ctype is None:
        raise HTTPException(status_code=400, detail="Unknown connection type")
    cred = Credential(
        name=body.name,
        type=body.type,
        data_encrypted=encrypt_json(_clean(ctype, body.data)),
        visibility=body.visibility,
        department=user.department,
        owner_id=user.id,
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
    user: User = Depends(get_current_user),
):
    _require_creator(db, user)
    cred = _get(db, cred_id, user)
    if not _can_edit(user, cred):
        raise HTTPException(status_code=403, detail="Only the owner or an admin can change this connection")
    if body.type != cred.type:
        raise HTTPException(status_code=400, detail="The connection type cannot be changed")
    ctype = CREDENTIAL_TYPES[cred.type]
    cred.data_encrypted = encrypt_json(_clean(ctype, body.data, decrypt_json(cred.data_encrypted)))
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
def delete_credential(
    cred_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    cred = _get(db, cred_id, user)
    if not _can_edit(user, cred):
        raise HTTPException(status_code=403, detail="Only the owner or an admin can delete this connection")
    db.delete(cred)
    audit(db, "connection.delete", user=user, resource_type="connection", resource_id=cred_id, request=request)
    return {"status": "deleted"}
