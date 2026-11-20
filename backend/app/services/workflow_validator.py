"""Checks run before a workflow is tested or activated. Messages are written for non-technical users."""

from typing import Any, Optional

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agent, Credential, User
from ..nodes import NODE_TYPES
from ..rbac import can_view
from ..tools import registry
from .form_input import EMAIL_RE
from .platform_settings import get_settings
from .workflow_engine import WorkflowError, edge_branch, topological_order  # noqa: F401

NODE_TYPES_ALLOWED = {"input", "action", "loop", "condition", "switch", "end", "agent", "tool", "transform"}
OPERATORS = {"==", "!=", ">", "<", ">=", "<=", "contains", "not_contains", "starts_with", "is_empty", "not_empty"}
MAPPING_SOURCES = {"static", "input", "workflow", "node", "template"}


class _Node(BaseModel):
    id: str
    type: str
    data: dict = {}


class _Edge(BaseModel):
    id: Optional[Any] = None
    source: str
    target: str
    sourceHandle: Optional[str] = None
    label: Optional[Any] = None


def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, (list, dict)) and not v)


def _credential_ok(db: Session, owner: Optional[User], cred_id: Any, allowed_types: set[str]) -> Optional[str]:
    try:
        cred = db.get(Credential, int(cred_id))
    except (TypeError, ValueError):
        cred = None
    if cred is None:
        return "the selected connection no longer exists"
    if cred.type not in allowed_types:
        return "the selected connection is the wrong kind"
    if owner is not None and not can_view(owner, cred):
        return "the workflow owner does not have access to the selected connection"
    return None


def _agent_ok(db: Session, owner: Optional[User], agent_id: Any) -> Optional[str]:
    agent = db.get(Agent, int(agent_id)) if str(agent_id or "").isdigit() else None
    if agent is None or (owner is not None and not can_view(owner, agent)):
        return "choose an agent"
    if not agent.is_active:
        return f"agent '{agent.name}' is disabled"
    return None


