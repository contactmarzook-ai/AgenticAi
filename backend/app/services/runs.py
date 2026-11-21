"""Creating and executing runs of agents and workflows.

Runs execute either inline (chat, where the user waits for the answer) or on a
small in-process thread pool (API / schedule / webhook), with status polled via
GET /api/runs/{id}. All state lives in the database, so any API replica can serve
the status call.
"""

import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_, update
from sqlalchemy.orm import Session

from .. import contracts
from ..config import settings
from ..crypto import decrypt_json
from ..database import SessionLocal
from ..llm.client import LLMError, get_llm_client
from ..models import Agent, Credential, Run, RunNode, User, Workflow
from ..nodes import NodeContext, NodeError, get_node_type
from ..rbac import can_view
from ..tools import registry
from .agent_runtime import AgentRunError, run_agent
from .models_service import ModelNotAvailable, resolve_model, to_target
from .platform_settings import get_settings
from .workflow_engine import WorkflowError, mask_secrets, run_definition

logger = logging.getLogger("agentos.runs")


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
    hold: bool = False,
) -> Run:
    """Create a run. `hold=True` creates it already claimed by the calling thread (for runs the
    request executes itself), so no poller can pick it up in between."""
    run = Run(
        target_type="agent" if isinstance(target, Agent) else "workflow",
        target_id=target.id,
        target_name=target.name,
        source=source,
        status="queued",
        input=input_data,
        user_id=user.id if user else None,
        org_id=target.org_id,
        trigger_id=trigger_id,
    )
    if hold:
        run.status, run.worker_id, run.heartbeat_at = "running", _thread_worker(), utcnow()
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def agent_input(run_input: dict) -> dict:
    """The agent's input object. Runs store {"input": {...}}; older runs and chat store {"message"}."""
    if isinstance(run_input.get("input"), dict):
        return run_input["input"]
    return {"message": str(run_input.get("message", ""))}


def _history_for(input_data: dict) -> list[dict]:
    hist = input_data.get("history") or []
    return [m for m in hist if isinstance(m, dict) and m.get("role") in ("user", "assistant")]


class _ThreadSessions:
    """One database session per thread for the duration of a run (steps may run in parallel and
    a SQLAlchemy session must not be shared between threads)."""

    def __init__(self, main: Session):
        self._local = threading.local()
        self._local.db = main
        self._main_thread = threading.get_ident()
        self._opened: list[Session] = []
        self._lock = threading.Lock()

    def get(self) -> Session:
        db = getattr(self._local, "db", None)
        if db is None:
            db = SessionLocal()
            self._local.db = db
            with self._lock:
                self._opened.append(db)
        return db

    def close(self) -> None:
        for db in self._opened:
            db.close()


def _ask_llm_factory(sessions: "_ThreadSessions", role: str, usage: dict, lock: threading.Lock):
    def ask_llm(messages: list[dict], json_mode: bool = False, model_id: Optional[int] = None) -> dict:
        try:
            model = resolve_model(sessions.get(), model_id, role)
            resp = get_llm_client().chat(to_target(model), messages, temperature=0.2, json_mode=json_mode)
        except (ModelNotAvailable, LLMError) as exc:
            raise NodeError(str(exc)) from exc
        with lock:
            usage["prompt"] += resp.prompt_tokens
            usage["completion"] += resp.completion_tokens
            usage["calls"] += 1
            usage["model"] = model.model_name
        return {"text": resp.content}

    return ask_llm


