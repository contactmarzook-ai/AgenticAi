"""Choosing an LLM model and checking that a user's role may use it."""

from typing import Optional

from sqlalchemy.orm import Session

from ..llm.client import ModelTarget, resolve_api_key
from ..models import LLMModel, LLMProvider


class ModelNotAvailable(Exception):
    pass


def default_model(db: Session) -> Optional[LLMModel]:
    q = db.query(LLMModel).join(LLMProvider).filter(LLMModel.is_active.is_(True), LLMProvider.is_active.is_(True))
    return q.filter(LLMModel.is_default.is_(True)).first() or q.order_by(LLMModel.id).first()


def role_may_use(model: LLMModel, role: str) -> bool:
    return not model.allowed_roles or role in model.allowed_roles or role == "admin"


def resolve_model(db: Session, model_id: Optional[int], role: str) -> LLMModel:
    model = db.get(LLMModel, model_id) if model_id else default_model(db)
    if model is None:
        raise ModelNotAvailable("No LLM model is configured. An administrator must add one under Models.")
    if not model.is_active or not model.provider.is_active:
        raise ModelNotAvailable(f"Model '{model.display_name}' is disabled.")
    if not role_may_use(model, role):
        raise ModelNotAvailable(f"Your role is not allowed to use model '{model.display_name}'.")
    return model


def to_target(model: LLMModel) -> ModelTarget:
    return ModelTarget(
        base_url=model.provider.base_url,
        model_name=model.model_name,
        api_key=resolve_api_key(model.provider.api_key_env),
        supports_tools=model.supports_tools,
    )
