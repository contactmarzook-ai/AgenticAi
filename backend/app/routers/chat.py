from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..database import get_db
from ..models import Agent, ChatMessage, ChatSession, User, utcnow
from ..rbac import can_view, require_permission
from ..schemas import ChatMessageOut, ChatSend, ChatSessionIn, ChatSessionOut
from ..services.orchestrator import handle_message
from ..services.runs import enforce_concurrency

router = APIRouter(prefix="/api/chat", tags=["chat"])
chat_user = require_permission("chat:use")


def _chat_rate_limit(db: Session, user: User) -> None:
    limit = settings.user_runs_per_minute
    if limit <= 0:
        return
    since = utcnow() - timedelta(minutes=1)
    count = (
        db.query(ChatMessage)
        .join(ChatSession)
        .filter(ChatSession.user_id == user.id, ChatMessage.role == "user", ChatMessage.created_at >= since)
        .count()
    )
    if count >= limit:
        raise HTTPException(status_code=429, detail=f"Rate limit: at most {limit} messages per minute")


def _own_session(db: Session, session_id: int, user: User) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(db: Session = Depends(get_db), user: User = Depends(chat_user)):
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(100)
        .all()
    )


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
def create_session(body: ChatSessionIn, db: Session = Depends(get_db), user: User = Depends(chat_user)):
    if body.agent_id is not None:
        agent = db.get(Agent, body.agent_id)
        if agent is None or not agent.is_active or not can_view(user, agent):
            raise HTTPException(status_code=404, detail="Agent not found")
    session = ChatSession(user_id=user.id, title=body.title or "New Chat", agent_id=body.agent_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def get_messages(session_id: int, db: Session = Depends(get_db), user: User = Depends(chat_user)):
    _own_session(db, session_id, user)
    return db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.id).all()


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageOut)
def send_message(
    session_id: int, body: ChatSend, request: Request, db: Session = Depends(get_db), user: User = Depends(chat_user)
):
    session = _own_session(db, session_id, user)
    text = body.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message is empty")
    if len(text) > settings.max_message_chars:
        raise HTTPException(status_code=413, detail=f"Message longer than {settings.max_message_chars} characters")
    _chat_rate_limit(db, user)
    enforce_concurrency(db, user)
    reply = handle_message(db, session, user, text)
    meta = reply.metadata_json or {}
    audit(
        db,
        "chat.message",
        user=user,
        resource_type="chat_session",
        resource_id=session.id,
        details={
            "routing": (meta.get("routing") or {}).get("method"),
            "target": meta.get("target"),
            "run_id": reply.run_id,
        },
        request=request,
    )
    return reply


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(chat_user)):
    session = _own_session(db, session_id, user)
    db.delete(session)
    db.commit()
    return {"status": "deleted"}
