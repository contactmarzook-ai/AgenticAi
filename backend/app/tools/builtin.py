"""Built-in tools. Add organisation-specific tools in new modules and import them in registry.py."""

import ast
import operator
import string
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .registry import ToolError, tool


@tool(
    name="get_current_time",
    description="Get the current date and time in a given IANA timezone (default UTC).",
    parameters={
        "type": "object",
        "properties": {"timezone": {"type": "string", "description": "IANA timezone, e.g. Asia/Kolkata"}},
        "additionalProperties": False,
    },
    min_role="user",
)
def get_current_time(timezone: str = "UTC") -> dict:
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ToolError(f"Unknown timezone '{timezone}'")
    now = datetime.now(tz)
    return {"timezone": timezone, "iso": now.isoformat(), "weekday": now.strftime("%A")}


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ToolError("Exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ToolError("Only numbers and + - * / // % ** are allowed")


@tool(
    name="calculator",
    description="Evaluate an arithmetic expression such as '(1200 * 0.18) + 40'.",
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string", "maxLength": 200}},
        "required": ["expression"],
        "additionalProperties": False,
    },
    min_role="user",
)
def calculator(expression: str) -> dict:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        raise ToolError("Invalid expression")
    try:
        result = _eval_node(tree)
    except ZeroDivisionError:
        raise ToolError("Division by zero")
    return {"expression": expression, "result": result}


@tool(
    name="render_template",
    description="Fill a text template using $placeholders, e.g. 'Dear $name, ...'.",
    parameters={
        "type": "object",
        "properties": {
            "template": {"type": "string", "maxLength": 20000},
            "values": {"type": "object", "additionalProperties": {"type": ["string", "number", "boolean"]}},
        },
        "required": ["template", "values"],
        "additionalProperties": False,
    },
    min_role="user",
)
def render_template(template: str, values: dict) -> dict:
    return {"text": string.Template(template).safe_substitute({k: str(v) for k, v in values.items()})}


@tool(
    name="http_get",
    description="Fetch a URL with HTTP GET. Only hosts on the administrator's allowlist can be reached.",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string", "maxLength": 2000}},
        "required": ["url"],
        "additionalProperties": False,
    },
    min_role="builder",
)
def http_get(url: str) -> dict:
    from .. import safe_http
    from ..services.platform_settings import get_settings

    platform = get_settings()
    if not platform.get("http_allowed_hosts"):
        raise ToolError("http_get is disabled: no allowed hosts are configured (Settings > Outbound HTTP)")
    try:
        resp = safe_http.request("GET", url, platform, headers={"User-Agent": "AgentOS-http_get/1.0"}, timeout=15)
    except safe_http.BlockedRequest as exc:
        raise ToolError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"Request failed: {exc.__class__.__name__}") from exc
    return {
        "status_code": resp.status_code,
        "content_type": resp.headers.get("content-type", ""),
        "body": resp.text[:10_000],
    }
