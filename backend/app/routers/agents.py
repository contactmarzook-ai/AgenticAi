import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import contracts
from ..audit import audit
from ..config import settings
from ..database import get_db
from ..models import Agent, LLMModel, Run, User
from ..rbac import can_edit, can_view, is_admin, require_permission, role_level, visible_filter
from ..schemas import AgentIn, AgentOut, AgentRunRequest, ContractCheckIn, RunOut, SchemaCheckIn
from ..services.agent_runtime import ContractError, check_input, effective_capabilities
from ..services.models_service import role_may_use
from ..services.runs import create_run, enforce_rate_limit, execute_run
from ..tools.registry import canonical, get_tool

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _out(agent: Agent, user: User) -> AgentOut:
    out = AgentOut.model_validate(agent)
    out.input_schema = agent.input_schema or contracts.DEFAULT_INPUT_SCHEMA
    out.output_schema = agent.output_schema or contracts.DEFAULT_OUTPUT_SCHEMA
    out.effective_capabilities = effective_capabilities(agent)
    out.can_edit = can_edit(user, agent)
    return out


def _contract(schema: dict | None, default: dict, which: str) -> dict:
    if schema is None:
        return dict(default)
    problems = contracts.schema_problems(schema)
    if problems:
        raise HTTPException(status_code=400, detail={"message": f"The {which} schema is not valid", "errors": problems})
    return contracts.normalize(schema)


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
    body.input_schema = _contract(body.input_schema, contracts.DEFAULT_INPUT_SCHEMA, "input")
    body.output_schema = _contract(body.output_schema, contracts.DEFAULT_OUTPUT_SCHEMA, "output")
    body.capabilities = sorted(set(body.capabilities))
    body.tags = sorted(set(body.tags))
    body.tools = list(dict.fromkeys(canonical(n) for n in body.tools))  # store current names
    for name in body.tools:
        t = get_tool(name)
        if t is None:
            raise HTTPException(status_code=400, detail=f"Unknown tool '{name}'")
        if role_level(t.min_role) > role_level(user.role):
            raise HTTPException(status_code=403, detail=f"Your role may not attach tool '{name}'")


def _department(body: AgentIn, user: User):
    # Only admins may place a resource in a department other than their own.
    return (body.department or None) if is_admin(user) else user.department


@router.get("", response_model=list[AgentOut])
def list_agents(
    include_inactive: bool = False,
    capability: Optional[str] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent:read")),
):
    """Agents the caller can see; filter by a capability (declared or derived) and/or a tag."""
    q = visible_filter(db.query(Agent), Agent, user)
    if not include_inactive:
        q = q.filter(Agent.is_active.is_(True))
    out = [_out(a, user) for a in q.order_by(Agent.name).all()]
    if capability:
        out = [a for a in out if capability in a.effective_capabilities]
    if tag:
        out = [a for a in out if tag in a.tags]
    return out


@router.get("/contract-defaults")
def contract_defaults(_: User = Depends(require_permission("agent:read"))):
    """The default contract ({message} -> {answer}) every agent starts with."""
    return {"input_schema": contracts.DEFAULT_INPUT_SCHEMA, "output_schema": contracts.DEFAULT_OUTPUT_SCHEMA}


@router.post("/check-schema")
def check_schema(body: SchemaCheckIn, _: User = Depends(require_permission("agent:write"))):
    """Check a contract schema (the editor calls this; the same check runs on save)."""
    problems = contracts.schema_problems(body.schema_)
    return {
        "valid": not problems,
        "problems": problems,
        "schema": contracts.normalize(body.schema_) if not problems else None,
    }


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
    agent = Agent(**data, owner_id=user.id, org_id=user.org_id)
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


@router.post("/{agent_id}/check")
def check_contract(
    agent_id: int,
    body: ContractCheckIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent:read")),
):
    """Validate an input (and/or an output) against the agent's contract without running it."""
    agent = _get_visible(db, agent_id, user)
    result = {}
    if body.input is not None:
        value, errors = contracts.validate(agent.input_schema or contracts.DEFAULT_INPUT_SCHEMA, body.input)
        result["input"] = {"valid": not errors, "errors": errors, "value": value}
    if body.output is not None:
        value, errors = contracts.validate(agent.output_schema or contracts.DEFAULT_OUTPUT_SCHEMA, body.output)
        result["output"] = {"valid": not errors, "errors": errors, "value": value}
    return result


@router.post("/{agent_id}/run", response_model=RunOut)
def run_agent_endpoint(
    agent_id: int,
    body: AgentRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent:run")),
):
    """Run an agent synchronously and return the finished run (output, steps, token usage).

    The input is validated against the agent's input schema first: invalid input is rejected
    with 422 and the list of problems, and nothing runs."""
    agent = _get_visible(db, agent_id, user)
    if not agent.is_active:
        raise HTTPException(status_code=409, detail="Agent is disabled")
    raw = body.input if body.input is not None else ({"message": body.message} if body.message is not None else {})
    if len(json.dumps(raw, default=str)) > settings.max_message_chars:
        raise HTTPException(status_code=413, detail=f"Input longer than {settings.max_message_chars} characters")
    try:
        value = check_input(agent, raw)
    except ContractError as exc:
        audit(
            db,
            "agent.run",
            user=user,
            resource_type="agent",
            resource_id=agent.id,
            status="failure",
            details={"stage": "input", "errors": exc.errors[:10]},
            request=request,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "message": "The input does not match this agent's input schema",
                "errors": [contracts.format_errors([e]) for e in exc.errors],
                "fields": exc.errors,
            },
        ) from None
    enforce_rate_limit(db, user)
    run = create_run(db, target=agent, user=user, source="api", input_data={"input": value})
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
