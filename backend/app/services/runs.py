"""Creating and executing runs of agents and workflows.

Runs execute either inline (chat, where the user waits for the answer) or on a
small in-process thread pool (API / schedule / webhook), with status polled via
GET /api/runs/{id}. All state lives in the database, so any API replica can serve
the status call.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..crypto import decrypt_json
from ..database import SessionLocal
from ..llm.client import LLMError, get_llm_client
from ..models import Agent, Credential, Run, User, Workflow
from ..nodes import NodeContext, NodeError, get_node_type
from ..rbac import can_view
from ..tools import registry
from .agent_runtime import AgentRunError, run_agent
from .models_service import ModelNotAvailable, resolve_model, to_target
from .platform_settings import get_settings
from .workflow_engine import WorkflowError, run_definition

logger = logging.getLogger("agentos.runs")
_pool = ThreadPoolExecutor(max_workers=settings.run_worker_threads, thread_name_prefix="run")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enforce_concurrency(db: Session, user: User) -> None:
    cap = settings.user_max_concurrent_runs
    if cap <= 0:
        return
    active = db.query(Run).filter(Run.user_id == user.id, Run.status.in_(["queued", "running"])).count()
    if active >= cap:
        raise HTTPException(
            status_code=429, detail=f"You already have {active} runs in progress; wait for one to finish"
        )


def enforce_rate_limit(db: Session, user: User) -> None:
    enforce_concurrency(db, user)
    limit = settings.user_runs_per_minute
    if limit <= 0:
        return
    since = utcnow() - timedelta(minutes=1)
    count = db.query(Run).filter(Run.user_id == user.id, Run.created_at >= since).count()
    if count >= limit:
        raise HTTPException(status_code=429, detail=f"Rate limit: at most {limit} runs per minute")


def create_run(
    db: Session,
    *,
    target: Agent | Workflow,
    user: Optional[User],
    source: str,
    input_data: dict,
    trigger_id: Optional[int] = None,
) -> Run:
    run = Run(
        target_type="agent" if isinstance(target, Agent) else "workflow",
        target_id=target.id,
        target_name=target.name,
        source=source,
        status="queued",
        input=input_data,
        user_id=user.id if user else None,
        trigger_id=trigger_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _history_for(input_data: dict) -> list[dict]:
    hist = input_data.get("history") or []
    return [m for m in hist if isinstance(m, dict) and m.get("role") in ("user", "assistant")]


def _ask_llm_factory(db: Session, role: str, usage: dict):
    def ask_llm(messages: list[dict], json_mode: bool = False, model_id: Optional[int] = None) -> dict:
        try:
            model = resolve_model(db, model_id, role)
            resp = get_llm_client().chat(to_target(model), messages, temperature=0.2, json_mode=json_mode)
        except (ModelNotAvailable, LLMError) as exc:
            raise NodeError(str(exc)) from exc
        usage["prompt"] += resp.prompt_tokens
        usage["completion"] += resp.completion_tokens
        usage["calls"] += 1
        usage["model"] = model.model_name
        return {"text": resp.content}

    return ask_llm


def _execute(db: Session, run: Run, usage: dict) -> None:
    user = db.get(User, run.user_id) if run.user_id else None
    role = user.role if user and user.is_active else "user"

    if run.target_type == "agent":
        agent = db.get(Agent, run.target_id)
        if agent is None:
            raise AgentRunError("Agent no longer exists")
        res = run_agent(db, agent, str(run.input.get("message", "")), role, history=_history_for(run.input))
        run.output = {"answer": res.answer}
        run.steps = res.steps
        usage.update(
            prompt=res.prompt_tokens, completion=res.completion_tokens, calls=res.llm_calls, model=res.model_name
        )
        return

    wf = db.get(Workflow, run.target_id)
    if wf is None:
        raise WorkflowError("Workflow no longer exists")
    # Agents and connections are used with the workflow OWNER's access: whoever runs a shared
    # workflow can only reach what its author was allowed to use.
    owner = db.get(User, wf.owner_id) if wf.owner_id else None
    if owner is not None and not owner.is_active:
        owner = None

    def call_agent(agent_id: int, message: str) -> dict:
        agent = db.get(Agent, agent_id)
        if agent is None or owner is None or not can_view(owner, agent):
            raise NodeError("This agent is not available to the workflow's owner")
        try:
            res = run_agent(db, agent, message, role)
        except AgentRunError as exc:
            raise NodeError(str(exc)) from exc
        usage["prompt"] += res.prompt_tokens
        usage["completion"] += res.completion_tokens
        usage["calls"] += res.llm_calls
        usage["model"] = res.model_name
        return {"answer": res.answer, "agent": agent.name}

    def get_credential(cred_id, expected_type: str) -> dict:
        try:
            cred = db.get(Credential, int(cred_id))
        except (TypeError, ValueError):
            cred = None
        if cred is None or owner is None or not can_view(owner, cred):
            raise NodeError("The selected connection is missing or not shared with the workflow's owner")
        if cred.type != expected_type:
            raise NodeError(f"The selected connection is not of type {expected_type}")
        try:
            return decrypt_json(cred.data_encrypted)
        except ValueError as exc:
            raise NodeError(str(exc)) from exc

    platform = get_settings(db)
    ctx = NodeContext(
        role=role,
        get_credential=get_credential,
        ask_llm=_ask_llm_factory(db, role, usage),
        run_agent=call_agent,
        settings=platform,
    )
    disabled = set(platform.get("disabled_nodes") or [])

    def call_action(key: str, config: dict, node: dict):
        ntype = get_node_type(key)
        if ntype is None:
            raise NodeError(f"Unknown step '{key}'")
        if key in disabled:
            raise NodeError(f"'{ntype.name}' steps are disabled by your administrator")
        values = {f.key: config.get(f.key, f.default) for f in ntype.fields}
        return ntype.handler(values, ctx)

    def call_tool(name: str, args: dict):
        try:
            return registry.execute(name, args)
        except registry.ToolError as exc:
            raise NodeError(str(exc)) from exc

    res = run_definition(wf.definition or {}, run.input or {}, call_agent, call_tool, call_action)
    run.output = {"result": res["output"]}
    run.steps = res["steps"]


def execute_run(run_id: int) -> None:
    """Execute a queued run in its own DB session. Never raises."""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None or run.status != "queued":
            return
        run.status = "running"
        run.started_at = utcnow()
        db.commit()
        usage = {"prompt": 0, "completion": 0, "calls": 0, "model": None}
        try:
            _execute(db, run, usage)
            run.status = "succeeded"
        except (AgentRunError, WorkflowError) as exc:
            db.rollback()
            run = db.get(Run, run_id)
            run.status = "failed"
            run.error = str(exc)
            if isinstance(exc, WorkflowError) and exc.steps:
                run.steps = exc.steps
        except Exception as exc:  # unexpected bug: record it, don't leak a traceback to users
            logger.exception("Run %s crashed", run_id)
            db.rollback()
            run = db.get(Run, run_id)
            run.status = "failed"
            run.error = f"Internal error ({exc.__class__.__name__})"
        run.prompt_tokens, run.completion_tokens, run.llm_calls = usage["prompt"], usage["completion"], usage["calls"]
        run.model_name = usage["model"]
        run.finished_at = utcnow()
        db.commit()
        if run.status == "failed":
            from .notify import notify_failure

            notify_failure(db, run)
    finally:
        db.close()


def submit_run(run_id: int) -> None:
    _pool.submit(execute_run, run_id)


def fail_stale_runs(db: Session) -> int:
    """Runs left 'running' or 'queued' by a crashed/restarted pod are marked failed."""
    cutoff = utcnow() - timedelta(seconds=max(settings.workflow_timeout_seconds, settings.agent_timeout_seconds) * 2)
    stale = db.query(Run).filter(Run.status.in_(["running", "queued"]), Run.created_at < cutoff).all()
    for run in stale:
        run.status = "failed"
        run.error = "Run was interrupted (server restarted or timed out)"
        run.finished_at = utcnow()
    db.commit()
    return len(stale)


def purge_old_runs(db: Session, days: int) -> int:
    """Delete finished runs older than `days` (0 keeps everything)."""
    if not days or days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=days)
    from ..models import ChatMessage

    old_ids = [
        r.id
        for r in db.query(Run.id).filter(Run.created_at < cutoff, Run.status.in_(["succeeded", "failed"])).limit(5000)
    ]
    if not old_ids:
        return 0
    db.query(ChatMessage).filter(ChatMessage.run_id.in_(old_ids)).update(
        {ChatMessage.run_id: None}, synchronize_session=False
    )
    deleted = db.query(Run).filter(Run.id.in_(old_ids)).delete(synchronize_session=False)
    db.commit()
    return deleted
