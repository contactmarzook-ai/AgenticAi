import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .contracts import DEFAULT_INPUT_SCHEMA, DEFAULT_OUTPUT_SCHEMA
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_ORG_ID = 1


class Organization(Base):
    """A tenant. Every user and every agent, workflow, run, trigger and connection belongs to one."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def _org_fk():
    # No default on purpose: code that forgets to set the organization fails instead of silently
    # putting the record in some tenant.
    return mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # platform_admin | org_admin | developer | operator | viewer | auditor (see rbac.py)
    role: Mapped[str] = mapped_column(String(32), default="operator")
    # Fixed at creation: a user never moves between organizations.
    org_id: Mapped[int] = _org_fk()
    # How the user signs in: "local" (password) or "oidc" (Microsoft Entra ID); oidc_subject is the IdP's id.
    auth_provider: Mapped[str] = mapped_column(String(20), default="local", server_default="local")
    oidc_subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Bumped on password change / deactivation so existing tokens stop working.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LLMProvider(Base):
    """An OpenAI-compatible endpoint (Ollama, vLLM, LM Studio, a hosted API...)."""

    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    # Name of the environment variable holding the API key. Secrets never live in the DB.
    api_key_env: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    models: Mapped[List["LLMModel"]] = relationship(back_populates="provider", cascade="all, delete-orphan")


class LLMModel(Base):
    __tablename__ = "llm_models"
    __table_args__ = (UniqueConstraint("provider_id", "model_name", name="uq_llm_model_provider_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("llm_providers.id", ondelete="CASCADE"))
    model_name: Mapped[str] = mapped_column(String(200))  # name sent to the API, e.g. "qwen2.5:7b-instruct"
    display_name: Mapped[str] = mapped_column(String(200))
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Roles allowed to use this model. Empty list = every role.
    allowed_roles: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    provider: Mapped[LLMProvider] = relationship(back_populates="models")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = _org_fk()
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    model_id: Mapped[Optional[int]] = mapped_column(ForeignKey("llm_models.id", ondelete="SET NULL"), nullable=True)
    tools: Mapped[list] = mapped_column(JSON, default=list)  # names from the tool registry
    # Contract (JSON Schema, see contracts.py). Every agent has one; the defaults are
    # {message: string} -> {answer: string}.
    input_schema: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_INPUT_SCHEMA))
    output_schema: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_OUTPUT_SCHEMA))
    # Discovery metadata: what the agent can do (e.g. "invoice.extract") and free labels.
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    trigger_keywords: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    max_steps: Mapped[int] = mapped_column(Integer, default=6)
    visibility: Mapped[str] = mapped_column(String(20), default="department")  # public | department | private
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    model: Mapped[Optional[LLMModel]] = relationship()


class Workflow(Base):
    """One version of a workflow. Versions of the same workflow share `group_id`."""

    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("group_id", "version", name="uq_workflow_group_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = _org_fk()
    group_id: Mapped[str] = mapped_column(String(32), index=True, default=lambda: uuid.uuid4().hex)
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # draft | active (= the published version that runs) | archived. A version is immutable once
    # published (published_at is set); archived versions with published_at can still be run explicitly.
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    definition: Mapped[dict] = mapped_column(JSON, default=dict)  # {"nodes": [...], "edges": [...]}
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    trigger_keywords: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), default="department")
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Run(Base):
    """A single execution of an agent or workflow (from chat, the API, a schedule or a webhook)."""

    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_target", "target_type", "target_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = _org_fk()
    target_type: Mapped[str] = mapped_column(String(20))  # agent | workflow
    target_id: Mapped[int] = mapped_column(Integer)
    target_name: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(20), default="api")  # chat | api | test | schedule | webhook
    status: Mapped[str] = mapped_column(
        String(20), default="queued", index=True
    )  # queued | running | succeeded | failed | cancelled
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trigger_id: Mapped[Optional[int]] = mapped_column(ForeignKey("triggers.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Durable execution: the worker holding the run renews heartbeat_at; a run whose heartbeat
    # stopped (pod restarted) is taken over and resumed from its saved step results.
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resume_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    nodes: Mapped[List["RunNode"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunNode.seq", passive_deletes=True
    )


class RunNode(Base):
    """One step of a workflow run: its state, data, error, attempts and timing (the checkpoint)."""

    __tablename__ = "run_nodes"
    __table_args__ = (UniqueConstraint("run_id", "node_id", name="uq_run_node"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(String(100))
    seq: Mapped[int] = mapped_column(Integer, default=0)  # position in dependency order
    type: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(200), default="")
    action: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending|running|success|failed|skipped|cancelled
    continued: Mapped[bool] = mapped_column(Boolean, default=False)  # failed but "continue on error"
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    input: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    output: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logs: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[Run] = relationship(back_populates="nodes")


class Trigger(Base):
    """Starts an active workflow on a cron schedule or from an authenticated webhook."""

    __tablename__ = "triggers"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = _org_fk()
    name: Mapped[str] = mapped_column(String(200))
    workflow_group_id: Mapped[str] = mapped_column(String(32), index=True)  # always runs the active version
    type: Mapped[str] = mapped_column(String(20))  # schedule | webhook | form
    cron: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    webhook_token_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Public form options: {"title", "intro", "success_message", "show_result"}
    options: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New Chat")
    agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[List["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.id"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)  # e.g. "agent.create", "auth.login_failed"
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success")  # success | failure | denied
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Credential(Base):
    """A saved connection (SMTP account, Slack webhook, API key...). Secrets are encrypted at rest."""

    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = _org_fk()
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(50), index=True)
    data_encrypted: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(20), default="private")  # private | department | public
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PlatformSetting(Base):
    """Admin-controlled platform settings (one JSON document per key)."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuthSession(Base):
    """A signed-in session. Holds the (hashed) refresh token; access tokens carry its id (`sid`)."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # The previous refresh token: presenting it again means it was stolen, so the session is revoked.
    prev_refresh_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    method: Mapped[str] = mapped_column(String(20), default="password")  # password | oidc
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