class DbNodeStore:
    """Step checkpoints in the run_nodes table. Each save commits on its own session, so a
    record is durable the moment a step changes state (and parallel steps never share a session)."""

    FIELDS = ("seq", "type", "label", "action", "status", "continued", "attempts", "input", "output", "error", "logs")

    def __init__(self, run_id: int):
        self.run_id = run_id
        self._lock = threading.Lock()

    def load(self) -> dict[str, dict]:
        db = SessionLocal()
        try:
            rows = db.query(RunNode).filter(RunNode.run_id == self.run_id).all()
            return {r.node_id: self._as_record(r) for r in rows}
        finally:
            db.close()

    @staticmethod
    def _as_record(r: RunNode) -> dict:
        rec = {k: getattr(r, k) for k in DbNodeStore.FIELDS}
        rec.update(
            node_id=r.node_id,
            logs=list(r.logs or []),
            started_at=r.started_at.isoformat() if r.started_at else None,
            finished_at=r.finished_at.isoformat() if r.finished_at else None,
        )
        return rec

    def save(self, record: dict) -> None:
        with self._lock:
            db = SessionLocal()
            try:
                row = (
                    db.query(RunNode)
                    .filter(RunNode.run_id == self.run_id, RunNode.node_id == record["node_id"])
                    .first()
                )
                if row is None:
                    row = RunNode(run_id=self.run_id, node_id=record["node_id"])
                    db.add(row)
                for k in self.FIELDS:
                    if k in record:
                        value = record[k]
                        if k in ("input", "output"):
                            value = mask_secrets(value) if k == "input" else value
                        setattr(row, k, value if k != "label" else str(value or "")[:200])
                row.started_at = _parse_ts(record.get("started_at"))
                row.finished_at = _parse_ts(record.get("finished_at"))
                db.commit()
            finally:
                db.close()


def _parse_ts(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _cancel_checker(run_id: int):
    """Cheap, rate-limited check of the run's cancel flag (read on its own session)."""
    state = {"at": 0.0, "value": False}

    def check() -> bool:
        if state["value"]:
            return True
        now = time.monotonic()
        if now - state["at"] < 0.5:
            return False
        state["at"] = now
        db = SessionLocal()
        try:
            state["value"] = bool(db.query(Run.cancel_requested).filter(Run.id == run_id).scalar())
        finally:
            db.close()
        return state["value"]

    return check


def _execute(db: Session, run: Run, usage: dict) -> None:
    user = db.get(User, run.user_id) if run.user_id else None
    role = user.role if user and user.is_active else "viewer"
    cancelled = _cancel_checker(run.id)

    if run.target_type == "agent":
        agent = db.get(Agent, run.target_id)
        if agent is None:
            raise AgentRunError("Agent no longer exists")
        if cancelled():
            raise AgentRunError("Run was cancelled")
        res = run_agent(db, agent, agent_input(run.input), role, history=_history_for(run.input))
        run.output = res.output
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
    owner_id = wf.owner_id
    sessions = _ThreadSessions(db)
    lock = threading.Lock()

    def owner_in(sdb: Session) -> Optional[User]:
        owner = sdb.get(User, owner_id) if owner_id else None
        return owner if owner is not None and owner.is_active else None

    def call_agent(agent_id: int, input_data: dict) -> dict:
        sdb = sessions.get()
        agent = sdb.get(Agent, agent_id)
        owner = owner_in(sdb)
        if agent is None or owner is None or not can_view(owner, agent):
            raise NodeError("This agent is not available to the workflow's owner")
        try:
            res = run_agent(sdb, agent, contracts.coerce(agent.input_schema or {}, input_data), role)
        except AgentRunError as exc:
            raise NodeError(str(exc)) from exc
        with lock:
            usage["prompt"] += res.prompt_tokens
            usage["completion"] += res.completion_tokens
            usage["calls"] += res.llm_calls
            usage["model"] = res.model_name
        return {**res.output, **({} if "agent" in res.output else {"agent": agent.name})}

    def get_credential(cred_id, expected_type: str) -> dict:
        sdb = sessions.get()
        try:
            cred = sdb.get(Credential, int(cred_id))
        except (TypeError, ValueError):
            cred = None
        owner = owner_in(sdb)
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
        ask_llm=_ask_llm_factory(sessions, role, usage, lock),
        run_agent=call_agent,
        settings=platform,
    )
    disabled = set(platform.get("disabled_nodes") or [])
    definition, run_input = wf.definition or {}, run.input or {}
    # End this session's read transaction before the (possibly long) run: steps use their own
    # sessions, and an idle open transaction would hold locks for minutes.
    db.commit()

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

    try:
        res = run_definition(
            definition,
            run_input,
            call_agent,
            call_tool,
            call_action,
            store=DbNodeStore(run.id),
            max_parallel=settings.workflow_max_parallel,
            should_cancel=cancelled,
        )
    finally:
        sessions.close()
    run.output = {"result": res["output"]}
    run.steps = res["steps"]