def validate_definition(definition: Any, db: Session, owner: Optional[User] = None) -> list[str]:
    if not isinstance(definition, dict):
        return ["The workflow is not in a valid format"]
    try:
        nodes = [_Node.model_validate(n) for n in (definition.get("nodes") or [])]
        edges = [_Edge.model_validate(e) for e in (definition.get("edges") or [])]
    except (ValidationError, TypeError):
        return ["The workflow is not in a valid format (steps or connections are malformed)"]

    if not nodes:
        return ["Add at least one step"]
    errors: list[str] = []
    if len(nodes) > settings.workflow_max_nodes:
        errors.append(f"The workflow has {len(nodes)} steps; the limit is {settings.workflow_max_nodes}")

    ids = [n.id for n in nodes]
    if len(set(ids)) != len(ids):
        errors.append("Two steps have the same id")
    by_id = {n.id: n for n in nodes}
    bad_edges = [e for e in edges if e.source not in by_id or e.target not in by_id]
    if bad_edges:
        errors.append("A connection points to a step that no longer exists - remove it")
    edges = [e for e in edges if e.source in by_id and e.target in by_id]

    starts = [n for n in nodes if n.type == "input"]
    if len(starts) != 1:
        errors.append("The workflow needs exactly one Start step")
    if not any(n.type == "end" for n in nodes):
        errors.append("Add a Finish step")

    has_in = {e.target for e in edges}
    has_out = {e.source for e in edges}
    platform = get_settings(db)
    disabled = set(platform.get("disabled_nodes") or [])

    for n in nodes:
        data = n.data or {}
        label = f"'{data.get('label') or n.type}'"
        if n.type not in NODE_TYPES_ALLOWED:
            errors.append(f"{label}: unknown step type")
            continue
        if n.type == "input" and n.id in has_in:
            errors.append(f"{label}: nothing can lead into the Start step")
        if n.type != "input" and n.id not in has_in:
            errors.append(f"{label}: not connected to a previous step")
        if n.type != "end" and n.id not in has_out:
            errors.append(f"{label}: not connected to a next step")

        if n.type == "loop" and _empty(data.get("items")):
            errors.append(f"{label}: choose the list to go through")
        if n.type in ("action", "loop"):
            ntype = NODE_TYPES.get(str(data.get("action") or ""))
            if ntype is None:
                errors.append(f"{label}: choose what this step does")
                continue
            if ntype.key in disabled:
                errors.append(f"{label}: '{ntype.name}' steps are disabled by your administrator")
            config = data.get("config") or {}
            if not isinstance(config, dict):
                errors.append(f"{label}: settings are malformed")
                continue
            for f in ntype.fields:
                value = config.get(f.key, f.default)
                if f.required and _empty(value):
                    errors.append(f"{label}: fill in '{f.label}'")
                elif f.type == "credential" and not _empty(value):
                    problem = _credential_ok(db, owner, value, set((f.credential_type or "").split("|")))
                    if problem:
                        errors.append(f"{label}: {problem}")
                elif f.type == "agent" and not _empty(value):
                    problem = _agent_ok(db, owner, value)
                    if problem:
                        errors.append(f"{label}: {problem}")
        elif n.type == "condition":
            cond = data.get("condition") or {}
            if not isinstance(cond, dict) or cond.get("operator") not in OPERATORS:
                errors.append(f"{label}: choose how to compare")
            for e in edges:
                if e.source == n.id and edge_branch(e.model_dump()) not in ("true", "false"):
                    errors.append(f"{label}: connect from the Yes or No handle")
                    break
        elif n.type == "switch":
            cases = data.get("cases") or []
            if not isinstance(cases, list) or not [c for c in cases if str(c).strip()]:
                errors.append(f"{label}: add at least one case")
            names = [str(c).strip().lower() for c in cases if str(c).strip()] if isinstance(cases, list) else []
            if len(set(names)) != len(names):
                errors.append(f"{label}: two paths have the same name")
            if "default" in names:
                errors.append(f"{label}: 'default' is reserved; give the path another name")
            valid = set(names) | {"default"}
            for e in edges:
                if e.source == n.id and edge_branch(e.model_dump()) not in valid:
                    errors.append(f"{label}: a connection leaves from a case that no longer exists")
                    break
        elif n.type == "agent":
            problem = _agent_ok(db, owner, data.get("agent_id"))
            if problem:
                errors.append(f"{label}: {problem}")
        elif n.type == "tool":
            tool = registry.get_tool(str(data.get("tool") or ""))
            if tool is None:
                errors.append(f"{label}: choose a tool")
            else:
                mapped = set((data.get("mappings") or {}).keys())
                for req in tool.parameters.get("required", []):
                    if req not in mapped:
                        errors.append(f"{label}: tool argument '{req}' is not set")
        for key, m in (data.get("mappings") or {}).items() if isinstance(data.get("mappings"), dict) else []:
            if isinstance(m, dict) and "source" in m:
                if m.get("source") not in MAPPING_SOURCES:
                    errors.append(f"{label}: value '{key}' has an invalid source")
                elif m.get("source") == "node" and m.get("node_id") not in by_id:
                    errors.append(f"{label}: value '{key}' reads from a step that does not exist")

    plain_edges = [e.model_dump() for e in edges]
    plain_nodes = [n.model_dump() for n in nodes]
    try:
        order = topological_order(plain_nodes, plain_edges)
    except WorkflowError as exc:
        errors.append(str(exc))
        order = []

    if order and len(starts) == 1:
        reachable = {starts[0].id}
        for nid in order:
            if any(e.source in reachable for e in edges if e.target == nid):
                reachable.add(nid)
        for nid in by_id:
            if nid not in reachable:
                errors.append(f"'{(by_id[nid].data or {}).get('label') or nid}' cannot be reached from Start")

    notify = ((definition.get("settings") or {}) if isinstance(definition.get("settings"), dict) else {}).get(
        "notify_on_failure"
    )
    if isinstance(notify, dict) and notify.get("credential_id"):
        problem = _credential_ok(db, owner, notify["credential_id"], {"slack_webhook", "teams_webhook", "smtp"})
        if problem:
            errors.append(f"Failure alerts: {problem}")
        else:
            cred = db.get(Credential, int(notify["credential_id"]))
            if cred.type == "smtp" and _empty(notify.get("email_to")):
                errors.append("Failure alerts: enter the email address to notify")
            elif cred.type == "smtp" and not EMAIL_RE.match(str(notify.get("email_to")).strip()):
                errors.append("Failure alerts: the alert address is not a valid email address")

    errors.extend(reference_problems(definition)[0])
    return errors


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def reference_problems(definition: Any) -> tuple[list[str], list[str]]:
    """Check {{ }} references. Returns (errors, warnings).

    Errors: a reference to a step that does not exist, or that never runs before the step using it.
    Warnings: a reference to a form field the Start step does not define (webhooks may still send it).
    """
    from .workflow_engine import VAR_RE

    if not isinstance(definition, dict):
        return [], []
    nodes = [n for n in definition.get("nodes") or [] if isinstance(n, dict) and isinstance(n.get("id"), str)]
    edges = [e for e in definition.get("edges") or [] if isinstance(e, dict)]
    by_id = {n["id"]: n for n in nodes}
    parents: dict[str, set] = {}
    for e in edges:
        if isinstance(e.get("source"), str) and isinstance(e.get("target"), str):
            parents.setdefault(e["target"], set()).add(e["source"])

    def ancestors(nid: str) -> set:
        seen, stack = set(), list(parents.get(nid, ()))
        while stack:
            cur = stack.pop()
            if cur not in seen:
                seen.add(cur)
                stack.extend(parents.get(cur, ()))
        return seen

    start = next((n for n in nodes if n.get("type") == "input"), None)
    start_data = (start or {}).get("data")
    start_fields = start_data.get("fields") if isinstance(start_data, dict) else None
    form_keys = (
        {f.get("key") for f in start_fields or [] if isinstance(f, dict)} if isinstance(start_fields, list) else set()
    )
    errors, warnings = [], []
    for n in nodes:
        data = n.get("data") if isinstance(n.get("data"), dict) else {}
        label = f"'{data.get('label') or n.get('type')}'"
        before = None
        for text in _strings({k: v for k, v in data.items() if k not in ("label", "fields")}):
            for m in VAR_RE.finditer(text):
                root, path = m.group(1), m.group(2).lstrip(".")
                if root in ("item", "index") and n.get("type") == "loop":
                    continue
                if root == "input":
                    field = path.split(".")[0] if path else ""
                    if form_keys and field and field not in form_keys and field != "message":
                        warnings.append(f"{label} uses form field '{field}', which the Start form does not have")
                    continue
                if root not in by_id:
                    errors.append(f"{label} uses data from a step that no longer exists ({m.group(0)})")
                    continue
                before = ancestors(n["id"]) if before is None else before
                if root not in before:
                    src = (by_id[root].get("data") or {}).get("label") or root
                    errors.append(f"{label} uses data from '{src}', which does not run before it")
    return sorted(set(errors)), sorted(set(warnings))
