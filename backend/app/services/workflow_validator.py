"""Static checks run before a workflow version can be activated or tested."""

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agent
from ..tools import registry
from .workflow_engine import WorkflowError, edge_branch, topological_order

NODE_TYPES = {"input", "agent", "tool", "condition", "transform", "end"}
MAPPING_SOURCES = {"static", "input", "workflow", "node", "template"}


def validate_definition(definition: dict, db: Session) -> list[str]:
    errors: list[str] = []
    if not isinstance(definition, dict):
        return ["Definition must be an object with nodes and edges"]
    nodes = definition.get("nodes") or []
    edges = definition.get("edges") or []
    if not nodes:
        return ["Workflow must have at least one node"]
    if len(nodes) > settings.workflow_max_nodes:
        errors.append(f"Workflow has {len(nodes)} nodes; the limit is {settings.workflow_max_nodes}")

    ids = [n.get("id") for n in nodes]
    if any(not i for i in ids):
        return ["Every node needs an id"]
    if len(set(ids)) != len(ids):
        errors.append("Node ids must be unique")
    by_id = {n["id"]: n for n in nodes}

    for e in edges:
        if e.get("source") not in by_id or e.get("target") not in by_id:
            errors.append(f"Edge {e.get('id', '?')} points to a node that does not exist")
    edges = [e for e in edges if e.get("source") in by_id and e.get("target") in by_id]

    inputs = [n for n in nodes if n.get("type") == "input"]
    ends = [n for n in nodes if n.get("type") == "end"]
    if len(inputs) != 1:
        errors.append("Workflow must have exactly one Input node")
    if not ends:
        errors.append("Workflow must have at least one End node")

    has_in = {e["target"] for e in edges}
    has_out = {e["source"] for e in edges}

    for node in nodes:
        nid, ntype, data = node["id"], node.get("type"), node.get("data") or {}
        label = f"{data.get('label') or ntype} ({nid})"
        if ntype not in NODE_TYPES:
            errors.append(f"{label}: unknown node type '{ntype}'")
            continue
        if ntype == "input" and nid in has_in:
            errors.append(f"{label}: the Input node cannot have incoming connections")
        if ntype != "input" and nid not in has_in:
            errors.append(f"{label}: not connected to anything before it")
        if ntype != "end" and nid not in has_out:
            errors.append(f"{label}: not connected to anything after it")

        for key, m in (data.get("mappings") or {}).items():
            if not isinstance(m, dict) or m.get("source") not in MAPPING_SOURCES:
                errors.append(f"{label}: mapping '{key}' has an invalid source")
            elif m.get("source") == "node" and m.get("node_id") not in by_id:
                errors.append(f"{label}: mapping '{key}' reads from a node that does not exist")

        if ntype == "agent":
            agent_id = data.get("agent_id")
            agent = db.get(Agent, int(agent_id)) if str(agent_id or "").isdigit() else None
            if agent is None:
                errors.append(f"{label}: select an agent")
            elif not agent.is_active:
                errors.append(f"{label}: agent '{agent.name}' is disabled")
        elif ntype == "tool":
            tool = registry.get_tool(str(data.get("tool") or ""))
            if tool is None:
                errors.append(f"{label}: select a valid tool")
            else:
                mapped = set((data.get("mappings") or {}).keys())
                for req in tool.parameters.get("required", []):
                    if req not in mapped:
                        errors.append(f"{label}: tool argument '{req}' is not mapped")
        elif ntype == "condition":
            cond = data.get("condition") or {}
            if cond.get("operator") not in {"==", "!=", ">", "<", ">=", "<=", "contains", "is_empty", "not_empty"}:
                errors.append(f"{label}: choose a condition operator")
            for e in edges:
                if e["source"] == nid and edge_branch(e) not in ("true", "false"):
                    errors.append(f"{label}: every outgoing connection must use the true or false handle")
                    break

    try:
        order = topological_order(nodes, edges)
    except WorkflowError:
        errors.append("Workflow contains a cycle")
        order = []

    if order and len(inputs) == 1:
        reachable = {inputs[0]["id"]}
        for nid in order:
            if any(e["source"] in reachable for e in edges if e["target"] == nid):
                reachable.add(nid)
        for nid in by_id:
            if nid not in reachable:
                errors.append(f"Node {nid} cannot be reached from the Input node")

    return errors
