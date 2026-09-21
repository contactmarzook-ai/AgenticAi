from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Any, Dict
from datetime import datetime

class UserBase(BaseModel):
    email: str
    full_name: Optional[str] = None
    role: str = "user"
    tenant_org_id: Optional[str] = None

class UserCreate(UserBase):
    pass

class UserSchema(UserBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatMessageBase(BaseModel):
    role: str
    content: str
    metadata_json: Optional[Dict[str, Any]] = None

class ChatMessageCreate(ChatMessageBase):
    pass

class ChatMessageSchema(ChatMessageBase):
    id: int
    session_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionBase(BaseModel):
    title: str = "New Chat"

class ChatSessionCreate(ChatSessionBase):
    pass

class ChatSessionSchema(ChatSessionBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessageSchema] = []

    model_config = ConfigDict(from_attributes=True)


class AgentBase(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_keywords: Optional[str] = None
    handler: str
    input_schema: Optional[Dict[str, Any]] = None
    is_active: bool = True

class AgentCreate(AgentBase):
    pass

class AgentSchema(AgentBase):
    id: int
    created_by: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowBase(BaseModel):
    name: str
    description: Optional[str] = None
    group_id: Optional[str] = None
    definition: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    status: str = "draft"
    version: int = 1

class WorkflowCreate(WorkflowBase):
    pass

class WorkflowSchema(WorkflowBase):
    id: int
    user_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
