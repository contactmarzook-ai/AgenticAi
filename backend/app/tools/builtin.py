"""Agent tools are generated from the workflow step catalogue, so there is one set of building
blocks: the same names, the same behaviour, and the same admin switches and HTTP allowlist.

Only steps that make sense for a model to call on its own are exposed (no AI-in-AI steps, no
steps that need a saved connection or pause the run). Add a key to AGENT_STEPS to expose more.
"""

from ..nodes import NODE_TYPES, NodeContext, NodeError
from .registry import Tool, ToolError, register

AGENT_STEPS = {
    "calculate": "user",
    "date_time": "user",
    "text_tools": "user",
    "parse_json": "user",
    "fill_template": "user",
    "compose_text": "user",
    "http_request": "developer",
}

# Names used before the catalogue was unified; agents saved with them keep working.
ALIASES = {
    "calculator": "calculate",
    "get_current_time": "date_time",
    "http_get": "http_request",
    "render_template": "fill_template",
}

_SKIP_FIELD_TYPES = {"credential", "agent"}


def _schema_for(field) -> dict:
    t = field.type
    if t in ("text", "textarea"):
        s = {"type": "string"}
    elif t == "number":
        s = {"type": "number"}
    elif t == "boolean":
        s = {"type": "boolean"}
    elif t == "select":
        s = {"type": "string", "enum": list(field.options)}
    elif t == "list":
        s = {"type": "array", "items": {"type": "string"}}
    elif t == "keyvalue":
        s = {"type": "object", "additionalProperties": {"type": ["string", "number", "boolean"]}}
    else:  # json: any value
        s = {}
    return {**s, "description": field.label + (f". {field.help}" if field.help else "")}


def _unavailable(*_a, **_k):
    raise NodeError("Not available when called by an agent")


def _make_tool(node_key: str, min_role: str) -> Tool:
    nt = NODE_TYPES[node_key]
    fields = [f for f in nt.fields if f.type not in _SKIP_FIELD_TYPES]
    parameters = {
        "type": "object",
        "properties": {f.key: _schema_for(f) for f in fields},
        "required": [f.key for f in fields if f.required],
        "additionalProperties": False,
    }

    def fn(**args):
        from ..services.platform_settings import get_settings

        settings = get_settings()
        if node_key in set(settings.get("disabled_nodes") or []):
            raise ToolError(f"'{nt.name}' is disabled by your administrator")
        values = {f.key: args.get(f.key, f.default) for f in nt.fields}
        ctx = NodeContext(
            role="user", get_credential=_unavailable, ask_llm=_unavailable, run_agent=_unavailable, settings=settings
        )
        try:
            return nt.handler(values, ctx)
        except NodeError as exc:
            raise ToolError(str(exc)) from exc

    return Tool(
        name=node_key, description=f"{nt.name}: {nt.description}", parameters=parameters, fn=fn, min_role=min_role
    )


for _key, _role in AGENT_STEPS.items():
    register(_make_tool(_key, _role))
