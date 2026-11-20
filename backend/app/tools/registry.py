"""Tool registry.

Tools are Python functions registered in code (never stored or uploaded as code),
each with a JSON Schema for its arguments. Agents reference tools by name, and
the LLM can only call tools that are attached to the agent it is running as.
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any, Callable

import jsonschema

from ..config import settings

MAX_TOOL_OUTPUT_CHARS = 20_000


class ToolError(Exception):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema (type: object)
    fn: Callable[..., Any]
    # Lowest role allowed to attach this tool to an agent.
    min_role: str = "builder"

    def openai_spec(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


_REGISTRY: dict[str, Tool] = {}
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tool")


def register(tool: Tool) -> Tool:
    if tool.name in _REGISTRY:
        raise ValueError(f"Tool '{tool.name}' is already registered")
    jsonschema.Draft202012Validator.check_schema(tool.parameters)
    _REGISTRY[tool.name] = tool
    return tool


def tool(name: str, description: str, parameters: dict, min_role: str = "builder"):
    """Decorator form of `register`."""

    def wrap(fn):
        register(Tool(name=name, description=description, parameters=parameters, fn=fn, min_role=min_role))
        return fn

    return wrap


def canonical(name: str) -> str:
    from .builtin import ALIASES

    return ALIASES.get(name, name)


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(canonical(name))


def list_tools() -> list[Tool]:
    return sorted(_REGISTRY.values(), key=lambda t: t.name)


def _legacy_args(name: str, args: dict) -> dict:
    """Map arguments of the old tool names onto the unified steps."""
    if name == "http_get":
        return {"url": args.get("url"), "method": "GET"}
    return args


def list_tools_for(settings: dict) -> list[Tool]:
    disabled = set(settings.get("disabled_nodes") or [])
    return [t for t in list_tools() if t.name not in disabled]


def validate_args(tool_obj: Tool, args: Any) -> None:
    if not isinstance(args, dict):
        raise ToolError("Tool arguments must be a JSON object")
    try:
        jsonschema.validate(args, tool_obj.parameters)
    except jsonschema.ValidationError as exc:
        raise ToolError(f"Invalid arguments for '{tool_obj.name}': {exc.message}") from exc


def execute(name: str, args: Any, timeout: float | None = None) -> Any:
    tool_obj = get_tool(name)
    if tool_obj is None:
        raise ToolError(f"Unknown tool '{name}'")
    if name != tool_obj.name and isinstance(args, dict):
        args = _legacy_args(name, args)
    validate_args(tool_obj, args)
    future = _executor.submit(tool_obj.fn, **args)
    try:
        return future.result(timeout=timeout or settings.tool_timeout_seconds)
    except FutureTimeout as exc:
        raise ToolError(f"Tool '{name}' timed out") from exc
    except ToolError:
        raise
    except Exception as exc:  # tool bugs must not crash the run
        raise ToolError(f"Tool '{name}' failed: {exc.__class__.__name__}: {exc}") from exc


# Import built-in tools so they register themselves.
from . import builtin  # noqa: E402,F401
