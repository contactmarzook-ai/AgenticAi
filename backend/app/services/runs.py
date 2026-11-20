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
from ..database import SessionLocal
from ..models import Agent, Run, User, Workflow
from ..tools import registry
from .agent_runtime import AgentRunError, run_agent
from .workflow_engine import WorkflowError, run_definition

logger = logging.getLogger("agentos.runs")
_pool = ThreadPoolExecutor(max_workers=settings.run_worker_threads, thread_name_prefix="run")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enforce_rate_limit(db: Session, user: User) -> None:
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


def _execute(db: Session, run: Run) -> None:
    user = db.get(User, run.user_id) if run.user_id else None
    role = user.role if user and user.is_active else "user"
    usage = {"prompt": 0, "completion": 0, "calls": 0, "model": None}

    def call_agent(agent_id: int, message: str) -> dict:
        agent = db.get(Agent, agent_id)
        if agent is None:
            raise WorkflowError(f"Agent {agent_id} not found")
        try:
            res = run_agent(db, agent, message, role)
        except AgentRunError as exc:
            raise WorkflowError(str(exc)) from exc
        usage["prompt"] += res.prompt_tokens
        usage["completion"] += res.completion_tokens
        usage["calls"] += res.llm_calls
        usage["model"] = res.model_name
        return {"answer": res.answer, "agent": agent.name, "steps": len(res.steps)}

    def call_tool(name: str, args: dict):
        try:
            return registry.execute(name, args)
        except registry.ToolError as exc:
            raise WorkflowError(str(exc)) from exc

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
    else:
        wf = db.get(Workflow, run.target_id)
        if wf is None:
            raise WorkflowError("Workflow no longer exists")
        try:
            res = run_definition(wf.definition or {}, run.input or {}, call_agent, call_tool)
        finally:
            run.prompt_tokens, run.completion_tokens, run.llm_calls = (
                usage["prompt"],
                usage["completion"],
                usage["calls"],
            )
        run.output = {"result": res["output"]}
        run.steps = res["steps"]

    run.prompt_tokens, run.completion_tokens, run.llm_calls = usage["prompt"], usage["completion"], usage["calls"]
    run.model_name = usage["model"]


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
        try:
            _execute(db, run)
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
        run.finished_at = utcnow()
        db.commit()
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
