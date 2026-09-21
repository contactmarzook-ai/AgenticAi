import json
import requests
import time
from typing import Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session

from app.models import Agent, Workflow, ChatSession, ChatMessage, User
from app.services.executor import execute_agent_script
from app.services.workflow_runner import run_workflow_pipeline

LLAMA_URL = "http://localhost:11434/api/generate"

def build_dynamic_prompt(db: Session) -> str:
    """
    Dynamically generates a system prompt based on active DB agents and workflows.
    Instructs the LLM to act as a router and return strict JSON.
    """
    agents = db.query(Agent).filter(Agent.is_active == True).all()
    workflows = db.query(Workflow).all()

    tools_desc = []

    # Format Agents
    for agent in agents:
        desc = f"- TYPE: agent | ID: {agent.id} | NAME: {agent.name} | DESC: {agent.description}"
        if agent.input_schema:
             desc += f" | SCHEMA: {json.dumps(agent.input_schema)}"
        tools_desc.append(desc)

    # Format Workflows
    active_workflows = db.query(Workflow).filter(Workflow.is_active == True).all()
    for wf in active_workflows:
         desc = f"- TYPE: workflow | ID: {wf.id} | NAME: {wf.name} | DESC: {wf.description}"
         tools_desc.append(desc)

    tools_str = "\n".join(tools_desc) if tools_desc else "No tools available."

    prompt = f"""You are a lightweight, fast AI Router.
Do NOT perform deep reasoning or generate multi-step plans.
Your ONLY job is to identify the most appropriate registered tool (agent or workflow) for the user's request and extract parameters.

Available tools:
{tools_str}

You MUST return your response as valid JSON ONLY, with NO markdown formatting, NO backticks, and NO conversational text.

Include a "confidence_score" between 0.0 and 1.0 indicating how well the request matches the tool.

If you clearly map the request to a tool (confidence >= 0.7), return:
{{"action": "agent" or "workflow", "target_id": integer_id, "parameters": {{"param1": "value1"}}, "confidence_score": float}}
Note: For workflows, parameters might be optional or empty depending on the first step.

If the request is ambiguous, doesn't clearly match a tool, or your confidence is below 0.7, return:
{{"action": "clarify", "message": "I'm not sure which tool to use. Could you clarify your request?", "confidence_score": float}}

If it's just a conversational greeting, respond appropriately:
{{"action": "chat", "message": "Hello! How can I help you today?", "confidence_score": 1.0}}
"""
    return prompt

def fast_path_route(user_input: str, db: Session) -> Optional[Dict[str, Any]]:
    """
    Attempts to route the request quickly without an LLM by checking agent names and keywords.
    Returns a routing dictionary if a confident match is found, otherwise None.
    """
    user_input_lower = user_input.lower().strip()
    agents = db.query(Agent).filter(Agent.is_active == True).all()
    workflows = db.query(Workflow).filter(Workflow.is_active == True).all()

    best_match = None
    match_type = None

    for agent in agents:
        # Check exact name match
        if agent.name.lower() in user_input_lower:
            best_match = agent
            match_type = "agent"
            break

        # Check trigger keywords
        if agent.trigger_keywords:
            keywords = [k.strip().lower() for k in agent.trigger_keywords.split(',')]
            if any(kw in user_input_lower for kw in keywords):
                best_match = agent
                match_type = "agent"
                break

    if not best_match:
        for wf in workflows:
            if wf.name.lower() in user_input_lower:
                best_match = wf
                match_type = "workflow"
                break

    if best_match:
        return {
            "action": match_type,
            "target_id": best_match.id,
            "parameters": {"raw_input": user_input},
            "confidence_score": 0.9,
            "routing_method": "fast_path"
        }

    return None

