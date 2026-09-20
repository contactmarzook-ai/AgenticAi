import json
import requests
from typing import Dict, Any, Tuple
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
    for wf in workflows:
         desc = f"- TYPE: workflow | ID: {wf.id} | NAME: {wf.name} | DESC: {wf.description}"
         tools_desc.append(desc)

    tools_str = "\n".join(tools_desc) if tools_desc else "No tools available."

    prompt = f"""You are an AI Orchestrator that acts as an intelligent router.
Your job is to analyze user requests and determine which tool (agent or workflow) to execute.

Available tools:
{tools_str}

You MUST return your response as valid JSON ONLY, with NO markdown formatting, NO backticks, and NO conversational text.

If you can map the request to a specific agent or workflow, return exactly:
{{"action": "agent" or "workflow", "target_id": integer_id, "parameters": {{"param1": "value1"}}}}
Note: For workflows, parameters might be optional or empty depending on the first step.

If the request is ambiguous, lacks required parameters, or doesn't match a tool, ask for clarification:
{{"action": "clarify", "message": "Your clarification message here"}}

If it's just a conversational greeting, respond appropriately:
{{"action": "chat", "message": "Hello! How can I help you today?"}}
"""
    return prompt

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

    # 2. Build prompt & call LLM
    system_prompt = build_dynamic_prompt(db)
    full_prompt = f"{system_prompt}\n\nUser Request: {user_input}"

    llm_response = call_llama(full_prompt)
    action = llm_response.get("action")

    # Setup response payload
    final_response = {
        "status": "success",
        "action": action,
        "message": "",
        "execution_trace": None,
        "llm_reasoning": llm_response
    }

    metadata = {"llm_routing": llm_response}

    # 3. Route
    if action == "error":
        final_response["status"] = "error"
        final_response["message"] = llm_response.get("message", "An unknown error occurred.")

    elif action in ["clarify", "chat"]:
        final_response["message"] = llm_response.get("message", "Could you provide more details?")

    elif action == "agent":
        target_id = llm_response.get("target_id")
        params = llm_response.get("parameters", {})

        agent = db.query(Agent).filter(Agent.id == target_id).first()
        if agent:
             exe_result = execute_agent_script(agent.python_code, params)
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
        target_id = llm_response.get("target_id")
        params = llm_response.get("parameters", {})

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