# ---------------- claiming, heartbeats and recovery ----------------
WORKER_ID = f"{socket.gethostname()[:40]}-{os.getpid()}"


def _thread_worker() -> str:
    return f"{WORKER_ID}-{threading.get_ident()}"


def _claim(db: Session, run_id: int, worker: str) -> bool:
    """Atomically take a queued run, or a running one whose worker stopped sending heartbeats."""
    now = utcnow()
    stale = now - timedelta(seconds=settings.run_stale_seconds)
    claimed = db.execute(
        update(Run)
        .where(
            Run.id == run_id,
            or_(
                Run.status == "queued",
                and_(Run.status == "running", Run.worker_id == worker),  # created held by this thread
                and_(Run.status == "running", or_(Run.heartbeat_at.is_(None), Run.heartbeat_at < stale)),
            ),
        )
        .values(status="running", worker_id=worker, heartbeat_at=now)
    ).rowcount
    db.commit()
    return claimed == 1


class _Heartbeat:
    """Renews the run's lease while it executes, from a background thread."""

    def __init__(self, run_id: int, worker: str):
        self.run_id, self.worker = run_id, worker
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._beat, name=f"heartbeat-{run_id}", daemon=True)

    def _beat(self) -> None:
        while not self._stop.wait(settings.run_heartbeat_seconds):
            db = SessionLocal()
            try:
                db.execute(
                    update(Run)
                    .where(Run.id == self.run_id, Run.worker_id == self.worker, Run.status == "running")
                    .values(heartbeat_at=utcnow())
                )
                db.commit()
            except Exception:  # noqa: BLE001 - a missed beat is retried on the next tick
                logger.warning("Heartbeat for run %s failed", self.run_id)
            finally:
                db.close()

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()


def execute_run(run_id: int, worker: Optional[str] = None) -> None:
    """Claim and execute a run in its own DB session. Never raises.

    A run interrupted earlier (its worker died) is resumed: finished workflow steps are kept and
    the rest run again; agent runs start over."""
    worker = worker or _thread_worker()
    db = SessionLocal()
    try:
        if not _claim(db, run_id, worker):
            return
        run = db.get(Run, run_id)
        if run.cancel_requested:
            _finish_cancelled(db, run)
            return
        if run.started_at is None:
            run.started_at = utcnow()
        else:
            run.resume_count = (run.resume_count or 0) + 1
            if run.resume_count > settings.run_max_resumes:
                run.status, run.error, run.finished_at = "failed", "Run was interrupted too many times", utcnow()
                db.commit()
                return
            logger.info("Resuming run %s (attempt %s)", run_id, run.resume_count + 1)
        db.commit()
        usage = {"prompt": 0, "completion": 0, "calls": 0, "model": None}
        with _Heartbeat(run_id, worker):
            try:
                _execute(db, run, usage)
                run.status = "succeeded"
            except (AgentRunError, WorkflowError) as exc:
                db.rollback()
                run = db.get(Run, run_id)
                db.refresh(run)
                run.status = "cancelled" if run.cancel_requested else "failed"
                run.error = str(exc)
                if getattr(exc, "steps", None):
                    run.steps = exc.steps
            except Exception as exc:  # unexpected bug: record it, don't leak a traceback to users
                logger.exception("Run %s crashed", run_id)
                db.rollback()
                run = db.get(Run, run_id)
                run.status = "failed"
                run.error = f"Internal error ({exc.__class__.__name__})"
        run.prompt_tokens = (run.prompt_tokens or 0) + usage["prompt"]
        run.completion_tokens = (run.completion_tokens or 0) + usage["completion"]
        run.llm_calls = (run.llm_calls or 0) + usage["calls"]
        run.model_name = usage["model"] or run.model_name
        run.finished_at = utcnow()
        run.worker_id = None
        db.commit()
        if run.status == "failed":
            from .notify import notify_failure

            notify_failure(db, run)
    finally:
        db.close()