def call_llama(prompt: str) -> Dict[str, Any]:
    """
    Calls local Llama model via Ollama API, enforcing JSON output.
    """
    payload = {
        "model": "llama3",
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(LLAMA_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        content = data.get("response", "{}")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"action": "error", "message": "Failed to parse LLM output as JSON.", "raw_output": content}

    except requests.exceptions.RequestException as e:
        return {"action": "error", "message": f"Error communicating with local LLM: {str(e)}"}

def route_and_execute(user_input: str, session_id: int, user: User, db: Session) -> Dict[str, Any]:
    """
    Main orchestration pipeline:
    1. Save user message.
    2. Build prompt & call LLM.
    3. Route to execution (Agent or Workflow).
    4. Save Assistant response & metadata.
    """
    # 1. Save user message
    user_msg = ChatMessage(session_id=session_id, role="user", content=user_input)
    db.add(user_msg)
    db.commit()

    # 2. Fast-Path Routing
    route_response = fast_path_route(user_input, db)

    # 3. LLM Fallback (if fast path fails)
    llm_duration_sec = 0.0
    if not route_response:
        system_prompt = build_dynamic_prompt(db)
        full_prompt = f"{system_prompt}\n\nUser Request: {user_input}"

        llm_start = time.time()
        route_response = call_llama(full_prompt)
        llm_duration_sec = time.time() - llm_start

        route_response["routing_method"] = "llm"
        route_response["llm_duration_sec"] = llm_duration_sec

    action = route_response.get("action")

    # Setup response payload
    final_response = {
        "status": "success",
        "action": action,
        "message": "",
        "execution_trace": None,
        "llm_reasoning": route_response if route_response.get("routing_method") == "llm" else None
    }

    metadata = {"routing": route_response}

    # 4. Route Execution
    confidence = route_response.get("confidence_score", 1.0)
    agent_duration_sec = 0.0

    agent_start = time.time()
    if action == "error":
        final_response["status"] = "error"
        final_response["message"] = route_response.get("message", "An unknown error occurred.")

    elif action in ["clarify", "chat"]:
        final_response["message"] = route_response.get("message", "Could you provide more details?")

    elif action in ["agent", "workflow"] and confidence < 0.7:
        final_response["action"] = "clarify"
        final_response["message"] = "I'm not confident about which tool to use. Could you clarify your request?"

    elif action == "agent":
        target_id = route_response.get("target_id")
        params = route_response.get("parameters", {})

        agent = db.query(Agent).filter(Agent.id == target_id).first()
        if agent:
             exe_result = execute_agent_script(agent.handler, params)
             metadata["execution"] = exe_result
             final_response["execution_trace"] = exe_result

             if exe_result.get("status") == "success":
                  final_response["message"] = f"Agent '{agent.name}' executed successfully."
             else:
                  final_response["status"] = "error"
                  final_response["message"] = f"Agent '{agent.name}' execution failed: {exe_result.get('error')}"
        else:
             final_response["status"] = "error"
             final_response["message"] = f"Agent with ID {target_id} not found."

    elif action == "workflow":
        target_id = route_response.get("target_id")
        params = route_response.get("parameters", {})

        wf = db.query(Workflow).filter(Workflow.id == target_id).first()
        if wf:
             exe_result = run_workflow_pipeline(wf.id, params, db)
             metadata["execution"] = exe_result
             final_response["execution_trace"] = exe_result

             if exe_result.get("status") == "success":
                  final_response["message"] = f"Workflow '{wf.name}' executed successfully."
             else:
                  final_response["status"] = "error"
                  final_response["message"] = f"Workflow '{wf.name}' execution failed."
        else:
             final_response["status"] = "error"
             final_response["message"] = f"Workflow with ID {target_id} not found."
    else:
        final_response["status"] = "error"
        final_response["message"] = f"Unknown action: {action}"

    agent_duration_sec = time.time() - agent_start
    metadata["timing"] = {
        "llm_duration_sec": llm_duration_sec,
        "agent_duration_sec": agent_duration_sec,
        "total_duration_sec": llm_duration_sec + agent_duration_sec
    }

    # 4. Save Assistant message
    asst_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=final_response["message"],
        metadata_json=metadata
    )
    db.add(asst_msg)

    # Update session modified time
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session:
         from datetime import datetime, timezone
         session.updated_at = datetime.now(timezone.utc)

    db.commit()

    return final_response
