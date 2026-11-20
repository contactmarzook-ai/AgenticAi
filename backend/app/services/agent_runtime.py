"""Runs an agent: system prompt + conversation + an OpenAI-style tool-calling loop.

Controls applied on every run:
- the model must be active and allowed for the caller's role
- the model can only call tools attached to the agent
- tool arguments are validated against the tool's JSON Schema
- step cap (agent.max_steps, bounded by AGENT_MAX_STEPS_CAP), per-tool timeout and overall deadline
"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..llm.client import LLMError, get_llm_client
from ..models import Agent
from ..tools import registry
from .models_service import resolve_model, to_target
from .platform_settings import get_settings

MAX_TOOL_RESULT_CHARS = 8000


class AgentRunError(Exception):
    pass


@dataclass
class AgentResult:
    answer: str
    model_name: str
    steps: list = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"... [truncated {len(text) - limit} chars]"


def run_agent(
    db: Session,
    agent: Agent,
    message: str,
    role: str,
    history: Optional[list[dict]] = None,
) -> AgentResult:
    if not agent.is_active:
        raise AgentRunError(f"Agent '{agent.name}' is disabled")
    try:
        model = resolve_model(db, agent.model_id, role)
    except Exception as exc:
        raise AgentRunError(str(exc)) from exc

    target = to_target(model)
    client = get_llm_client()
    deadline = time.monotonic() + settings.agent_timeout_seconds
    max_steps = max(1, min(agent.max_steps or 1, settings.agent_max_steps_cap))

    disabled = set(get_settings(db).get("disabled_nodes") or [])
    tool_names = []
    for t in agent.tools or []:
        name = registry.canonical(t)
        if registry.get_tool(name) and name not in disabled and name not in tool_names:
            tool_names.append(name)
    tool_specs = [registry.get_tool(t).openai_spec() for t in tool_names] if model.supports_tools else []

    messages: list[dict] = []
    if agent.system_prompt:
        messages.append({"role": "system", "content": agent.system_prompt})
    messages.extend(history or [])
    messages.append({"role": "user", "content": message})

    result = AgentResult(answer="", model_name=model.model_name)

    def call(with_tools: bool):
        if time.monotonic() > deadline:
            raise AgentRunError(f"Agent exceeded the {settings.agent_timeout_seconds}s time limit")
        started = time.monotonic()
        try:
            resp = client.chat(
                target, messages, tools=tool_specs if with_tools else None, temperature=agent.temperature
            )
        except LLMError as exc:
            raise AgentRunError(str(exc)) from exc
        result.llm_calls += 1
        result.prompt_tokens += resp.prompt_tokens
        result.completion_tokens += resp.completion_tokens
        result.steps.append(
            {
                "type": "llm",
                "content": _truncate(resp.content, 2000),
                "tool_calls": [{"name": c.name, "arguments": _truncate(c.arguments, 2000)} for c in resp.tool_calls],
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        )
        return resp

    for _ in range(max_steps):
        resp = call(with_tools=bool(tool_specs))
        if not resp.tool_calls:
            result.answer = resp.content
            return result

        messages.append(
            {
                "role": "assistant",
                "content": resp.content or "",
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                    for c in resp.tool_calls
                ],
            }
        )
        for c in resp.tool_calls:
            started = time.monotonic()
            c.name = registry.canonical(c.name)
            step = {"type": "tool", "name": c.name}
            try:
                if c.name not in tool_names:
                    raise registry.ToolError(f"Tool '{c.name}' is not available to this agent")
                try:
                    args = json.loads(c.arguments or "{}")
                except json.JSONDecodeError:
                    raise registry.ToolError("Tool arguments were not valid JSON")
                step["arguments"] = args
                output = registry.execute(c.name, args)
                content = _truncate(json.dumps(output, default=str), MAX_TOOL_RESULT_CHARS)
                step["status"] = "success"
                step["output"] = _truncate(content, 2000)
            except registry.ToolError as exc:
                content = json.dumps({"error": str(exc)})
                step["status"] = "error"
                step["error"] = str(exc)
            step["duration_ms"] = int((time.monotonic() - started) * 1000)
            result.steps.append(step)
            messages.append({"role": "tool", "tool_call_id": c.id, "name": c.name, "content": content})

    # Step budget used up: ask for a final answer without tools.
    messages.append({"role": "user", "content": "Stop using tools now and give your best final answer."})
    resp = call(with_tools=False)
    result.answer = resp.content
    return result