def _finish_cancelled(db: Session, run: Run) -> None:
    run.status, run.error, run.finished_at, run.worker_id = "cancelled", "Run was cancelled", utcnow(), None
    db.query(RunNode).filter(RunNode.run_id == run.id, RunNode.status.in_(["pending", "running"])).update(
        {RunNode.status: "cancelled"}, synchronize_session=False
    )
    db.commit()


def cancel_run(db: Session, run: Run) -> Run:
    """Cancel a queued run at once; ask a running one to stop (it stops before its next step)."""
    if run.status in ("succeeded", "failed", "cancelled"):
        return run
    run.cancel_requested = True
    db.commit()
    cancelled_now = db.execute(
        update(Run)
        .where(Run.id == run.id, Run.status == "queued")
        .values(status="cancelled", finished_at=utcnow(), error="Run was cancelled")
    ).rowcount
    db.commit()
    db.refresh(run)
    if cancelled_now:
        _finish_cancelled(db, run)
    return run


# ---------------- worker: runs queued work and takes over abandoned runs ----------------
class Worker:
    """Executes runs on a thread pool. `submit` starts a run right away; with polling on
    (RUN_POLL_SECONDS > 0) it also picks up queued runs from any pod and resumes runs whose
    heartbeat stopped (a restarted pod). The database is the queue: nothing is lost on restart."""

    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=settings.run_worker_threads, thread_name_prefix="run")
        self._inflight: set[int] = set()
        self._lock = threading.Lock()
        self._poller: Optional[threading.Thread] = None

    def submit(self, run_id: int) -> bool:
        with self._lock:
            if run_id in self._inflight:
                return False
            self._inflight.add(run_id)
        self._pool.submit(self._run, run_id)
        return True

    def _run(self, run_id: int) -> None:
        try:
            execute_run(run_id)
        finally:
            with self._lock:
                self._inflight.discard(run_id)

    def free_slots(self) -> int:
        with self._lock:
            return settings.run_worker_threads - len(self._inflight)

    def poll_once(self) -> int:
        """Pick up queued and abandoned runs. Returns how many were started."""
        slots = self.free_slots()
        if slots <= 0:
            return 0
        stale = utcnow() - timedelta(seconds=settings.run_stale_seconds)
        db = SessionLocal()
        try:
            ids = [
                r.id
                for r in db.query(Run.id)
                .filter(
                    or_(
                        Run.status == "queued",
                        and_(Run.status == "running", or_(Run.heartbeat_at.is_(None), Run.heartbeat_at < stale)),
                    )
                )
                .order_by(Run.id)
                .limit(slots)
            ]
        finally:
            db.close()
        return sum(1 for rid in ids if self.submit(rid))

    def start_polling(self) -> None:
        if settings.run_poll_seconds <= 0 or self._poller is not None:
            return
        self._poller = threading.Thread(target=self._poll_loop, name="run-poller", daemon=True)
        self._poller.start()

    def _poll_loop(self) -> None:
        while True:
            try:
                n = self.poll_once()
                if n:
                    logger.info("Picked up %d queued or interrupted run(s)", n)
            except Exception:  # noqa: BLE001 - keep polling (e.g. database briefly unavailable)
                logger.exception("Run poller failed")
            time.sleep(settings.run_poll_seconds)


worker = Worker()


def submit_run(run_id: int) -> None:
    if settings.run_worker_enabled:
        worker.start_polling()
        worker.submit(run_id)
    # Otherwise the run stays queued for a dedicated worker process (python -m app.worker).


def purge_old_runs(db: Session, days: int) -> int:
    """Delete finished runs older than `days` (0 keeps everything)."""
    if not days or days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=days)
    from ..models import ChatMessage

    old_ids = [
        r.id
        for r in db.query(Run.id)
        .filter(Run.created_at < cutoff, Run.status.in_(["succeeded", "failed", "cancelled"]))
        .limit(5000)
    ]
    if not old_ids:
        return 0
    db.query(ChatMessage).filter(ChatMessage.run_id.in_(old_ids)).update(
        {ChatMessage.run_id: None}, synchronize_session=False
    )
    deleted = db.query(Run).filter(Run.id.in_(old_ids)).delete(synchronize_session=False)
    db.commit()
    return deleted
