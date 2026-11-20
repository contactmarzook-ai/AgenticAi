"""Draft a workflow from a plain-language description, using the platform's own model."""

import json
import logging

from sqlalchemy.orm import Session

from ..llm.client import LLMError, get_llm_client
from ..models import User
from ..nodes import NODE_TYPES
from .blueprint import to_definition
from .models_service import ModelNotAvailable, resolve_model, to_target
from .platform_settings import get_settings
from .workflow_validator import validate_definition

logger = logging.getLogger("agentos.ai_builder")

# Problems the user is expected to fix in the builder after generation (not generation errors).
USER_FIXABLE = ("fill in", "connection", "choose an agent", "select an agent")


class BuilderError(Exception):
    pass


def _catalog(disabled: set[str]) -> str:
    lines = []
    for nt in NODE_TYPES.values():
        if nt.key in disabled:
            continue
        fields = ", ".join(
            f"{f.key} ({f.type}{', required' if f.required else ''}{', options: ' + '/'.join(f.options) if f.options else ''})"
            for f in nt.fields
        )
        lines.append(f"- {nt.key}: {nt.description} Fields: {fields}. Output: {nt.output_hint or '{...}'}")
    return "\n".join(lines)


SYSTEM = """You design no-code automation workflows. Reply with ONE JSON object and nothing else.

Format:
{{
  "name": "short name",
  "description": "one sentence",
  "steps": [
    {{"id": "start", "type": "start", "label": "...", "fields": [{{"key": "snake_case", "label": "...", "type": "text|textarea|number|email|select|boolean|date", "required": true}}]}},
    {{"id": "<short_id>", "type": "action", "action": "<action key from the list>", "label": "...", "config": {{"<field key>": "<value>"}}}},
    {{"id": "<short_id>", "type": "if", "label": "...", "left": "{{{{...}}}}", "operator": "==|!=|>|<|>=|<=|contains|not_contains|is_empty|not_empty", "right": "..."}},
    {{"id": "<short_id>", "type": "repeat", "label": "...", "items": "{{{{<step id>.<list field>}}}}", "action": "<action key>", "config": {{"<field>": "... {{{{item}}}} ..."}}}},
    {{"id": "<short_id>", "type": "switch", "label": "...", "value": "{{{{...}}}}", "cases": ["a", "b"]}},
    {{"id": "finish", "type": "finish", "label": "...", "output": "{{{{<step id>.<field>}}}}"}}
  ],
  "links": [{{"from": "start", "to": "<id>"}}, {{"from": "<if id>", "to": "<id>", "branch": "true|false"}}, {{"from": "<switch id>", "to": "<id>", "branch": "<case>|default"}}]
}}

Rules:
- Exactly one "start" step (its "fields" are the form the user fills in; use [] for scheduled/webhook automations) and at least one "finish" step.
- Use only these actions:
{catalog}
- Refer to data with variables: {{{{input.<form field key>}}}} or {{{{<step id>.<output field>}}}}.
- "list" fields are JSON arrays of strings; "keyvalue" fields are JSON objects; "credential" fields must be "" (the user picks a connection later).
- Every step must be linked; every "if" needs both a "true" and a "false" link; every switch case and "default" should be linked.
- Use "repeat" to apply one action to every item of a list; inside its config, {{{{item}}}} is the current item. Its output is {{"results": [...]}}.
- Keep it as simple as possible: usually 3-8 steps. Use AI steps for reading, deciding and writing text.
"""


def _parse(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise BuilderError("The AI did not return a workflow")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise BuilderError("The AI returned an incomplete workflow") from exc
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise BuilderError("The AI returned an incomplete workflow")
    return data


def generate(db: Session, user: User, prompt: str) -> dict:
    """Returns {"name", "description", "definition", "warnings", "usage"}; raises BuilderError."""
    platform = get_settings(db)
    if not platform.get("ai_builder_enabled", True):
        raise BuilderError("The AI builder is turned off by your administrator")
    try:
        model = resolve_model(db, None, user.role)
    except ModelNotAvailable as exc:
        raise BuilderError(str(exc)) from exc

    system = SYSTEM.format(catalog=_catalog(set(platform.get("disabled_nodes") or [])))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": f"Automate this: {prompt}"}]
    client = get_llm_client()
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    last_errors: list[str] = []

    for attempt in range(2):
        try:
            resp = client.chat(to_target(model), messages, temperature=0.1, json_mode=True)
        except LLMError as exc:
            raise BuilderError(str(exc)) from exc
        usage["prompt_tokens"] += resp.prompt_tokens
        usage["completion_tokens"] += resp.completion_tokens
        try:
            blueprint = _parse(resp.content)
            definition = to_definition(blueprint)
        except BuilderError as exc:
            last_errors = [str(exc)]
        else:
            errors = validate_definition(definition, db, owner=user)
            blocking = [e for e in errors if not any(k in e for k in USER_FIXABLE)]
            if not blocking:
                return {
                    "name": str(blueprint.get("name") or "New workflow")[:200],
                    "description": str(blueprint.get("description") or prompt)[:2000],
                    "definition": definition,
                    "warnings": errors,
                    "usage": usage,
                }
            last_errors = blocking
        logger.info("AI builder attempt %d rejected: %s", attempt + 1, last_errors)
        messages += [
            {"role": "assistant", "content": resp.content},
            {
                "role": "user",
                "content": "Fix these problems and reply with the full corrected JSON:\n- " + "\n- ".join(last_errors),
            },
        ]
    raise BuilderError(
        "The AI could not produce a valid workflow. Try describing it in simpler steps. Problems: "
        + "; ".join(last_errors[:5])
    )
