import json
import requests
from typing import Dict, Any

from workflows import WORKFLOW_REGISTRY

def build_system_prompt() -> str:
    """
    Dynamically generates a system prompt based on the WORKFLOW_REGISTRY.
    Instructs the LLM to act as a router and return strict JSON.
    """
    tools_desc = []
    for name, config in WORKFLOW_REGISTRY.items():
        params = ", ".join([f"{p['name']} ({p['type']})" for p in config['parameters']])
        tools_desc.append(f"- {name}: {config['description']}. Parameters: {params}")

    tools_str = "\n".join(tools_desc)

    prompt = f"""You are an AI Orchestrator that acts as an intelligent router.
Your job is to analyze user requests and determine which tool to use.

Available tools:
{tools_str}

You MUST return your response as valid JSON ONLY, with NO markdown formatting, NO backticks, and NO conversational text.

If you can map the request to a tool, return:
{{"action": "tool_name", "parameters": {{"param1": "value1", "param2": "value2"}}}}

If the request is ambiguous, lacks required parameters, or doesn't match a tool, ask for clarification:
{{"action": "clarify", "message": "Your clarification message here"}}
"""
    return prompt

def call_llama(prompt: str) -> Dict[str, Any]:
    """
    Calls a local Llama model via the Ollama API, enforcing JSON output.
    """
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "llama3",
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Parse the JSON string within the response
        content = data.get("response", "{}")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"action": "clarify", "message": "Failed to parse LLM output as JSON."}

    except requests.exceptions.RequestException as e:
        return {"action": "clarify", "message": f"Error communicating with local LLM: {str(e)}"}

def process_agent_interaction(user_input: str) -> Dict[str, Any]:
    """
    Main orchestration logic: builds prompt, calls LLM, and routes execution.
    """
    system_prompt = build_system_prompt()
    full_prompt = f"{system_prompt}\n\nUser Request: {user_input}"

    llm_response = call_llama(full_prompt)

    action = llm_response.get("action")

    if action in ["clarify", "chat"]:
        return {
            "status": "clarification_needed",
            "message": llm_response.get("message", "Could you please provide more details?")
        }

    if action in WORKFLOW_REGISTRY:
        tool = WORKFLOW_REGISTRY[action]
        func = tool["function"]
        parameters = llm_response.get("parameters", {})

        try:
            # Secure execution: we only pass extracted parameters to registered functions
            result = func(**parameters)
            return {
                "status": "success",
                "action_executed": action,
                "result": result
            }
        except TypeError as e:
             return {
                "status": "error",
                "message": f"Parameter mismatch for {action}: {str(e)}"
            }
        except Exception as e:
             return {
                 "status": "error",
                 "message": f"Error executing {action}: {str(e)}"
             }

    return {
        "status": "error",
        "message": f"Unknown action requested by LLM: {action}"
    }
