from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, List

from app.database import get_db
from app.auth import get_current_user, require_admin
from app.models import User, ChatMessage, Agent, Workflow

monitoring_router = APIRouter(prefix="/api/admin/monitoring", tags=["monitoring"])

@monitoring_router.get("/logs")
def get_monitoring_logs(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    # Fetch all assistant messages that have routing metadata
    # And their corresponding user message for context
    assistant_messages = db.query(ChatMessage).filter(
        ChatMessage.role == "assistant",
        ChatMessage.metadata_json != None
    ).order_by(ChatMessage.created_at.desc()).limit(100).all()

    logs = []

    total_fast_path = 0
    total_llm = 0
    sum_llm_latency = 0.0
    sum_agent_time = 0.0
    success_count = 0
    total_requests = 0

    for asst_msg in assistant_messages:
        # find the preceding user message in the same session
        user_msg = db.query(ChatMessage).filter(
            ChatMessage.session_id == asst_msg.session_id,
            ChatMessage.role == "user",
            ChatMessage.id < asst_msg.id
        ).order_by(ChatMessage.id.desc()).first()

        user_request = user_msg.content if user_msg else "N/A"

        meta = asst_msg.metadata_json or {}
        routing = meta.get("routing", {})
        timing = meta.get("timing", {})
        execution = meta.get("execution", {})

        method = routing.get("routing_method", "unknown")
        action = routing.get("action", "unknown")

        target_name = "N/A"
        if action == "agent":
             agent = db.query(Agent).filter(Agent.id == routing.get("target_id")).first()
             if agent:
                 target_name = agent.name
        elif action == "workflow":
             wf = db.query(Workflow).filter(Workflow.id == routing.get("target_id")).first()
             if wf:
                 target_name = wf.name

        status = "success" if asst_msg.content and "failed" not in asst_msg.content.lower() else "error"
        if execution and execution.get("status") == "error":
             status = "error"

        error_details = execution.get("error", "") if status == "error" else ""

        logs.append({
            "id": asst_msg.id,
            "created_at": asst_msg.created_at,
            "user_request": user_request,
            "routing_method": method,
            "target": f"{action}: {target_name}",
            "total_duration": timing.get("total_duration_sec", 0.0),
            "llm_duration": timing.get("llm_duration_sec", 0.0),
            "status": status,
            "error_details": error_details
        })

        # Aggregate metrics
        if method == "fast_path":
            total_fast_path += 1
        elif method == "llm":
            total_llm += 1
            sum_llm_latency += timing.get("llm_duration_sec", 0.0)

        sum_agent_time += timing.get("agent_duration_sec", 0.0)

        if status == "success":
            success_count += 1

        total_requests += 1

    fast_path_percent = (total_fast_path / total_requests * 100) if total_requests > 0 else 0
    avg_llm_latency = (sum_llm_latency / total_llm) if total_llm > 0 else 0
    avg_agent_time = (sum_agent_time / total_requests) if total_requests > 0 else 0
    success_rate = (success_count / total_requests * 100) if total_requests > 0 else 0

    return {
        "logs": logs,
        "metrics": {
            "fastPathPercent": fast_path_percent,
            "avgLlmLatency": avg_llm_latency,
            "avgAgentTime": avg_agent_time,
            "successRate": success_rate,
            "totalRequests": total_requests
        }
    }
