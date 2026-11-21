from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..database import get_db
from ..llm.client import LLMError, get_llm_client
from ..models import Agent, LLMModel, LLMProvider, User
from ..rbac import has_permission, require_permission
from ..schemas import ModelIn, ModelOut, ProviderIn, ProviderOut
from ..services.models_service import role_may_use, to_target

router = APIRouter(prefix="/api/models", tags=["models"])
manage = require_permission("model:manage")
read = require_permission("model:read")


@router.get("", response_model=list[ModelOut])
def list_models(db: Session = Depends(get_db), user: User = Depends(read)):
    """Models the caller may assign to agents (active + allowed for their role)."""
    models = db.query(LLMModel).join(LLMProvider).order_by(LLMModel.display_name).all()
    if has_permission(user, "model:manage"):
        return models
    return [m for m in models if m.is_active and m.provider.is_active and role_may_use(m, user.role)]


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db), _: User = Depends(manage)):
    return db.query(LLMProvider).order_by(LLMProvider.name).all()


@router.post("/providers", response_model=ProviderOut, status_code=201)
def create_provider(body: ProviderIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(manage)):
    if db.query(LLMProvider).filter(LLMProvider.name == body.name).first():
        raise HTTPException(status_code=409, detail="Provider name already exists")
    provider = LLMProvider(**body.model_dump())
    db.add(provider)
    db.flush()
    audit(
        db,
        "model.provider_create",
        user=admin,
        resource_type="llm_provider",
        resource_id=provider.id,
        details=body.model_dump(),
        request=request,
    )
    db.refresh(provider)
    return provider


@router.put("/providers/{provider_id}", response_model=ProviderOut)
def update_provider(
    provider_id: int, body: ProviderIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(manage)
):
    provider = db.get(LLMProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    for k, v in body.model_dump().items():
        setattr(provider, k, v)
    try:
        audit(
            db,
            "model.provider_update",
            user=admin,
            resource_type="llm_provider",
            resource_id=provider.id,
            details=body.model_dump(),
            request=request,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Provider name already exists")
    db.refresh(provider)
    return provider


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(manage)):
    provider = db.get(LLMProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    model_ids = [m.id for m in provider.models]
    if model_ids and db.query(Agent).filter(Agent.model_id.in_(model_ids)).count():
        raise HTTPException(
            status_code=409,
            detail="Agents still use models from this provider. Disable it instead, or move the agents first.",
        )
    db.delete(provider)
    audit(
        db, "model.provider_delete", user=admin, resource_type="llm_provider", resource_id=provider_id, request=request
    )
    return {"status": "deleted"}


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(manage)):
    """Send a tiny prompt to the provider's first model to check connectivity."""
    provider = db.get(LLMProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    if not provider.models:
        raise HTTPException(status_code=400, detail="Add a model to this provider first")
    model = provider.models[0]
    try:
        resp = get_llm_client().chat(
            to_target(model), [{"role": "user", "content": "Reply with the word OK."}], temperature=0
        )
        result = {"ok": True, "model": model.model_name, "reply": resp.content[:200]}
    except LLMError as exc:
        result = {"ok": False, "model": model.model_name, "error": str(exc)}
    audit(
        db,
        "model.provider_test",
        user=admin,
        resource_type="llm_provider",
        resource_id=provider_id,
        status="success" if result["ok"] else "failure",
        request=request,
    )
    return result


def _apply_default(db: Session, model: LLMModel) -> None:
    if model.is_default:
        db.query(LLMModel).filter(LLMModel.id != model.id).update({LLMModel.is_default: False})


@router.post("", response_model=ModelOut, status_code=201)
def create_model(body: ModelIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(manage)):
    if db.get(LLMProvider, body.provider_id) is None:
        raise HTTPException(status_code=400, detail="Provider not found")
    model = LLMModel(**body.model_dump())
    db.add(model)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This model already exists for the provider")
    _apply_default(db, model)
    audit(
        db,
        "model.create",
        user=admin,
        resource_type="llm_model",
        resource_id=model.id,
        details=body.model_dump(),
        request=request,
    )
    db.refresh(model)
    return model


@router.put("/{model_id}", response_model=ModelOut)
def update_model(
    model_id: int, body: ModelIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(manage)
):
    model = db.get(LLMModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    for k, v in body.model_dump().items():
        setattr(model, k, v)
    _apply_default(db, model)
    try:
        audit(
            db,
            "model.update",
            user=admin,
            resource_type="llm_model",
            resource_id=model.id,
            details=body.model_dump(),
            request=request,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This model already exists for the provider")
    db.refresh(model)
    return model


@router.delete("/{model_id}")
def delete_model(model_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(manage)):
    model = db.get(LLMModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    if db.query(Agent).filter(Agent.model_id == model_id).count():
        raise HTTPException(
            status_code=409, detail="Agents still use this model. Disable it instead, or move the agents first."
        )
    db.delete(model)
    audit(db, "model.delete", user=admin, resource_type="llm_model", resource_id=model_id, request=request)
    return {"status": "deleted"}
