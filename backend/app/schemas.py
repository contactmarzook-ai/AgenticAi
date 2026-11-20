from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["user", "builder", "admin"]
Visibility = Literal["public", "department", "private"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth / users ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORM):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    department: Optional[str]
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: datetime


class MeOut(UserOut):
    permissions: list[str] = []


class UserCreate(BaseModel):
    email: EmailStr
    full_name: Optional[str] = Field(default=None, max_length=255)
    password: str = Field(max_length=200)
    role: Role = "user"
    department: Optional[str] = Field(default=None, max_length=100)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    role: Optional[Role] = None
    department: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None


class PasswordReset(BaseModel):
    password: str = Field(max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


# ---------- models ----------
class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=500)
    api_key_env: Optional[str] = Field(default=None, max_length=100, pattern=r"^[A-Z_][A-Z0-9_]*$")
    is_active: bool = True

    @field_validator("base_url")
    @classmethod
    def http_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")


class ProviderOut(ORM):
    id: int
    name: str
    base_url: str
    api_key_env: Optional[str]
    is_active: bool
    created_at: datetime


class ModelIn(BaseModel):
    provider_id: int
    model_name: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    supports_tools: bool = True
    is_default: bool = False
    is_active: bool = True
    allowed_roles: list[Role] = []


class ModelOut(ORM):
    id: int
    provider_id: int
    model_name: str
    display_name: str
    supports_tools: bool
    is_default: bool
    is_active: bool
    allowed_roles: list[str]


# ---------- tools ----------
class ToolOut(BaseModel):
    name: str
    description: str
    parameters: dict
    min_role: str


# ---------- agents ----------
class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    system_prompt: str = Field(default="", max_length=20000)
    model_id: Optional[int] = None
    tools: list[str] = []
    trigger_keywords: Optional[str] = Field(default=None, max_length=500)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_steps: int = Field(default=6, ge=1, le=50)
    visibility: Visibility = "department"
    department: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = True


class AgentOut(ORM):
    id: int
    name: str
    description: Optional[str]
    system_prompt: str
    model_id: Optional[int]
    tools: list[str]
    trigger_keywords: Optional[str]
    temperature: float
    max_steps: int
    visibility: str
    department: Optional[str]
    is_active: bool
    owner_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False


def _no_nul(v: str) -> str:
    # PostgreSQL text columns cannot store NUL characters.
    return v.replace("\x00", "")


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1)
    _clean = field_validator("message")(classmethod(lambda cls, v: _no_nul(v)))


# ---------- workflows ----------
class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    definition: dict = Field(default_factory=lambda: {"nodes": [], "edges": []})
    trigger_keywords: Optional[str] = Field(default=None, max_length=500)
    visibility: Visibility = "department"
    department: Optional[str] = Field(default=None, max_length=100)
    # Set to save a new version of an existing workflow.
    group_id: Optional[str] = Field(default=None, max_length=32)


class WorkflowOut(ORM):
    id: int
    group_id: str
    version: int
    name: str
    description: Optional[str]
    status: str
    definition: dict
    trigger_keywords: Optional[str]
    visibility: str
    department: Optional[str]
    owner_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False


class WorkflowRunRequest(BaseModel):
    input: dict[str, Any] = {}


class ValidationOut(BaseModel):
    is_valid: bool
    errors: list[str]


# ---------- runs ----------
class RunOut(ORM):
    id: int
    target_type: str
    target_id: int
    target_name: str
    source: str
    status: str
    input: dict
    output: Optional[dict]
    steps: list
    error: Optional[str]
    model_name: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    llm_calls: int
    user_id: Optional[int]
    trigger_id: Optional[int]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class RunSummary(ORM):
    id: int
    target_type: str
    target_id: int
    target_name: str
    source: str
    status: str
    error: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    user_id: Optional[int]
    created_at: datetime
    finished_at: Optional[datetime]


# ---------- triggers ----------
class TriggerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    workflow_group_id: str = Field(max_length=32)
    type: Literal["schedule", "webhook"]
    cron: Optional[str] = Field(default=None, max_length=100)
    timezone: str = Field(default="UTC", max_length=64)
    input: dict[str, Any] = {}
    is_enabled: bool = True


class TriggerOut(ORM):
    id: int
    name: str
    workflow_group_id: str
    type: str
    cron: Optional[str]
    timezone: str
    input: dict
    is_enabled: bool
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    owner_id: Optional[int]
    created_at: datetime


class TriggerCreated(TriggerOut):
    webhook_token: Optional[str] = None  # returned once, on creation / rotation only


# ---------- chat ----------
class ChatSessionIn(BaseModel):
    title: str = Field(default="New Chat", max_length=200)
    agent_id: Optional[int] = None


class ChatSessionOut(ORM):
    id: int
    title: str
    agent_id: Optional[int]
    created_at: datetime
    updated_at: datetime


class ChatMessageOut(ORM):
    id: int
    session_id: int
    role: str
    content: str
    run_id: Optional[int]
    metadata_json: Optional[dict]
    created_at: datetime


class ChatSend(BaseModel):
    message: str = Field(min_length=1)
    _clean = field_validator("message")(classmethod(lambda cls, v: _no_nul(v)))


# ---------- audit ----------
class AuditOut(ORM):
    id: int
    user_id: Optional[int]
    user_email: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    status: str
    details: Optional[dict]
    ip_address: Optional[str]
    request_id: Optional[str]
    created_at: datetime


class Page(BaseModel):
    items: list[Any]
    total: int


# ---------- node catalog / connections / settings ----------
class CredentialIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(max_length=50)
    # Field values. On update, omitted or empty secret fields keep their saved value.
    data: dict[str, Any] = {}
    visibility: Visibility = "private"


class CredentialOut(ORM):
    id: int
    name: str
    type: str
    visibility: str
    department: Optional[str]
    owner_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    # Non-secret field values only; secrets are never returned.
    public_data: dict = {}
    can_edit: bool = False


class SettingsIn(BaseModel):
    disabled_nodes: Optional[list[str]] = None
    http_allowed_hosts: Optional[list[str]] = None
    allow_private_network: Optional[bool] = None
    connections_min_role: Optional[Literal["builder", "admin"]] = None
    ai_builder_enabled: Optional[bool] = None
    max_wait_seconds: Optional[int] = Field(default=None, ge=0, le=3600)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=4000)
    _clean = field_validator("prompt")(classmethod(lambda cls, v: _no_nul(v)))
