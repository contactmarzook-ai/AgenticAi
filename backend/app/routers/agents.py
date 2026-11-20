from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..database import get_db
from ..models import Agent, LLMModel, Run, User
from ..rbac import ROLE_LEVEL, can_edit, can_view, require_permission
from ..schemas import AgentIn, AgentOut, AgentRunRequest, RunOut
from ..services.models_service import role_may_use
from ..services.runs import create_run, enforce_rate_limit, execute_run
from ..tools.registry import get_tool

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _out(agent: Agent, user: User) -> AgentOut:
    out = AgentOut.model_validate(agent)
    out.can_edit = can_edit(user, agent)
    return out


def _get_visible(db: Session, agent_id: int, user: User) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None or not can_view(user, agent):
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _validate(db: Session, body: AgentIn, user: User) -> None:
    if body.model_id is not None:
        model = db.get(LLMModel, body.model_id)
        if model is None or not model.is_active:
            raise HTTPException(status_code=400, detail="Selected model does not exist or is disabled")
        if not role_may_use(model, user.role):
            raise HTTPException(status_code=403, detail="Your role may not use the selected model")
        if body.tools and not model.supports_tools:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{model.display_name}' does not support tool calling; remove the tools or pick another model",
            )
    for name in body.tools:
        t = get_tool(name)
        if t is None:
            raise HTTPException(status_code=400, detail=f"Unknown tool '{name}'")
        if ROLE_LEVEL.get(t.min_role, 99) > ROLE_LEVEL[user.role]:
            raise HTTPException(status_code=403, detail=f"Your role may not attach tool '{name}'")


def _department(body: AgentIn, user: User):
    # Only admins may place a resource in a department other than their own.
    return (body.department or None) if user.role == "admin" else user.department


@router.get("", response_model=list[AgentOut])
def list_agents(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent:read")),
):
    q = db.query(Agent)
    if not include_inactive:
        q = q.filter(Agent.is_active.is_(True))
    return [_out(a, user) for a in q.order_by(Agent.name).all() if can_view(user, a)]


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("agent:read"))):
    return _out(_get_visible(db, agent_id, user), user)


@router.post("", response_model=AgentOut, status_code=201)
def create_agent(
    body: AgentIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent:write")),
):
    _validate(db, body, user)
    data = body.model_dump()
    data["department"] = _department(body, user)
    agent = Agent(**data, owner_id=user.id)
    db.add(agent)
    db.flush()
    audit(
        db,
        "agent.create",
        user=user,
        resource_type="agent",
        resource_id=agent.id,
        details={"name": agent.name, "tools": agent.tools, "model_id": agent.model_id, "visibility": agent.visibility},
        request=request,
    )
    db.refresh(agent)
    return _out(agent, user)


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: int,
    body: AgentIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent:write")),
):
    agent = _get_visible(db, agent_id, user)
    if not can_edit(user, agent):
        raise HTTPException(status_code=403, detail="You cannot edit this agent")
    _validate(db, body, user)
    data = body.model_dump()
    data["department"] = _department(body, user)
    changed = {k: v for k, v in data.items() if getattr(agent, k) != v}
    for k, v in data.items():
        setattr(agent, k, v)
    audit(
        db,
        "agent.update",
        user=user,
        resource_type="agent",
        resource_id=agent.id,
        details={"changed": sorted(changed)},
        request=request,
    )
    db.refresh(agent)
    return _out(agent, user)


@router.delete("/{agent_id}")
def disable_agent(
    agent_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent:write")),
):
    """Agents are disabled, not deleted, so run history and audit references stay meaningful."""
    agent = _get_visible(db, agent_id, user)
    if not can_edit(user, agent):
        raise HTTPException(status_code=403, detail="You cannot edit this agent")
    agent.is_active = False
    audit(db, "agent.disable", user=user, resource_type="agent", resource_id=agent.id, request=request)
    return {"status": "disabled"}


@router.post("/{agent_id}/run", response_model=RunOut)
def run_agent_endpoint(
    agent_id: int,
    body: AgentRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent:run")),
):
    """Run an agent synchronously and return the finished run (answer, steps, token usage)."""
    if len(body.message) > settings.max_message_chars:
        raise HTTPException(status_code=413, detail=f"Message longer than {settings.max_message_chars} characters")
    agent = _get_visible(db, agent_id, user)
    if not agent.is_active:
        raise HTTPException(status_code=409, detail="Agent is disabled")
    enforce_rate_limit(db, user)
    run = create_run(db, target=agent, user=user, source="api", input_data={"message": body.message})
    execute_run(run.id)
    db.expire_all()
    run = db.get(Run, run.id)
    audit(
        db,
        "agent.run",
        user=user,
        resource_type="agent",
        resource_id=agent.id,
        status="success" if run.status == "succeeded" else "failure",
        details={"run_id": run.id},
        request=request,
    )
    return run
