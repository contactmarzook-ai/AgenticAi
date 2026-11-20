"""Data steps: shape, format and compute values without code."""

import json
import string
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..safe_eval import EvalError
from ..safe_eval import calculate as safe_calculate
from .base import Field, NodeContext, NodeError, node


@node(
    "set_fields",
    "Set fields",
    "Data",
    "Create named values for later steps (e.g. customer_name = {{input.name}}).",
    "list-plus",
    [
        Field(
            "fields",
            "Fields",
            "keyvalue",
            required=True,
            help="Name on the left, value (may use variables) on the right.",
        )
    ],
    output_hint="{ <your field names> }",
)
def set_fields(cfg: dict, ctx: NodeContext):
    fields = cfg.get("fields") or {}
    if not isinstance(fields, dict):
        raise NodeError("Fields must be name/value pairs")
    return dict(fields)


@node(
    "compose_text",
    "Compose text",
    "Data",
    "Write a message or document from a template with variables.",
    "file-text",
    [
        Field(
            "template",
            "Text",
            "textarea",
            required=True,
            placeholder="Hi {{input.name}},\n\nYour order {{input.order_id}} has shipped.",
        )
    ],
    output_hint="{ text }",
)
def compose_text(cfg: dict, ctx: NodeContext):
    return {"text": str(cfg["template"])}


@node(
    "parse_json",
    "Read JSON",
    "Data",
    "Turn JSON text (for example an API response body) into fields later steps can use.",
    "braces",
    [Field("text", "JSON text", "textarea", required=True, placeholder="{{http.body}}")],
    output_hint="{ data }",
)
def parse_json(cfg: dict, ctx: NodeContext):
    raw = cfg["text"]
    if isinstance(raw, (dict, list)):
        return {"data": raw}
    try:
        return {"data": json.loads(str(raw))}
    except json.JSONDecodeError as exc:
        raise NodeError(f"Not valid JSON: {exc.msg} at position {exc.pos}") from exc


@node(
    "calculate",
    "Calculate",
    "Data",
    "Do arithmetic, e.g. {{input.amount}} * 0.18",
    "calculator",
    [Field("expression", "Formula", "text", required=True, placeholder="{{input.amount}} * 1.18")],
    output_hint="{ result }",
)
def calculate(cfg: dict, ctx: NodeContext):
    try:
        return {"result": safe_calculate(str(cfg["expression"]))}
    except EvalError as exc:
        raise NodeError(str(exc)) from exc


@node(
    "date_time",
    "Date & time",
    "Data",
    "Get the current date/time, optionally shifted (e.g. 7 days from now) and formatted.",
    "calendar",
    [
        Field("timezone", "Timezone", "text", default="UTC", help="e.g. Asia/Kolkata, Europe/London"),
        Field("add_days", "Add days", "number", default=0, help="Negative for the past."),
        Field("format", "Format", "select", default="iso", options=("iso", "date", "datetime", "human")),
    ],
    output_hint="{ value, iso, weekday }",
)
def date_time(cfg: dict, ctx: NodeContext):
    try:
        tz = ZoneInfo(str(cfg.get("timezone") or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        raise NodeError(f"Unknown timezone '{cfg.get('timezone')}'") from None
    try:
        days = float(cfg.get("add_days") or 0)
    except (TypeError, ValueError):
        raise NodeError("Add days must be a number") from None
    when = datetime.now(tz) + timedelta(days=days)
    fmt = {"date": "%Y-%m-%d", "datetime": "%Y-%m-%d %H:%M", "human": "%A, %d %B %Y %H:%M"}.get(
        cfg.get("format") or "iso"
    )
    return {
        "value": when.strftime(fmt) if fmt else when.isoformat(),
        "iso": when.isoformat(),
        "weekday": when.strftime("%A"),
    }


@node(
    "text_tools",
    "Text tools",
    "Data",
    "Common text operations: upper/lower case, trim, length, find & replace, split into a list.",
    "type",
    [
        Field("text", "Text", "textarea", required=True),
        Field(
            "operation",
            "Operation",
            "select",
            default="trim",
            options=("trim", "uppercase", "lowercase", "length", "replace", "split"),
        ),
        Field(
            "find",
            "Find / separator",
            "text",
            help="For replace (text to find) or split (separator, default new line).",
        ),
        Field("replace_with", "Replace with", "text"),
    ],
    output_hint="{ result }",
)
def text_tools(cfg: dict, ctx: NodeContext):
    text, op = str(cfg["text"]), cfg.get("operation") or "trim"
    if op == "uppercase":
        return {"result": text.upper()}
    if op == "lowercase":
        return {"result": text.lower()}
    if op == "length":
        return {"result": len(text)}
    if op == "replace":
        return {
            "result": text.replace(str(cfg.get("find") or ""), str(cfg.get("replace_with") or ""))
            if cfg.get("find")
            else text
        }
    if op == "split":
        sep = cfg.get("find") or "\n"
        return {"result": [p.strip() for p in text.split(sep) if p.strip()]}
    return {"result": text.strip()}


@node(
    "fill_template",
    "Fill template ($name)",
    "Data",
    "Fill a template that uses $placeholders from a set of values.",
    "file-pen",
    [
        Field("template", "Template", "textarea", required=True, placeholder="Dear $name, ..."),
        Field("values", "Values", "keyvalue", required=True),
    ],
    output_hint="{ text }",
)
def fill_template(cfg: dict, ctx: NodeContext):
    values = cfg.get("values") or {}
    return {"text": string.Template(str(cfg["template"])).safe_substitute({k: str(v) for k, v in values.items()})}
