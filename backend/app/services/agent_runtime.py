"""Runs an agent: system prompt + conversation + an OpenAI-style tool-calling loop.

Controls applied on every run:
- the model must be active and allowed for the caller's role
- the model can only call tools attached to the agent
- tool arguments are validated against the tool's JSON Schema
- step cap (agent.max_steps, bounded by AGENT_MAX_STEPS_CAP), per-tool timeout and overall deadline
- the input must match the agent's input schema before anything runs, and the result must match
  its output schema (one repair attempt, then the run fails); both checks are recorded as steps
"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from .. import contracts
from ..config import settings
from ..llm.client import LLMError, get_llm_client
from ..models import Agent
from ..tools import registry
from .models_service import resolve_model, to_target
from .platform_settings import get_settings

MAX_TOOL_RESULT_CHARS = 8000


class AgentRunError(Exception):
    def __init__(self, message: str, steps: Optional[list] = None):
        super().__init__(message)
        self.steps = steps


class ContractError(AgentRunError):
    """Input or output did not match the agent's contract."""

    def __init__(self, stage: str, errors: list[dict], steps: Optional[list] = None):
        label = "Input" if stage == "input" else "Output"
        super().__init__(f"{label} does not match the agent's {stage} schema: {contracts.format_errors(errors)}", steps)
        self.stage = stage
        self.errors = errors


@dataclass
class AgentResult:
    answer: str
    model_name: str
    output: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"... [truncated {len(text) - limit} chars]"


def effective_capabilities(agent: Agent) -> list[str]:
    """What the agent can actually do: declared capabilities, plus one per attached tool and
    whether it takes/returns structured data. Used for discovery by people and by the chat router."""
    caps = set(agent.capabilities or [])
    caps |= {f"tool:{registry.canonical(t)}" for t in agent.tools or []}
    if not contracts.is_default_output(agent.output_schema):
        caps.add("structured-output")
    if not contracts.is_default_input(agent.input_schema):
        caps.add("structured-input")
    return sorted(caps)


def check_input(agent: Agent, input_data) -> dict:
    """Validate (and fill defaults into) an agent's input. Raises ContractError."""
    schema = agent.input_schema or contracts.DEFAULT_INPUT_SCHEMA
    value, errors = contracts.validate(schema, input_data)
    if errors:
        raise ContractError(
            "input", errors, [{"type": "validation", "stage": "input", "valid": False, "errors": errors}]
        )
    return value


def run_agent(
    db: Session,
    agent: Agent,
    input_data: dict,
    role: str,
    history: Optional[list[dict]] = None,
) -> AgentResult:
    if not agent.is_active:
        raise AgentRunError(f"Agent '{agent.name}' is disabled")
    in_schema = agent.input_schema or contracts.DEFAULT_INPUT_SCHEMA
    out_schema = agent.output_schema or contracts.DEFAULT_OUTPUT_SCHEMA
    structured = not contracts.is_default_output(out_schema)
    value = check_input(agent, input_data)
    message = contracts.input_as_message(in_schema, value)
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
    system = agent.system_prompt or ""
    if structured:
        system += (
            "\n\nWhen you give your final answer, reply with ONE JSON object only (no prose, no code fence) "
            f"that matches this JSON Schema:\n{contracts.describe(out_schema)}"
        )
    if system.strip():
        messages.append({"role": "system", "content": system.strip()})
    messages.extend(history or [])
    messages.append({"role": "user", "content": message})

    result = AgentResult(answer="", model_name=model.model_name)
    result.steps.append({"type": "validation", "stage": "input", "valid": True, "errors": []})

    def call(with_tools: bool, json_mode: bool = False):
        if time.monotonic() > deadline:
            raise AgentRunError(f"Agent exceeded the {settings.agent_timeout_seconds}s time limit", result.steps)
        started = time.monotonic()
        try:
            resp = client.chat(
                target,
                messages,
                tools=tool_specs if with_tools else None,
                temperature=agent.temperature,
                json_mode=json_mode,
            )
        except LLMError as exc:
            raise AgentRunError(str(exc), result.steps) from exc
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

    def finish(text: str) -> AgentResult:
        if not structured:
            result.answer = text
            result.output = {"answer": text}
            _record_output(result, out_schema, result.output)
            return result
        # Structured contract: parse and validate; one repair attempt with the errors.
        for attempt in (1, 2):
            parsed, problem = contracts.parse_json_output(text)
            errors = [{"path": "(root)", "message": problem}] if problem else contracts.validate(out_schema, parsed)[1]
            output = contracts.apply_defaults(out_schema, parsed) if not problem else None
            result.steps.append(
                {"type": "validation", "stage": "output", "valid": not errors, "errors": errors, "attempt": attempt}
            )
            if not errors:
                result.output = output
                result.answer = json.dumps(output, ensure_ascii=False, indent=2)
                return result
            if attempt == 2:
                break
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": "Your answer does not match the required JSON Schema: "
                    + contracts.format_errors(errors)
                    + ". Reply again with the corrected JSON object only.",
                }
            )
            text = call(with_tools=False, json_mode=True).content
        result.answer = text
        raise ContractError("output", errors, result.steps)

    for _ in range(max_steps):
        resp = call(with_tools=bool(tool_specs))
        if not resp.tool_calls:
            return finish(resp.content)

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
    return finish(resp.content)


def _record_output(result: AgentResult, schema: dict, output: dict) -> None:
    _, errors = contracts.validate(schema, output)
    result.steps.append({"type": "validation", "stage": "output", "valid": not errors, "errors": errors, "attempt": 1})
    if errors:
        raise ContractError("output", errors, result.steps)
