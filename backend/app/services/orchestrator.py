"""Chat orchestration: decide which agent or workflow handles a message, run it, store the reply.

Routing order:
1. The session is pinned to an agent  -> use it.
2. Keyword fast path: exactly one accessible agent/workflow has a matching trigger keyword.
3. LLM router over the accessible agents/workflows (default model, JSON output, validated).
4. Nothing fits -> answer directly with the default model as a general assistant.
"""

import json
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..llm.client import LLMError, get_llm_client
from ..models import Agent, ChatMessage, ChatSession, Run, User, Workflow, utcnow
from ..rbac import has_permission, visible_filter
from .form_input import check_input, from_chat_message
from .models_service import ModelNotAvailable, resolve_model, to_target
from .runs import create_run, execute_run

logger = logging.getLogger("agentos.orchestrator")

ROUTER_MIN_CONFIDENCE = 0.6
GENERAL_SYSTEM_PROMPT = "You are a helpful enterprise assistant. Answer concisely. If you do not know, say so."


def keywords_of(raw: Optional[str]) -> list[str]:
    return [k.strip().lower() for k in (raw or "").split(",") if len(k.strip()) >= 3]


def keyword_matches(text: str, raw_keywords: Optional[str]) -> bool:
    lowered = text.lower()
    return any(re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", lowered) for k in keywords_of(raw_keywords))


def accessible_targets(db: Session, user: User) -> tuple[list[Agent], list[Workflow]]:
    agents, workflows = [], []
    if has_permission(user, "agent:run"):
        agents = visible_filter(db.query(Agent), Agent, user).filter(Agent.is_active.is_(True)).all()
    if has_permission(user, "workflow:run"):
        workflows = visible_filter(db.query(Workflow), Workflow, user).filter(Workflow.status == "active").all()
    return agents, workflows


def fast_path(text: str, agents: list[Agent], workflows: list[Workflow]):
    matches = [a for a in agents if keyword_matches(text, a.trigger_keywords)]
    matches += [w for w in workflows if keyword_matches(text, w.trigger_keywords)]
    return matches[0] if len(matches) == 1 else None


def llm_route(db: Session, user: User, text: str, agents: list[Agent], workflows: list[Workflow]):
    if not agents and not workflows:
        return None, None
    try:
        model = resolve_model(db, None, user.role)
    except ModelNotAvailable:
        return None, None

    catalog = [
        {"type": "agent", "id": a.id, "name": a.name, "description": (a.description or "")[:300]} for a in agents
    ]
    catalog += [
        {"type": "workflow", "id": w.id, "name": w.name, "description": (w.description or "")[:300]} for w in workflows
    ]
    prompt = (
        "You route a user's request to one of the tools below, or to none.\n"
        f"Tools:\n{json.dumps(catalog)}\n\n"
        'Reply with JSON only: {"type": "agent"|"workflow"|"none", "id": <id or null>, "confidence": <0..1>}.\n'
        'Use "none" for greetings, general questions, or when no tool clearly fits.'
    )
    try:
        resp = get_llm_client().chat(
            to_target(model),
            [{"role": "system", "content": prompt}, {"role": "user", "content": text}],
            temperature=0,
            json_mode=True,
        )
        decision = json.loads(resp.content)
        kind, target_id, confidence = decision.get("type"), decision.get("id"), float(decision.get("confidence", 0))
    except (LLMError, ValueError, TypeError, AttributeError) as exc:
        logger.warning("LLM routing failed: %s", exc)
        return None, {"error": str(exc)[:200]}

    info = {"type": kind, "id": target_id, "confidence": confidence}
    if confidence < ROUTER_MIN_CONFIDENCE:
        return None, info
    pool = agents if kind == "agent" else workflows if kind == "workflow" else []
    return next((t for t in pool if str(t.id) == str(target_id)), None), info


def general_answer(db: Session, user: User, history: list[dict], text: str) -> tuple[str, dict]:
    model = resolve_model(db, None, user.role)
    messages = [{"role": "system", "content": GENERAL_SYSTEM_PROMPT}, *history, {"role": "user", "content": text}]
    resp = get_llm_client().chat(to_target(model), messages, temperature=0.3)
    return resp.content, {
        "model": model.model_name,
        "prompt_tokens": resp.prompt_tokens,
        "completion_tokens": resp.completion_tokens,
    }


def recent_history(db: Session, session_id: int) -> list[dict]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .limit(settings.chat_history_messages)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def handle_message(db: Session, session: ChatSession, user: User, text: str) -> ChatMessage:
    history = recent_history(db, session.id)
    db.add(ChatMessage(session_id=session.id, role="user", content=text))
    db.commit()

    agents, workflows = accessible_targets(db, user)
    target, routing = None, {"method": None}

    if session.agent_id:
        pinned = next((a for a in agents if a.id == session.agent_id), None)
        if pinned is None:
            return _reply(
                db,
                session,
                "The agent pinned to this chat is no longer available to you.",
                {"routing": {"method": "pinned", "error": "unavailable"}},
            )
        target, routing = pinned, {"method": "pinned"}
    else:
        target = fast_path(text, agents, workflows)
        if target is not None:
            routing = {"method": "keyword"}
        else:
            target, info = llm_route(db, user, text, agents, workflows)
            routing = {"method": "llm" if target else "general", "router": info}

    if target is None:
        try:
            answer, meta = general_answer(db, user, history, text)
        except (ModelNotAvailable, LLMError) as exc:
            return _reply(db, session, f"Sorry, I can't answer right now: {exc}", {"routing": routing, "error": True})
        return _reply(db, session, answer, {"routing": routing, **meta})

    kind = "agent" if isinstance(target, Agent) else "workflow"
    run_input = {"message": text}
    if kind == "agent":
        run_input["history"] = history
    else:
        run_input, problems = check_input(target.definition or {}, from_chat_message(target.definition or {}, text))
        if problems:
            meta = {"routing": routing, "target": {"type": kind, "id": target.id, "name": target.name}}
            return _reply(
                db,
                session,
                f"'{target.name}' needs more information than a chat message ({'; '.join(problems)}). "
                "Run it from Workflows to fill in its form.",
                meta,
            )
    run = create_run(db, target=target, user=user, source="chat", input_data=run_input)
    execute_run(run.id)
    db.expire_all()
    run = db.get(Run, run.id)

    if run.status == "succeeded":
        out = run.output or {}
        content = out.get("answer") if kind == "agent" else _format_result(out.get("result"))
    else:
        content = f"The {kind} '{target.name}' could not complete this request: {run.error}"
    meta = {
        "routing": routing,
        "target": {"type": kind, "id": target.id, "name": target.name},
        "run_status": run.status,
    }
    return _reply(db, session, content or "(no answer)", meta, run_id=run.id)


def _format_result(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict) and len(result) == 1 and isinstance(next(iter(result.values())), str):
        return next(iter(result.values()))
    return "```json\n" + json.dumps(result, indent=2, default=str) + "\n```"


def _reply(db: Session, session: ChatSession, content: str, meta: dict, run_id: Optional[int] = None) -> ChatMessage:
    msg = ChatMessage(session_id=session.id, role="assistant", content=content, run_id=run_id, metadata_json=meta)
    db.add(msg)
    session.updated_at = utcnow()
    db.commit()
    db.refresh(msg)
    return msg
