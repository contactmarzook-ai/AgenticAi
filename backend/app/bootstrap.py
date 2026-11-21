"""First-run seeding. Idempotent: only acts on empty tables."""

import logging

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .models import DEFAULT_ORG_ID, LLMModel, LLMProvider, Organization, User
from .security import hash_password, password_problems

logger = logging.getLogger("agentos.bootstrap")


def seed(db: Session) -> None:
    """Safe to run concurrently from several workers/pods: a lost race is ignored."""
    try:
        _seed(db)
    except IntegrityError:
        db.rollback()
        logger.info("Seed data was created concurrently by another process")


def _seed(db: Session) -> None:
    if db.query(Organization).count() == 0:
        db.add(Organization(id=DEFAULT_ORG_ID, name="Default organization", slug="default"))
        db.flush()
        if db.get_bind().dialect.name == "postgresql":
            # The id was set explicitly, so move the sequence past it.
            db.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('organizations', 'id'), (SELECT MAX(id) FROM organizations))"
                )
            )
        db.commit()

    if db.query(User).count() == 0:
        email, password = settings.bootstrap_admin_email.strip().lower(), settings.bootstrap_admin_password
        if email and password:
            problems = password_problems(password)
            if problems:
                raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD " + "; ".join(problems))
            db.add(
                User(
                    email=email,
                    full_name="Administrator",
                    role="platform_admin",
                    org_id=DEFAULT_ORG_ID,
                    password_hash=hash_password(password),
                )
            )
            db.commit()
            logger.info("Created bootstrap admin %s", email)
        else:
            logger.warning(
                "No users exist. Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD to create the first admin."
            )

    if db.query(LLMProvider).count() == 0 and settings.llm_base_url:
        provider = LLMProvider(
            name="default",
            base_url=settings.llm_base_url.rstrip("/"),
            api_key_env=settings.llm_api_key_env if settings.llm_api_key_env.startswith("LLM_KEY_") else None,
        )
        db.add(provider)
        db.flush()
        db.add(
            LLMModel(
                provider_id=provider.id,
                model_name=settings.llm_default_model,
                display_name=settings.llm_default_model,
                supports_tools=True,
                is_default=True,
            )
        )
        db.commit()
        logger.info("Seeded default LLM provider %s with model %s", provider.base_url, settings.llm_default_model)
